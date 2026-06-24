from functools import wraps

import json

from flask import Blueprint, g, jsonify, request, session
from werkzeug.security import check_password_hash

from models import Club, Course, Round, RoundPlayer, ScoreEntry, ScoreStat, SeriesPlayer, User
from extensions import db
from routes.balletour import (
    MAX_BALLETOUR_ROUND_PLAYERS,
    _balletour_all_player_stats,
    _balletour_memberships_with_rounds,
    _balletour_player_stats,
    _player_display_name,
)
from routes.rounds import (
    DRIVE_DISTANCE_OPTIONS,
    LAST_PUTT_DISTANCE_OPTIONS,
    _club_options_for_round,
    _create_round,
    _encode_green_stat,
    _is_balletour_round,
    _missing_round_choices,
    _parse_hcp,
    _parse_score_for_hole,
    _parse_tee,
    _save_score_stat,
    _save_tee_club,
    _score_options_for_par,
)
from services.balletour import BALLETOUR_MENU_LABEL, get_balletour_series, is_balletour_player
from services.balletour import get_balletour_memberships
from services.balletour_mcp import (
    get_balletour_overview as build_balletour_overview,
    get_balletour_player_summary,
    list_balletour_players,
    list_balletour_rounds,
)
from services.tee_filters import selected_tee_key, tee_ids_for_key
from services.time import format_server_datetime, server_now
from services.version import APP_VERSION
from services.weather import fetch_bekkestua_weather, summarize_weather_payload
from routes.balletour import _send_balletour_round_started_mail
from routes.rounds import _send_balletour_round_finished_mail

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
                "tee_club_id": entry.tee_club_id if entry else None,
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


def _balletour_course_setup_payload(series):
    course = series.course
    holes = []
    for hole in course.holes:
        lengths = {
            str(length.tee_id): length.length_meters
            for length in hole.tee_lengths
        }
        holes.append({
            "hole_number": hole.hole_number,
            "par": hole.par,
            "stroke_index": hole.stroke_index,
            "lengths": lengths,
            "score_options": _score_options_for_par(hole.par),
        })

    return {
        "course": {
            "id": course.id,
            "name": course.name,
            "hole_count": course.hole_count,
            "par": sum(hole.par for hole in course.holes),
        },
        "holes": holes,
        "tees": [
            {
                "id": tee.id,
                "name": tee.name,
                "display_order": tee.display_order,
                "total_length_meters": sum(length.length_meters for length in tee.lengths),
            }
            for tee in course.tees
        ],
        "players": [
            {
                "id": membership.player.id,
                "name": membership.player.name,
                "display_name": _player_display_name(membership.player),
                "default_hcp": membership.player.default_hcp,
                "gender": membership.player.gender,
                "display_order": membership.display_order,
            }
            for membership in get_balletour_memberships()
        ],
        "clubs": [
            {
                "id": club.id,
                "name": club.name,
                "sort_order": club.sort_order,
            }
            for club in Club.query.filter(Club.sort_order >= 1).order_by(Club.sort_order.asc(), Club.name.asc()).all()
        ],
        "max_players": MAX_BALLETOUR_ROUND_PLAYERS,
        "drive_distance_options": list(DRIVE_DISTANCE_OPTIONS),
        "putt_options": list(range(0, 6)),
        "last_putt_distance_options": list(LAST_PUTT_DISTANCE_OPTIONS),
    }


def _json_error(code, message, status=400, **extra):
    payload = {"error": {"code": code, "message": message}}
    payload.update(extra)
    return jsonify(payload), status


def _normalize_green_payload(raw):
    raw = raw or {}
    status = (raw.get("status") or "hit").strip()
    directions = raw.get("directions") or []
    if isinstance(directions, str):
        directions = [directions]
    return _encode_green_stat(status, directions)


