import hashlib
import secrets
import subprocess
from pathlib import Path

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import AiFixRequest, BalleTourInvitation, Player, User
from routes.auth import login_required
from services.admin_tools import (
    DatabaseWriteError,
    create_backup,
    generate_test_rounds,
    list_backups,
    restore_backup,
    clear_balletour_rounds,
    clear_rounds,
)
from services.balletour_test_db import (
    PROD_DATABASE_VIEW,
    TEST_DATABASE_VIEW,
    current_balletour_database_view,
    delete_balletour_test_database,
    reset_balletour_test_database,
    set_balletour_database_view,
    test_database_exists,
    test_database_path,
)
from services.github_issues import (
    GitHubIssueError,
    apply_issue_snapshot,
    create_ai_issue,
    fetch_issue,
    fetch_issue_comments,
    fetch_issue_comments_for_ai_request,
    fetch_issue_for_ai_request,
    list_ai_issues,
    merge_ready_pull_request_for_ai_request,
)
from services.mailer import send_mail
from services.balletour import get_balletour_series

admin_bp = Blueprint("admin", __name__)
APP_ROOT = Path(__file__).resolve().parents[1]


def admin_required(view):
    @login_required
    def wrapped_view(*args, **kwargs):
        if not g.current_user.is_admin:
            flash("Du har ikke tilgang til admin.", "error")
            return redirect(url_for("main.index"))
        return view(*args, **kwargs)

    wrapped_view.__name__ = view.__name__
    return wrapped_view


AI_REQUEST_FILTERS = {
    "open": "Åpne",
    "new_open": "Åpne og nye",
    "ready": "Klar for deploy",
    "running": "Pågår",
    "failed": "Feilet",
    "deployed": "Deployet",
    "all": "Alle",
}


def _labels_for_request(fix_request):
    return {
        label.strip()
        for label in (fix_request.github_issue_labels or "").split(",")
        if label.strip()
    }


def _matches_ai_request_filter(fix_request, selected_filter):
    labels = _labels_for_request(fix_request)
    github_state = fix_request.github_issue_state or "open"
    if selected_filter == "all":
        return True
    if selected_filter == "new_open":
        return github_state == "open" and ("needs-triage" in labels or fix_request.status == "new")
    if selected_filter == "ready":
        return "ready-to-deploy" in labels
    if selected_filter == "running":
        return "in-progress" in labels or fix_request.status == "in_progress"
    if selected_filter == "failed":
        return "failed" in labels
    if selected_filter == "deployed":
        return "deployed" in labels or fix_request.status == "done"
    return github_state == "open"


def _prompt_from_issue(issue):
    body = issue.get("body") or ""
    marker = "## Prompt"
    if marker in body:
        prompt = body.split(marker, 1)[1].strip()
        if "\n## " in prompt:
            prompt = prompt.split("\n## ", 1)[0].strip()
        if prompt:
            return prompt
    return issue.get("title") or body or "GitHub issue"


def _upsert_ai_request_from_issue(issue, fallback_user_id):
    fix_request = AiFixRequest.query.filter_by(github_issue_number=issue["number"]).first()
    if not fix_request:
        fix_request = AiFixRequest(
            prompt=_prompt_from_issue(issue),
            created_by_user_id=fallback_user_id,
        )
        db.session.add(fix_request)
    else:
        fix_request.prompt = _prompt_from_issue(issue)

    apply_issue_snapshot(fix_request, issue)
    fix_request.github_title = issue.get("title") or fix_request.prompt
    return fix_request


def _hash_invitation_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _balletour_invitation_body(name, invitation_url):
    return (
        f"Hei {name},\n\n"
        "Du er invitert til BalleTour i Shanklife Pro.\n\n"
        "BalleTour er vår interne golftour der rundene spilles, scores og følges opp samlet. "
        "Her kan du registrere score hull for hull, se live leaderboard, følge egne og andres "
        "runder, og bygge statistikk over tid for score, putting, køller, greenvalg og utvikling.\n\n"
        "For å komme i gang må du sette passord for brukeren din. Trykk på lenken under, "
        "velg passord, og logg inn:\n\n"
        f"{invitation_url}\n\n"
        "Lenken kan bare brukes én gang. Hvis den ikke fungerer, si fra til en administrator, "
        "så kan du få en ny invitasjon.\n\n"
        "Velkommen til BalleTour. Måtte puttene sitte litt oftere enn de burde.\n\n"
        "Hilsen\n"
        "BalleTour / Shanklife Pro"
    )


