from functools import wraps

from flask import Blueprint, g, jsonify, request, session
from werkzeug.security import check_password_hash

from models import Course, Round, RoundPlayer, ScoreEntry, ScoreStat, SeriesPlayer, User
from services.balletour import BALLETOUR_MENU_LABEL, get_balletour_series, is_balletour_player
from services.balletour_mcp import (
    get_balletour_overview as build_balletour_overview,
    get_balletour_player_summary,
    list_balletour_players,
    list_balletour_rounds,
)
from services.tee_filters import selected_tee_key, tee_ids_for_key
from services.time import format_server_datetime
from services.version import APP_VERSION

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def _user_payload(user):
    player = user.player if user else None
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_admin": bool(user.is_admin),
        "player": {
            "id": player.id,
            "name": player.name,
            "gender": player.gender,
            "default_hcp": player.default_hcp,
            "profile_image_url": f"/uploads/{player.profile_image_filename}" if player.profile_image_filename else None,
        } if player else None,
        "products": {
            "shanklife": True,
            "balletour": is_balletour_player(user),
        },
    }


def _round_payload(round_obj):
    return {
        "id": round_obj.id,
        "status": round_obj.status,
        "started_at": round_obj.started_at.isoformat() if round_obj.started_at else None,
        "finished_at": round_obj.finished_at.isoformat() if round_obj.finished_at else None,
        "played_hole_count": round_obj.played_hole_count,
        "course": {
            "id": round_obj.course.id,
            "name": round_obj.course.name,
            "hole_count": round_obj.course.hole_count,
        } if round_obj.course else None,
        "players": [
            {
                "id": round_player.player_id,
                "name": round_player.player_name_snapshot,
                "hcp": round_player.hcp_for_round,
                "tracks_stats": bool(round_player.tracks_stats),
            }
            for round_player in round_obj.round_players
        ],
    }


def _require_balletour_access():
    if not is_balletour_player(g.current_user):
        return jsonify({"error": {"code": "forbidden", "message": "Denne brukeren har ikke BalleTour-tilgang."}}), 403
    return None


def _score_vs_par_display(value):
    if value is None:
        return "-"
    if value == 0:
        return "E"
    return f"+{value}" if value > 0 else str(value)


def _balletour_series_or_error():
    series = get_balletour_series()
    if not series or not series.course:
        return None
    return series


def _balletour_tee_options(course):
    options = [{"key": "all", "label": "Alle"}]
    for tee in course.tees:
        name = tee.name or ""
        key = "gul" if "gul" in name.lower() else "rod" if "rød" in name.lower() or "rod" in name.lower() else str(tee.id)
        if not any(option["key"] == key for option in options):
            options.append({"key": key, "label": name})
    return options


def _balletour_round_detail_payload(round_obj):
    holes = list(round_obj.course.holes)
    par_by_hole = {hole.hole_number: hole.par for hole in holes}
    length_by_tee = {
        tee.id: {length.hole_number: length.length_meters for length in tee.lengths}
        for tee in round_obj.course.tees
    }
    round_player_ids = [round_player.id for round_player in round_obj.round_players]
    stats_by_entry = {
        stat.score_entry_id: stat
        for stat in ScoreStat.query.join(ScoreEntry)
        .filter(ScoreEntry.round_player_id.in_(round_player_ids))
        .all()
    } if round_player_ids else {}

    course_par = sum(hole.par for hole in holes)
    players = []
    for round_player in sorted(round_obj.round_players, key=lambda item: item.id):
        entries = {entry.hole_number: entry for entry in round_player.score_entries}
        scores = []
        total = 0
        scored_count = 0
        for hole in holes:
            entry = entries.get(hole.hole_number)
            stat = stats_by_entry.get(entry.id) if entry else None
            strokes = entry.strokes if entry else None
            if strokes is not None:
                total += strokes
                scored_count += 1
            scores.append({
                "hole_number": hole.hole_number,
                "par": hole.par,
                "stroke_index": hole.stroke_index,
                "length_meters": length_by_tee.get(round_player.selected_tee_id, {}).get(hole.hole_number),
                "strokes": strokes,
                "to_par": strokes - hole.par if strokes is not None else None,
                "tee_club": entry.tee_club.name if entry and entry.tee_club else None,
                "drive_distance_m": stat.drive_distance_m if stat else None,
                "green_result": stat.fairway_result if stat else None,
                "putts": stat.putts if stat else None,
                "last_putt_distance_m": stat.last_putt_distance_m if stat else None,
            })

        complete = scored_count == round_obj.course.hole_count
        players.append({
            "id": round_player.player_id,
            "round_player_id": round_player.id,
            "name": round_player.player_name_snapshot,
            "hcp": round_player.hcp_for_round,
            "tee": round_player.selected_tee.name if round_player.selected_tee else None,
            "tracks_stats": bool(round_player.tracks_stats),
            "completed_holes": scored_count,
            "total_strokes": total if scored_count else None,
            "to_par": total - course_par if complete else None,
            "to_par_display": _score_vs_par_display(total - course_par) if complete else "-",
            "scores": scores,
        })

    return {
        "id": round_obj.id,
        "status": round_obj.status,
        "course": {
            "id": round_obj.course.id,
            "name": round_obj.course.name,
            "hole_count": round_obj.course.hole_count,
            "par": course_par,
        },
        "started_at": round_obj.started_at.isoformat() if round_obj.started_at else None,
        "started_at_display": format_server_datetime(round_obj.started_at),
        "finished_at": round_obj.finished_at.isoformat() if round_obj.finished_at else None,
        "finished_at_display": format_server_datetime(round_obj.finished_at) if round_obj.finished_at else None,
        "players": players,
    }


