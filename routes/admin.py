from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import AiFixRequest
from routes.auth import login_required
from services.admin_tools import (
    DatabaseWriteError,
    create_backup,
    generate_balletour_test_rounds,
    generate_test_rounds,
    list_backups,
    restore_backup,
    clear_balletour_rounds,
    clear_rounds,
)
from services.github_issues import (
    GitHubIssueError,
    apply_issue_snapshot,
    create_issue_for_ai_request,
    fetch_issue_for_ai_request,
)

admin_bp = Blueprint("admin", __name__)


def admin_required(view):
    @login_required
    def wrapped_view(*args, **kwargs):
        if not g.current_user.is_admin:
            flash("Du har ikke tilgang til admin.", "error")
            return redirect(url_for("main.index"))
        return view(*args, **kwargs)

    wrapped_view.__name__ = view.__name__
    return wrapped_view


@admin_bp.route("/admin")
@admin_required
def admin_home():
    return render_template("admin.html", backups=list_backups())


@admin_bp.route("/admin/ai-requests", methods=["GET", "POST"])
@admin_required
def ai_requests():
    if request.method == "POST":
        prompt = request.form.get("prompt", "").strip()
        if not prompt:
            flash("Prompt kan ikke være tom.", "error")
            return redirect(url_for("admin.ai_requests"))

        fix_request = AiFixRequest(
            prompt=prompt,
            created_by_user_id=g.current_user.id,
        )
        db.session.add(fix_request)
        db.session.commit()

        try:
            issue = create_issue_for_ai_request(fix_request)
            apply_issue_snapshot(fix_request, issue)
            db.session.commit()
            flash("Forespørselen er lagret og sendt til GitHub.", "success")
        except GitHubIssueError as exc:
            fix_request.github_sync_error = str(exc)
            db.session.commit()
            flash("Forespørselen er lagret lokalt, men GitHub-synk feilet.", "error")
        return redirect(url_for("admin.ai_requests"))

    requests = AiFixRequest.query.order_by(AiFixRequest.created_at.desc()).all()
    return render_template("admin_ai_requests.html", requests=requests)


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


@admin_bp.route("/admin/ai-requests/<int:request_id>/github-sync", methods=["POST"])
@admin_required
def sync_ai_request_to_github(request_id):
    fix_request = AiFixRequest.query.get_or_404(request_id)
    if fix_request.github_issue_url:
        flash("Forespørselen har allerede et GitHub issue.", "success")
        return redirect(url_for("admin.ai_requests"))

    try:
        issue = create_issue_for_ai_request(fix_request)
        apply_issue_snapshot(fix_request, issue)
        db.session.commit()
        flash("Forespørselen er sendt til GitHub.", "success")
    except GitHubIssueError as exc:
        fix_request.github_sync_error = str(exc)
        db.session.commit()
        flash("GitHub-synk feilet.", "error")
    return redirect(url_for("admin.ai_requests"))


@admin_bp.route("/admin/ai-requests/<int:request_id>/github-status", methods=["POST"])
@admin_required
def sync_ai_request_github_status(request_id):
    fix_request = AiFixRequest.query.get_or_404(request_id)
    try:
        issue = fetch_issue_for_ai_request(fix_request)
        apply_issue_snapshot(fix_request, issue)
        db.session.commit()
        flash("GitHub-status er oppdatert.", "success")
    except GitHubIssueError as exc:
        fix_request.github_sync_error = str(exc)
        db.session.commit()
        flash("Kunne ikke oppdatere GitHub-status.", "error")
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
        count = generate_balletour_test_rounds(count=20)
    except (ValueError, DatabaseWriteError, SQLAlchemyError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.admin_home"))

    flash(f"{count} nye BalleTour-test-runder er laget. Eksisterende BalleTour-runder ble erstattet.", "success")
    return redirect(url_for("balletour.index"))