def _sync_ai_requests_from_github(fallback_user_id):
    comments_by_request_id = {}
    errors = []
    issues = list_ai_issues(state="all")
    github_issue_numbers = {issue["number"] for issue in issues}

    if github_issue_numbers:
        stale_requests = AiFixRequest.query.filter(
            (AiFixRequest.github_issue_number.is_(None))
            | (~AiFixRequest.github_issue_number.in_(github_issue_numbers))
        ).all()
    else:
        stale_requests = AiFixRequest.query.all()
    for stale_request in stale_requests:
        db.session.delete(stale_request)

    fix_requests = []
    for issue in issues:
        fix_request = _upsert_ai_request_from_issue(issue, fallback_user_id)
        fix_requests.append(fix_request)
    db.session.flush()

    for fix_request in fix_requests:
        try:
            comments_by_request_id[fix_request.id] = fetch_issue_comments_for_ai_request(fix_request)
        except GitHubIssueError as exc:
            fix_request.github_sync_error = str(exc)
            errors.append(f"#{fix_request.github_issue_number}: {exc}")

    db.session.commit()
    return comments_by_request_id, errors


@admin_bp.route("/admin")
@admin_required
def admin_home():
    return render_template(
        "admin.html",
        backups=list_backups(),
        balletour_database_view=current_balletour_database_view(),
        balletour_test_database_exists=test_database_exists(),
        balletour_test_database_path=test_database_path(),
        pending_balletour_invitations=BalleTourInvitation.query.filter_by(accepted_at=None)
        .order_by(BalleTourInvitation.created_at.desc())
        .all(),
        balletour_series=get_balletour_series(),
        users=User.query.order_by(User.username.asc()).all(),
    )


@admin_bp.route("/admin/balletour-settings", methods=["POST"])
@admin_required
def update_balletour_settings():
    series = get_balletour_series()
    if not series:
        flash("Fant ikke BalleTour-serien.", "error")
        return redirect(url_for("admin.admin_home"))

    raw_min_rounds = request.form.get("min_qualifying_rounds", "").strip()
    try:
        min_rounds = int(raw_min_rounds)
    except ValueError:
        flash("Minimum runder må være et heltall.", "error")
        return redirect(url_for("admin.admin_home"))

    if min_rounds < 1 or min_rounds > 200:
        flash("Minimum runder må være mellom 1 og 200.", "error")
        return redirect(url_for("admin.admin_home"))

    series.min_qualifying_rounds = min_rounds
    db.session.commit()
    flash("Minimum tellende BalleTour-runder er oppdatert.", "success")
    return redirect(url_for("admin.admin_home"))


@admin_bp.route("/admin/balletour-invitations", methods=["POST"])
@admin_required
def invite_balletour_player():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()

    if not name or not email:
        flash("Navn og e-post må fylles ut.", "error")
        return redirect(url_for("admin.admin_home"))
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        flash("E-postadressen ser ikke gyldig ut.", "error")
        return redirect(url_for("admin.admin_home"))
    if not get_balletour_series():
        flash("Fant ikke BalleTour-serien.", "error")
        return redirect(url_for("admin.admin_home"))
    if Player.query.filter(db.func.lower(Player.name) == name.lower()).first():
        flash(f"Spilleren '{name}' finnes allerede.", "error")
        return redirect(url_for("admin.admin_home"))
    if User.query.filter(db.func.lower(User.username) == email.lower()).first():
        flash(f"Det finnes allerede en bruker med e-postadressen {email}.", "error")
        return redirect(url_for("admin.admin_home"))

    token = secrets.token_urlsafe(32)
    token_hash = _hash_invitation_token(token)
    invitation = BalleTourInvitation.query.filter(
        BalleTourInvitation.accepted_at.is_(None),
        db.func.lower(BalleTourInvitation.email) == email.lower(),
    ).first()
    if not invitation:
        invitation = BalleTourInvitation(
            name=name,
            email=email,
            token_hash=token_hash,
            invited_by_user_id=g.current_user.id,
        )
        db.session.add(invitation)
    else:
        invitation.name = name
        invitation.token_hash = token_hash
        invitation.invited_by_user_id = g.current_user.id

    invitation_url = url_for("auth.accept_balletour_invitation", token=token, _external=True)
    if not send_mail(
        "Du er invitert til BalleTour",
        _balletour_invitation_body(name, invitation_url),
        recipient=email,
    ):
        db.session.rollback()
        flash("Invitasjonen ble ikke sendt. Sjekk e-postoppsettet.", "error")
        return redirect(url_for("admin.admin_home"))

    db.session.commit()
    flash(f"Invitasjon sendt til {name} på {email}.", "success")
    return redirect(url_for("admin.admin_home"))