def api_login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not g.get("current_user"):
            return jsonify({"error": {"code": "unauthorized", "message": "Du må logge inn først."}}), 401
        return view(*args, **kwargs)

    return wrapped_view


@api_bp.route("/health")
def health():
    return jsonify({"status": "ok", "version": APP_VERSION})


@api_bp.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": {"code": "invalid_credentials", "message": "Feil brukernavn eller passord."}}), 401

    session.clear()
    session["user_id"] = user.id
    return jsonify({"user": _user_payload(user)})


@api_bp.route("/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "logged_out"})


@api_bp.route("/auth/me")
@api_login_required
def me():
    return jsonify({"user": _user_payload(g.current_user)})


@api_bp.route("/bootstrap")
@api_login_required
def bootstrap():
    return jsonify({
        "version": APP_VERSION,
        "user": _user_payload(g.current_user),
        "products": [
            {
                "id": "shanklife",
                "name": "Shanklife Pro",
                "enabled": True,
                "navigation": [
                    {"id": "rounds", "title": "Runder"},
                    {"id": "stats", "title": "Statistikk"},
                    {"id": "courses", "title": "Baner"},
                    {"id": "profile", "title": "Profil"},
                ],
            },
            {
                "id": "balletour",
                "name": BALLETOUR_MENU_LABEL,
                "enabled": is_balletour_player(g.current_user),
                "navigation": [
                    {"id": "rounds", "title": "Runder"},
                    {"id": "leaderboard", "title": "Live"},
                    {"id": "stats", "title": "Statistikk"},
                    {"id": "players", "title": "Spillere"},
                ],
            },
        ],
    })


@api_bp.route("/shanklife/overview")
@api_login_required
def shanklife_overview():
    rounds = (
        Round.query.order_by(Round.started_at.desc())
        .limit(10)
        .all()
    )
    return jsonify({
        "course_count": Course.query.count(),
        "recent_rounds": [_round_payload(round_obj) for round_obj in rounds],
    })


@api_bp.route("/balletour/overview")
@api_login_required
def balletour_overview():
    forbidden = _require_balletour_access()
    if forbidden:
        return forbidden

    tee = selected_tee_key(request.args.get("tee"))
    try:
        payload = build_balletour_overview(tee=tee)
    except ValueError as exc:
        return jsonify({"error": {"code": "not_found", "message": str(exc)}}), 404

    series = _balletour_series_or_error()
    payload["enabled"] = True
    payload["tee_options"] = _balletour_tee_options(series.course) if series else []
    return jsonify(payload)


@api_bp.route("/balletour/players")
@api_login_required
def balletour_players():
    forbidden = _require_balletour_access()
    if forbidden:
        return forbidden

    try:
        return jsonify(list_balletour_players())
    except ValueError as exc:
        return jsonify({"error": {"code": "not_found", "message": str(exc)}}), 404


@api_bp.route("/balletour/players/<int:player_id>/summary")
@api_login_required
def balletour_player_summary(player_id):
    forbidden = _require_balletour_access()
    if forbidden:
        return forbidden

    series = _balletour_series_or_error()
    if not series:
        return jsonify({"error": {"code": "not_found", "message": "Fant ikke BalleTour-serien."}}), 404

    membership = SeriesPlayer.query.filter_by(series_id=series.id, player_id=player_id).first()
    if not membership:
        return jsonify({"error": {"code": "not_found", "message": "Fant ikke BalleTour-spilleren."}}), 404

    tee = selected_tee_key(request.args.get("tee"))
    try:
        return jsonify(get_balletour_player_summary(membership.player.name, tee=tee))
    except ValueError as exc:
        return jsonify({"error": {"code": "not_found", "message": str(exc)}}), 404


@api_bp.route("/balletour/me")
@api_login_required
def balletour_me():
    forbidden = _require_balletour_access()
    if forbidden:
        return forbidden

    player = g.current_user.player
    if not player:
        return jsonify({"error": {"code": "not_found", "message": "Brukeren mangler spillerprofil."}}), 404

    tee = selected_tee_key(request.args.get("tee"))
    try:
        return jsonify(get_balletour_player_summary(player.name, tee=tee))
    except ValueError as exc:
        return jsonify({"error": {"code": "not_found", "message": str(exc)}}), 404


@api_bp.route("/balletour/rounds")
@api_login_required
def balletour_rounds():
    forbidden = _require_balletour_access()
    if forbidden:
        return forbidden

    tee = selected_tee_key(request.args.get("tee"))
    status = request.args.get("status", "finished")
    limit = request.args.get("limit", 25)
    player_name = request.args.get("player_name")
    try:
        return jsonify(list_balletour_rounds(status=status, player_name=player_name, limit=limit, tee=tee))
    except ValueError as exc:
        return jsonify({"error": {"code": "bad_request", "message": str(exc)}}), 400


@api_bp.route("/balletour/rounds/<int:round_id>")
@api_login_required
def balletour_round_detail(round_id):
    forbidden = _require_balletour_access()
    if forbidden:
        return forbidden

    series = _balletour_series_or_error()
    if not series:
        return jsonify({"error": {"code": "not_found", "message": "Fant ikke BalleTour-serien."}}), 404

    round_obj = Round.query.filter_by(id=round_id, course_id=series.course_id).first()
    if not round_obj:
        return jsonify({"error": {"code": "not_found", "message": "Fant ikke BalleTour-runden."}}), 404

    return jsonify(_balletour_round_detail_payload(round_obj))
