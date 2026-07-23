import json
from email.utils import parseaddr

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from extensions import db
from models import GarminRoundSync, Round, RoundPlayer
from routes.auth import login_required
from services.balletour import (
    get_balletour_course_id,
    get_balletour_memberships,
    get_balletour_series,
    is_balletour_player,
)
from services.garmin_golf import garmin_connection_available
from services.golfbox import clear_user_golfbox_credentials, golfbox_connection_summary, save_user_golfbox_credentials
from services.play_formats import MATCHPLAY
from services.round_length import round_holes

profile_bp = Blueprint("profile", __name__)


def _valid_email(value):
    parsed_name, parsed_email = parseaddr(value)
    return not parsed_name and parsed_email == value and "@" in parsed_email and "." in parsed_email.rsplit("@", 1)[-1]


def _selected_balletour_notification_player_ids(user):
    raw_value = (user.balletour_round_notification_player_ids or "").strip()
    if not raw_value:
        return set()
    try:
        values = json.loads(raw_value)
    except json.JSONDecodeError:
        return set()
    return {int(value) for value in values if str(value).isdigit()}


def _exclude_balletour_course(query):
    balletour_course_id = get_balletour_course_id()
    if balletour_course_id:
        return query.filter(Round.course_id != balletour_course_id)
    return query


def _personal_round_players(player):
    query = (
        RoundPlayer.query.filter_by(player_id=player.id)
        .join(Round)
        .order_by(Round.started_at.desc())
    )
    return _exclude_balletour_course(query).all()


def _round_row(round_player):
    round_obj = round_player.round
    holes = round_holes(round_obj)
    scored_entries = [
        entry for entry in round_player.score_entries
        if entry.strokes is not None
    ]
    total = sum(entry.strokes for entry in scored_entries) if scored_entries else None
    par = sum(hole.par for hole in holes)
    completed_score = bool(
        round_obj.status == "finished"
        and total is not None
        and len(scored_entries) == len(holes)
    )
    score_to_par = total - par if completed_score and round_obj.play_format != MATCHPLAY else None
    return {
        "round_player": round_player,
        "round": round_obj,
        "course": round_obj.course,
        "tee_name": round_player.selected_tee.name if round_player.selected_tee else "—",
        "hole_count": len(holes),
        "status_label": "Fullført" if round_obj.status == "finished" else "Pågående",
        "total": total,
        "score_to_par": score_to_par,
        "score_to_par_display": (
            "E" if score_to_par == 0
            else f"{score_to_par:+d}" if score_to_par is not None
            else "—"
        ),
        "garmin_synced": round_obj.garmin_sync is not None,
        "can_send_to_golfbox": (
            round_obj.status == "finished"
            and round_obj.play_format != MATCHPLAY
        ),
    }


def _optional_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@profile_bp.route("/me")
@login_required
def me():
    player = g.current_user.player
    round_players = _personal_round_players(player)
    recent_rounds = [_round_row(round_player) for round_player in round_players[:3]]
    last_garmin_sync = (
        GarminRoundSync.query.filter_by(user_id=g.current_user.id)
        .order_by(GarminRoundSync.synced_at.desc())
        .first()
    )

    return render_template(
        "profile.html",
        player=player,
        recent_rounds=recent_rounds,
        total_round_count=len(round_players),
        golfbox_connection=golfbox_connection_summary(g.current_user),
        garmin_connected=garmin_connection_available(g.current_user),
        last_garmin_sync=last_garmin_sync,
    )