@admin_bp.route("/admin/users/<int:user_id>/admin-role", methods=["POST"])
@admin_required
def update_user_admin_role(user_id):
    user = User.query.get_or_404(user_id)
    should_be_admin = request.form.get("is_admin") == "1"

    if user.id == g.current_user.id and not should_be_admin:
        flash("Du kan ikke fjerne admin-rollen fra deg selv.", "error")
        return redirect(url_for("admin.admin_home"))

    if user.is_admin and not should_be_admin:
        admin_count = User.query.filter_by(is_admin=True).count()
        if admin_count <= 1:
            flash("Du kan ikke fjerne den siste admin-brukeren.", "error")
            return redirect(url_for("admin.admin_home"))

    user.is_admin = should_be_admin
    db.session.commit()
    flash(f"Admin-rolle oppdatert for {user.username}.", "success")
    return redirect(url_for("admin.admin_home"))


@admin_bp.route("/admin/ai-requests", methods=["GET", "POST"])
@admin_required
def ai_requests():
    if request.method == "POST":
        prompt = request.form.get("prompt", "").strip()
        if not prompt:
            flash("Prompt kan ikke være tom.", "error")
            return redirect(url_for("admin.ai_requests"))

        try:
            fix_request = AiFixRequest(
                prompt=prompt,
                created_by_user_id=g.current_user.id,
            )
            db.session.add(fix_request)
            db.session.flush()
            issue = create_ai_issue(prompt, g.current_user.username, internal_id=fix_request.id)
            apply_issue_snapshot(fix_request, issue)
            db.session.commit()
            send_mail(
                f"Ny GitHub-sak #{issue['number']} opprettet",
                (
                    f"Ny AI-sak er opprettet fra Shanklife admin.\n\n"
                    f"Sak: #{issue['number']} {issue.get('title') or ''}\n"
                    f"Opprettet av: {g.current_user.username}\n"
                    f"Status: needs-triage\n"
                    f"Lenke: {issue['url']}\n\n"
                    f"Prompt:\n{prompt[:500]}"
                ),
            )
            flash("Forespørselen er lagret og sendt til GitHub.", "success")
        except GitHubIssueError as exc:
            db.session.rollback()
            flash(f"GitHub-synk feilet. Ingen lokal sak ble opprettet. {exc}", "error")
        return redirect(url_for("admin.ai_requests"))

    selected_filter = request.args.get("filter", "open")
    if selected_filter not in AI_REQUEST_FILTERS:
        selected_filter = "open"

    try:
        comments_by_request_id, sync_errors = _sync_ai_requests_from_github(g.current_user.id)
        all_requests = AiFixRequest.query.filter(
            AiFixRequest.github_issue_number.isnot(None)
        ).order_by(AiFixRequest.github_issue_updated_at.desc()).all()
    except GitHubIssueError as exc:
        comments_by_request_id = {}
        sync_errors = [str(exc)]
        all_requests = []

    requests = [
        item for item in all_requests
        if _matches_ai_request_filter(item, selected_filter)
    ]
    return render_template(
        "admin_ai_requests.html",
        requests=requests,
        selected_filter=selected_filter,
        filters=AI_REQUEST_FILTERS,
        comments_by_request_id=comments_by_request_id,
        sync_errors=sync_errors,
    )


