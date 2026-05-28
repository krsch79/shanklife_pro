import json
from email.utils import parseaddr

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from extensions import db
from models import CourseHole, Round, RoundPlayer, ScoreEntry, ScoreStat
from routes.auth import login_required
from services.balletour import (
    get_balletour_course_id,
    get_balletour_memberships,
    get_balletour_series,
    is_balletour_player,
)
from services.golfbox import clear_user_golfbox_credentials, golfbox_connection_summary, save_user_golfbox_credentials
from services.tee_filters import round_player_matches_tee, selected_tee_key, tee_filter_options

profile_bp = Blueprint("profile", __name__)


def _percent(numerator, denominator):
    if denominator == 0:
        return None
    return round((numerator / denominator) * 100, 1)


def _avg(values):
    if not values:
        return None
    return round(sum(values) / len(values), 2)


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


@profile_bp.route("/me")
@login_required
def me():
    player = g.current_user.player
    tee_key = selected_tee_key(request.args.get("tee"))
    round_player_query = (
        RoundPlayer.query.filter_by(player_id=player.id)
        .join(Round)
        .order_by(Round.started_at.desc())
    )
    round_players = _exclude_balletour_course(round_player_query).all()
    round_players = [
        round_player for round_player in round_players
        if round_player_matches_tee(round_player, tee_key)
    ]

    rounds_played = len(round_players)
    finished_rounds = [rp for rp in round_players if rp.round.status == "finished"]

    completed_round_totals = []
    scores_by_par = {3: [], 4: [], 5: []}
    gir_hits = 0
    gir_attempts = 0

    for round_player in round_players:
        entries = [entry for entry in round_player.score_entries if entry.strokes is not None]
        if round_player.round.status == "finished" and entries:
            completed_round_totals.append(sum(entry.strokes for entry in entries))

    score_rows = (
        ScoreEntry.query.join(RoundPlayer, ScoreEntry.round_player_id == RoundPlayer.id)
        .join(Round, ScoreEntry.round_id == Round.id)
        .join(
            CourseHole,
            (CourseHole.course_id == Round.course_id)
            & (CourseHole.hole_number == ScoreEntry.hole_number),
        )
        .outerjoin(ScoreStat, ScoreStat.score_entry_id == ScoreEntry.id)
        .filter(RoundPlayer.player_id == player.id)
        .filter(RoundPlayer.id.in_([round_player.id for round_player in round_players]))
        .filter(ScoreEntry.strokes.isnot(None))
        .with_entities(
            ScoreEntry.strokes,
            CourseHole.par,
            ScoreStat.putts,
        )
        .all()
    )

    for strokes, par, putts in score_rows:
        if par in scores_by_par:
            scores_by_par[par].append(strokes)
        if putts is not None:
            gir_attempts += 1
            if strokes - putts <= par - 2:
                gir_hits += 1

    stats_rows = (
        ScoreStat.query.join(ScoreEntry)
        .join(RoundPlayer, ScoreEntry.round_player_id == RoundPlayer.id)
        .filter(RoundPlayer.player_id == player.id)
        .filter(RoundPlayer.id.in_([round_player.id for round_player in round_players]))
        .all()
    )

    drive_distances = [row.drive_distance_m for row in stats_rows if row.drive_distance_m is not None]
    putts = [row.putts for row in stats_rows if row.putts is not None]
    fairway_attempts = [
        row for row in stats_rows
        if row.drive_distance_m is not None and row.fairway_result in ("hit", "left", "right")
    ]
    fairway_hits = [row for row in fairway_attempts if row.fairway_result == "hit"]
    fairway_left = [row for row in fairway_attempts if row.fairway_result == "left"]
    fairway_right = [row for row in fairway_attempts if row.fairway_result == "right"]

    heatmap_points = []
    for index, row in enumerate(fairway_attempts[-120:]):
        distance = row.drive_distance_m or 220
        y_pos = 88 - max(0, min(1, distance / 400)) * 70
        lane_base = {"left": 39, "hit": 50, "right": 61}.get(row.fairway_result, 50)
        jitter = ((index * 37) % 9) - 4
        heatmap_points.append(
            {
                "result": row.fairway_result,
                "x": max(30, min(70, lane_base + jitter)),
                "y": round(y_pos, 1),
            }
        )

    fairway_summary = {
        "attempts": len(fairway_attempts),
        "hit_percent": _percent(len(fairway_hits), len(fairway_attempts)),
        "left_percent": _percent(len(fairway_left), len(fairway_attempts)),
        "right_percent": _percent(len(fairway_right), len(fairway_attempts)),
        "heatmap_points": heatmap_points,
    }

    summary = {
        "rounds_played": rounds_played,
        "finished_rounds": len(finished_rounds),
        "avg_round_score": round(sum(completed_round_totals) / len(completed_round_totals), 1) if completed_round_totals else None,
        "tracked_holes": len(stats_rows),
        "avg_drive_distance": round(sum(drive_distances) / len(drive_distances), 1) if drive_distances else None,
        "fairway_hit_percent": _percent(len(fairway_hits), len(fairway_attempts)),
        "avg_putts": round(sum(putts) / len(putts), 2) if putts else None,
        "avg_par_3": _avg(scores_by_par[3]),
        "avg_par_4": _avg(scores_by_par[4]),
        "avg_par_5": _avg(scores_by_par[5]),
        "gir_percent": _percent(gir_hits, gir_attempts),
        "gir_hits": gir_hits,
        "gir_attempts": gir_attempts,
    }

    return render_template(
        "profile.html",
        player=player,
        round_players=round_players,
        summary=summary,
        fairway_summary=fairway_summary,
        tee_options=tee_filter_options(),
        selected_tee_key=tee_key,
        golfbox_connection=golfbox_connection_summary(g.current_user),
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