@profile_bp.route("/me/rounds")
@login_required
def my_rounds():
    all_round_players = _personal_round_players(g.current_user.player)

    available_years = sorted(
        {round_player.round.started_at.year for round_player in all_round_players},
        reverse=True,
    )
    available_courses = sorted(
        {
            (round_player.round.course.id, round_player.round.course.name)
            for round_player in all_round_players
        },
        key=lambda item: item[1].lower(),
    )
    available_tees = sorted(
        {
            round_player.selected_tee.name
            for round_player in all_round_players
            if round_player.selected_tee
        },
        key=str.lower,
    )

    filters = {
        "status": request.args.get("status", "").strip(),
        "year": _optional_int(request.args.get("year")),
        "course_id": _optional_int(request.args.get("course_id")),
        "tee": request.args.get("tee", "").strip(),
        "holes": _optional_int(request.args.get("holes")),
        "garmin": request.args.get("garmin", "").strip(),
    }
    if filters["status"] not in ("", "ongoing", "finished"):
        filters["status"] = ""
    if filters["year"] not in available_years:
        filters["year"] = None
    if filters["course_id"] not in {course_id for course_id, _name in available_courses}:
        filters["course_id"] = None
    if filters["tee"] not in available_tees:
        filters["tee"] = ""
    if filters["holes"] not in (9, 18):
        filters["holes"] = None
    if filters["garmin"] not in ("", "synced", "unsynced"):
        filters["garmin"] = ""

    filtered_round_players = []
    for round_player in all_round_players:
        round_obj = round_player.round
        hole_count = len(round_holes(round_obj))
        if filters["status"] and round_obj.status != filters["status"]:
            continue
        if filters["year"] and round_obj.started_at.year != filters["year"]:
            continue
        if filters["course_id"] and round_obj.course_id != filters["course_id"]:
            continue
        tee_name = round_player.selected_tee.name if round_player.selected_tee else ""
        if filters["tee"] and tee_name != filters["tee"]:
            continue
        if filters["holes"] and hole_count != filters["holes"]:
            continue
        is_synced = round_obj.garmin_sync is not None
        if filters["garmin"] == "synced" and not is_synced:
            continue
        if filters["garmin"] == "unsynced" and is_synced:
            continue
        filtered_round_players.append(round_player)

    return render_template(
        "my_rounds.html",
        round_rows=[_round_row(round_player) for round_player in filtered_round_players],
        total_round_count=len(all_round_players),
        filters=filters,
        available_years=available_years,
        available_courses=available_courses,
        available_tees=available_tees,
    )


@profile_bp.route("/me/golfbox", methods=["POST"])
@login_required
def golfbox_settings():
    user = g.current_user
    if request.form.get("action") == "clear":
        clear_user_golfbox_credentials(user)
        db.session.commit()
        flash("GolfBox-innloggingen er fjernet.", "success")
    else:
        username = request.form.get("golfbox_username", "").strip()
        password = request.form.get("golfbox_password", "")
        try:
            identity = save_user_golfbox_credentials(user, username, password)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            db.session.commit()
            player_name = identity.get("player_name") or "GolfBox-brukeren"
            club_name = identity.get("club_name") or "ukjent klubb"
            flash(f"GolfBox er koblet til {player_name} i {club_name}.", "success")
    next_url = request.form.get("next") or url_for("profile.me")
    return redirect(next_url)


@profile_bp.route("/me/notifications", methods=["GET", "POST"])
@login_required
def notification_settings():
    user = g.current_user
    balletour_memberships = get_balletour_memberships() if is_balletour_player(user) else []
    selected_player_ids = _selected_balletour_notification_player_ids(user)

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if email and (len(email) > 255 or not _valid_email(email)):
            flash("Skriv inn en gyldig e-postadresse.", "error")
            return render_template(
                "notification_settings.html",
                user=user,
                series=get_balletour_series(),
                balletour_memberships=balletour_memberships,
                selected_player_ids=selected_player_ids,
                round_notification_mode=request.form.get("round_notification_mode", "all"),
            )

        user.email = email or None
        user.email_notifications_enabled = request.form.get("email_notifications_enabled") == "1"
        user.notify_balletour_round_started = request.form.get("notify_balletour_round_started") == "1"
        user.notify_balletour_round_finished = request.form.get("notify_balletour_round_finished") == "1"
        user.notify_shanklife_round_started = request.form.get("notify_shanklife_round_started") == "1"
        user.notify_shanklife_round_finished = request.form.get("notify_shanklife_round_finished") == "1"
        user.notify_version_updates = request.form.get("notify_version_updates") == "1"
        round_notification_mode = request.form.get("round_notification_mode", "all")
        if round_notification_mode == "selected":
            allowed_player_ids = {membership.player_id for membership in balletour_memberships}
            selected_ids = []
            for raw_player_id in request.form.getlist("balletour_round_player_id"):
                if not raw_player_id.isdigit():
                    continue
                player_id = int(raw_player_id)
                if player_id in allowed_player_ids:
                    selected_ids.append(player_id)
            if not selected_ids:
                flash("Velg minst én BalleTour-spiller, eller velg alle spillere.", "error")
                return render_template(
                    "notification_settings.html",
                    user=user,
                    series=get_balletour_series(),
                    balletour_memberships=balletour_memberships,
                    selected_player_ids=set(),
                    round_notification_mode="selected",
                )
            user.balletour_round_notification_player_ids = json.dumps(sorted(set(selected_ids)))
        else:
            user.balletour_round_notification_player_ids = None
        db.session.commit()

        flash("E-post og varselvalg er lagret.", "success")
        return redirect(url_for("profile.notification_settings"))

    return render_template(
        "notification_settings.html",
        user=user,
        series=get_balletour_series(),
        balletour_memberships=balletour_memberships,
        selected_player_ids=selected_player_ids,
        round_notification_mode="selected" if selected_player_ids else "all",
    )