@admin_bp.route("/admin/ai-requests/<int:request_id>/status", methods=["POST"])
@admin_required
def update_ai_request_status(request_id):
    fix_request = AiFixRequest.query.get_or_404(request_id)
    status = request.form.get("status", "").strip()
    admin_note = request.form.get("admin_note", "").strip()
    if status not in ("new", "in_progress", "done", "rejected"):
        flash("Ugyldig status.", "error")
        return redirect(url_for("admin.ai_requests"))

    fix_request.status = status
    fix_request.admin_note = admin_note or None
    db.session.commit()
    flash("Forespørselen er oppdatert.", "success")
    return redirect(url_for("admin.ai_requests"))


@admin_bp.route("/admin/ai-requests/<int:request_id>/github-status", methods=["POST"])
@admin_required
def sync_ai_request_github_status(request_id):
    fix_request = AiFixRequest.query.get_or_404(request_id)
    try:
        issue = fetch_issue(fix_request.github_issue_number)
        apply_issue_snapshot(fix_request, issue)
        fetch_issue_comments(fix_request.github_issue_number)
        db.session.commit()
        flash("GitHub-status er oppdatert.", "success")
    except GitHubIssueError:
        db.session.delete(fix_request)
        db.session.commit()
        flash("Kunne ikke oppdatere GitHub-status.", "error")
    return redirect(url_for("admin.ai_requests"))


@admin_bp.route("/admin/ai-requests/<int:request_id>/generate-fix", methods=["POST"])
@admin_required
def generate_ai_request_fix(request_id):
    fix_request = AiFixRequest.query.get_or_404(request_id)
    if not fix_request.github_issue_number:
        flash("Forespørselen må først være sendt til GitHub.", "error")
        return redirect(url_for("admin.ai_requests"))

    command = (
        "cd /home/kristian/shanklife_pro && "
        f"nohup /tmp/shanklife_pro_venv/bin/python scripts/ai_fix_worker.py --issue {fix_request.github_issue_number} "
        "--run-codex --push --create-pr >> /tmp/shanklife_pro_ai_worker.log 2>&1 &"
    )
    subprocess.Popen(["bash", "-lc", command], cwd=APP_ROOT)
    fix_request.status = "in_progress"
    db.session.commit()
    flash("Generering av fiks er startet. Synk status om litt for å se når den er klar.", "success")
    return redirect(url_for("admin.ai_requests"))


@admin_bp.route("/admin/ai-requests/<int:request_id>/deploy-fix", methods=["POST"])
@admin_required
def deploy_ai_request_fix(request_id):
    fix_request = AiFixRequest.query.get_or_404(request_id)
    try:
        issue = fetch_issue_for_ai_request(fix_request)
        apply_issue_snapshot(fix_request, issue)
        labels = set(issue.get("labels", []))
        if "ready-to-deploy" not in labels:
            db.session.commit()
            flash("Fiksen er ikke klar for deploy ennå.", "error")
            return redirect(url_for("admin.ai_requests"))

        merge_ready_pull_request_for_ai_request(fix_request)
        fix_request.status = "done"
        refreshed_issue = fetch_issue_for_ai_request(fix_request)
        apply_issue_snapshot(fix_request, refreshed_issue)
        db.session.commit()
    except GitHubIssueError as exc:
        fix_request.github_sync_error = str(exc)
        db.session.commit()
        flash("Kunne ikke deploye fiksen.", "error")
        return redirect(url_for("admin.ai_requests"))

    command = (
        "cd /home/kristian/shanklife_pro && "
        f"nohup /tmp/shanklife_pro_venv/bin/python scripts/deploy_and_notify.py --issue {fix_request.github_issue_number} "
        ">> /tmp/shanklife_pro_admin_deploy.log 2>&1 &"
    )
    subprocess.Popen(["bash", "-lc", command], cwd=APP_ROOT)
    flash("Fiksen er merget, og deploy er startet i bakgrunnen.", "success")
    return redirect(url_for("admin.ai_requests"))