def _save_balletour_hole_payload(round_obj, hole_number, player_payloads):
    if round_obj.status != "ongoing":
        raise ValueError("Runden er allerede fullført.")
    if not _is_balletour_round(round_obj):
        raise ValueError("Dette er ikke en BalleTour-runde.")

    hole = next((item for item in round_obj.course.holes if item.hole_number == hole_number), None)
    if not hole:
        raise ValueError("Fant ikke hullet.")

    round_players = {round_player.id: round_player for round_player in round_obj.round_players}
    allowed_club_ids = {club.id for club in _club_options_for_round(round_obj)}

    for player_payload in player_payloads:
        try:
            round_player_id = int(player_payload.get("round_player_id"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Ugyldig spiller i scoredata.") from exc

        round_player = round_players.get(round_player_id)
        if not round_player:
            raise ValueError("Fant ikke spiller i runden.")

        entry = ScoreEntry.query.filter_by(
            round_id=round_obj.id,
            round_player_id=round_player.id,
            hole_number=hole_number,
        ).first()
        if not entry:
            raise ValueError(f"Fant ikke scorelinje for {round_player.player_name_snapshot}.")

        entry.strokes = _parse_score_for_hole(
            "" if player_payload.get("strokes") is None else str(player_payload.get("strokes")),
            hole,
            round_player.player_name_snapshot,
        )
        _save_tee_club(
            entry,
            "" if player_payload.get("tee_club_id") is None else str(player_payload.get("tee_club_id")),
            round_player.player_name_snapshot,
            allowed_club_ids,
        )

        fairway_result = (
            _normalize_green_payload(player_payload.get("green"))
            if hole.par == 3
            else (player_payload.get("fairway_result") or "")
        )
        _save_score_stat(
            entry,
            hole,
            "" if player_payload.get("drive_distance_m") is None else str(player_payload.get("drive_distance_m")),
            fairway_result,
            "" if player_payload.get("putts") is None else str(player_payload.get("putts")),
            "" if player_payload.get("last_putt_distance_m") is None else str(player_payload.get("last_putt_distance_m")),
        )


def _player_stats_payload(stats):
    selected_player = stats.get("selected_player")
    return {
        "selected_player": {
            "id": selected_player.id,
            "name": selected_player.name,
            "display_name": _player_display_name(selected_player),
            "default_hcp": selected_player.default_hcp,
        } if selected_player else None,
        "selected_hole_number": stats.get("selected_hole_number"),
        "round_count": stats.get("round_count"),
        "completed_round_count": stats.get("completed_round_count"),
        "avg_round": stats.get("avg_round"),
        "best_round": stats.get("best_round"),
        "best_round_vs_par": stats.get("best_round_vs_par"),
        "scored_holes": stats.get("scored_holes"),
        "birdies_or_better": stats.get("birdies_or_better"),
        "pars": stats.get("pars"),
        "bogeys_or_worse": stats.get("bogeys_or_worse"),
        "green_attempts": stats.get("green_attempts"),
        "green_hit_percent": stats.get("green_hit_percent"),
        "bunker_percent": stats.get("bunker_percent"),
        "sand_save_attempts": stats.get("sand_save_attempts"),
        "sand_saves": stats.get("sand_saves"),
        "sand_save_percent": stats.get("sand_save_percent"),
        "avg_putts": stats.get("avg_putts"),
        "avg_last_putt_distance": stats.get("avg_last_putt_distance"),
        "avg_putt_meters_per_round": stats.get("avg_putt_meters_per_round"),
        "strokes_gained": stats.get("strokes_gained"),
        "green_points": stats.get("green_points"),
        "green_distribution": stats.get("green_distribution"),
        "best_by_hole": {
            str(hole_number): score
            for hole_number, score in (stats.get("best_by_hole") or {}).items()
        },
        "club_rows": stats.get("club_rows"),
    }


def _all_stats_row_payload(row):
    player = row["player"]
    return {
        "player": {
            "id": player.id,
            "name": player.name,
            "display_name": _player_display_name(player),
            "default_hcp": player.default_hcp,
        },
        "completed_round_count": row.get("completed_round_count"),
        "avg_round": row.get("avg_round"),
        "best_round": row.get("best_round"),
        "green_hit_percent": row.get("green_hit_percent"),
        "bunker_percent": row.get("bunker_percent"),
        "sand_save_percent": row.get("sand_save_percent"),
        "avg_putts": row.get("avg_putts"),
        "avg_last_putt_distance": row.get("avg_last_putt_distance"),
        "avg_putt_meters_per_round": row.get("avg_putt_meters_per_round"),
        "birdies_or_better": row.get("birdies_or_better"),
        "pars": row.get("pars"),
        "bogeys_or_worse": row.get("bogeys_or_worse"),
        "strokes_gained": row.get("strokes_gained"),
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


@api_bp.route("/balletour/round-setup")
@api_login_required
def balletour_round_setup():
    forbidden = _require_balletour_access()
    if forbidden:
        return forbidden

    series = _balletour_series_or_error()
    if not series:
        return _json_error("not_found", "Fant ikke BalleTour-serien.", 404)

    payload = _balletour_course_setup_payload(series)
    try:
        weather_payload = fetch_bekkestua_weather()
    except Exception:
        weather_payload = None
    payload["weather_summary"] = summarize_weather_payload(weather_payload)
    return jsonify(payload)


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


@api_bp.route("/balletour/rounds", methods=["POST"])
@api_login_required
def balletour_create_round():
    forbidden = _require_balletour_access()
    if forbidden:
        return forbidden

    series = _balletour_series_or_error()
    if not series:
        return _json_error("not_found", "Fant ikke BalleTour-serien.", 404)

    data = request.get_json(silent=True) or {}
    player_payloads = data.get("players") or []
    if not (1 <= len(player_payloads) <= MAX_BALLETOUR_ROUND_PLAYERS):
        return _json_error("bad_request", "Velg mellom 1 og 4 BalleTour-spillere.")

    memberships = get_balletour_memberships()
    allowed_players = {membership.player_id: membership.player for membership in memberships}
    course_tees = {tee.id: tee for tee in series.course.tees}
    round_players_payload = []
    seen_player_ids = set()

    for player_payload in player_payloads:
        try:
            player_id = int(player_payload.get("player_id"))
        except (TypeError, ValueError):
            return _json_error("bad_request", "Ugyldig spiller-valg.")

        if player_id in seen_player_ids:
            return _json_error("bad_request", "Du kan ikke ha samme spiller mer enn én gang i samme runde.")
        seen_player_ids.add(player_id)

        player = allowed_players.get(player_id)
        if not player:
            return _json_error("forbidden", "Du kan bare velge BalleTour-spillere.", 403)

        try:
            hcp = _parse_hcp(str(player_payload.get("hcp", "")).strip(), player.name)
            tee_id = _parse_tee(str(player_payload.get("tee_id", "")).strip(), course_tees, player.name)
        except ValueError as exc:
            return _json_error("bad_request", str(exc))

        round_players_payload.append({
            "player": player,
            "player_name": player.name,
            "hcp_for_round": hcp,
            "selected_tee_id": tee_id,
        })
        if hcp != player.default_hcp:
            player.default_hcp = hcp

    if g.current_user.player_id not in seen_player_ids:
        return _json_error("bad_request", "Du må være med i runden du starter.")

    round_obj = _create_round(series.course, round_players_payload, stats_user_id=g.current_user.id)
    try:
        weather_payload = fetch_bekkestua_weather(round_obj.started_at)
        round_obj.weather_json = json.dumps(weather_payload, ensure_ascii=True)
    except Exception:
        round_obj.weather_json = None

    db.session.commit()
    _send_balletour_round_started_mail(round_obj)
    return jsonify(_balletour_round_detail_payload(round_obj)), 201


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


@api_bp.route("/balletour/rounds/<int:round_id>/holes/<int:hole_number>", methods=["PUT"])
@api_login_required
def balletour_save_hole(round_id, hole_number):
    forbidden = _require_balletour_access()
    if forbidden:
        return forbidden

    series = _balletour_series_or_error()
    if not series:
        return _json_error("not_found", "Fant ikke BalleTour-serien.", 404)

    round_obj = Round.query.filter_by(id=round_id, course_id=series.course_id).first()
    if not round_obj:
        return _json_error("not_found", "Fant ikke BalleTour-runden.", 404)

    data = request.get_json(silent=True) or {}
    player_payloads = data.get("players") or []
    if not player_payloads:
        return _json_error("bad_request", "Ingen scoredata sendt.")

    try:
        _save_balletour_hole_payload(round_obj, hole_number, player_payloads)
    except ValueError as exc:
        return _json_error("bad_request", str(exc))

    db.session.commit()
    return jsonify(_balletour_round_detail_payload(round_obj))


@api_bp.route("/balletour/rounds/<int:round_id>/finish", methods=["POST"])
@api_login_required
def balletour_finish_round(round_id):
    forbidden = _require_balletour_access()
    if forbidden:
        return forbidden

    series = _balletour_series_or_error()
    if not series:
        return _json_error("not_found", "Fant ikke BalleTour-serien.", 404)

    round_obj = Round.query.filter_by(id=round_id, course_id=series.course_id).first()
    if not round_obj:
        return _json_error("not_found", "Fant ikke BalleTour-runden.", 404)
    if round_obj.status != "ongoing":
        return jsonify(_balletour_round_detail_payload(round_obj))

    missing_round_choices = _missing_round_choices(round_obj)
    if missing_round_choices:
        db.session.commit()
        return _json_error(
            "missing_choices",
            "Runden kan ikke fullføres før alle hull og obligatoriske felt er fylt ut.",
            400,
            missing=missing_round_choices,
        )

    round_obj.status = "finished"
    round_obj.finished_at = server_now()
    db.session.commit()
    _send_balletour_round_finished_mail(round_obj)
    return jsonify(_balletour_round_detail_payload(round_obj))


@api_bp.route("/balletour/stats")
@api_login_required
def balletour_stats():
    forbidden = _require_balletour_access()
    if forbidden:
        return forbidden

    series = _balletour_series_or_error()
    if not series:
        return _json_error("not_found", "Fant ikke BalleTour-serien.", 404)

    tee_key = selected_tee_key(request.args.get("tee"))
    tee_ids = tee_ids_for_key(series.course, tee_key)
    memberships_with_rounds = _balletour_memberships_with_rounds(
        series,
        get_balletour_memberships(),
        tee_ids,
        statuses=("finished",),
    )
    players = [membership.player for membership in memberships_with_rounds]
    player_by_id = {player.id: player for player in players}

    selected_player = None
    player_id_raw = request.args.get("player_id", "").strip()
    if player_id_raw:
        try:
            selected_player = player_by_id.get(int(player_id_raw))
        except ValueError:
            selected_player = None
    if not selected_player:
        selected_player = player_by_id.get(g.current_user.player_id)
    if not selected_player and players:
        selected_player = players[0]

    selected_hole_number = None
    hole_raw = request.args.get("hole", "").strip()
    if hole_raw:
        try:
            candidate_hole = int(hole_raw)
        except ValueError:
            candidate_hole = None
        if candidate_hole and any(hole.hole_number == candidate_hole for hole in series.course.holes):
            selected_hole_number = candidate_hole

    stats = _balletour_player_stats(series, memberships_with_rounds, selected_player, selected_hole_number, tee_ids)
    return jsonify({
        "tee": tee_key,
        "players": [
            {
                "id": player.id,
                "name": player.name,
                "display_name": _player_display_name(player),
                "default_hcp": player.default_hcp,
            }
            for player in players
        ],
        "stats": _player_stats_payload(stats),
    })


@api_bp.route("/balletour/stats/all")
@api_login_required
def balletour_all_stats():
    forbidden = _require_balletour_access()
    if forbidden:
        return forbidden

    series = _balletour_series_or_error()
    if not series:
        return _json_error("not_found", "Fant ikke BalleTour-serien.", 404)

    tee_key = selected_tee_key(request.args.get("tee"))
    tee_ids = tee_ids_for_key(series.course, tee_key)
    memberships_with_rounds = _balletour_memberships_with_rounds(
        series,
        get_balletour_memberships(),
        tee_ids,
        statuses=("finished",),
    )
    rows = _balletour_all_player_stats(series, memberships_with_rounds, tee_ids)
    return jsonify({
        "tee": tee_key,
        "rows": [_all_stats_row_payload(row) for row in rows],
    })