@admin_bp.route("/admin/backup", methods=["POST"])
@admin_required
def backup_database():
    name = request.form.get("backup_name", "").strip()
    try:
        filename = create_backup(name)
    except DatabaseWriteError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.admin_home"))
    flash(f"Backup lagret: {filename}", "success")
    return redirect(url_for("admin.admin_home"))


@admin_bp.route("/admin/restore", methods=["POST"])
@admin_required
def restore_database():
    filename = request.form.get("backup_filename", "").strip()
    try:
        restore_backup(filename)
    except (FileNotFoundError, DatabaseWriteError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.admin_home"))

    session.clear()
    flash("Backup er gjenopprettet. Last siden på nytt hvis noe ser gammelt ut.", "success")
    return redirect(url_for("auth.login"))


@admin_bp.route("/admin/balletour-database-view", methods=["POST"])
@admin_required
def balletour_database_view():
    selected_view = request.form.get("database_view", PROD_DATABASE_VIEW).strip()
    if selected_view == TEST_DATABASE_VIEW and not test_database_exists():
        flash("Testdatabasen finnes ikke ennå. Lag den fra admin-siden først.", "error")
        set_balletour_database_view(PROD_DATABASE_VIEW)
    elif selected_view == TEST_DATABASE_VIEW:
        set_balletour_database_view(TEST_DATABASE_VIEW)
        flash("BalleTour-visning bruker testdatabasen for admin-brukeren din.", "success")
    else:
        set_balletour_database_view(PROD_DATABASE_VIEW)
        flash("BalleTour-visning bruker prod-databasen.", "success")
    return redirect(url_for("admin.admin_home"))


@admin_bp.route("/admin/clear-rounds", methods=["POST"])
@admin_required
def clear_round_data():
    try:
        clear_rounds()
    except (DatabaseWriteError, SQLAlchemyError) as exc:
        flash(f"Kunne ikke nullstille runder: {exc}", "error")
        return redirect(url_for("admin.admin_home"))
    flash("Alle runder, scorer og statistikk er slettet. Baner, spillere og brukere er beholdt.", "success")
    return redirect(url_for("admin.admin_home"))


@admin_bp.route("/admin/clear-balletour-rounds", methods=["POST"])
@admin_required
def clear_balletour_round_data():
    try:
        deleted_count = clear_balletour_rounds()
    except (ValueError, DatabaseWriteError, SQLAlchemyError) as exc:
        flash(f"Kunne ikke nullstille BalleTour-data: {exc}", "error")
        return redirect(url_for("admin.admin_home"))
    flash(
        f"BalleTour-data er nullstilt. {deleted_count} runder med tilhørende data ble slettet.",
        "success",
    )
    return redirect(url_for("admin.admin_home"))


@admin_bp.route("/admin/testdata", methods=["POST"])
@admin_required
def make_testdata():
    try:
        generate_test_rounds(count=50)
    except (ValueError, DatabaseWriteError, SQLAlchemyError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.admin_home"))

    flash("50 test-runder per bruker er laget for Kristian og Erik. Baner og spillere ble beholdt.", "success")
    return redirect(url_for("profile.me"))


@admin_bp.route("/admin/balletour-testdata", methods=["POST"])
@admin_required
def make_balletour_testdata():
    try:
        result = reset_balletour_test_database(rounds_per_player=25)
    except (ValueError, DatabaseWriteError, SQLAlchemyError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.admin_home"))

    flash(
        (
            f"BalleTour-testdatabasen er oppdatert med {result['rounds']} runder "
            f"for hver av {result['players']} spillere. Prod-databasen er ikke endret."
        ),
        "success",
    )
    return redirect(url_for("balletour.index"))


@admin_bp.route("/admin/balletour-testdata/delete", methods=["POST"])
@admin_required
def delete_balletour_testdata():
    deleted = delete_balletour_test_database()
    if deleted:
        flash("BalleTour-testdatabasen er slettet. Prod-databasen er ikke endret.", "success")
    else:
        flash("Det fantes ingen BalleTour-testdatabase å slette.", "error")
    return redirect(url_for("admin.admin_home"))
