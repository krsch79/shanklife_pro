from functools import wraps

import json

from flask import Blueprint, g, jsonify, request, session
from werkzeug.security import check_password_hash

from models import (
    Club,
    Course,
    CourseHole,
    CourseTee,
    CourseTeeLength,
    Player,
    Round,
    ScoreEntry,
    ScoreStat,
    SeriesPlayer,
    User,
)
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
    _send_shanklife_round_finished_mail,
    _send_shanklife_round_started_mail,
    _shanklife_rounds_query,
    _score_options_for_par,
)
from services.round_length import allowed_round_hole_counts, round_holes
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


def _course_summary_payload(course):
    return {
        "id": course.id,
        "name": course.name,
        "hole_count": course.hole_count,
        "par": sum(hole.par for hole in course.holes),
        "supports_nine_hole_round": 9 in allowed_round_hole_counts(course),
        "tees": [
            {
                "id": tee.id,
                "name": tee.name,
                "display_order": tee.display_order,
                "total_length_meters": sum(length.length_meters for length in tee.lengths),
                "ratings": {
                    rating.gender: {
                        "slope": rating.slope,
                        "course_rating": rating.course_rating,
                    }
                    for rating in tee.ratings
                },
            }
            for tee in sorted(course.tees, key=lambda item: item.display_order)
        ],
        "holes": [
            {
                "hole_number": hole.hole_number,
                "par": hole.par,
                "stroke_index": hole.stroke_index,
                "lengths": {
                    str(length.tee_id): length.length_meters
                    for length in hole.tee_lengths
                },
            }
            for hole in sorted(course.holes, key=lambda item: item.hole_number)
        ],
    }


def _player_payload(player, display_order=0):
    return {
        "id": player.id,
        "name": player.name,
        "display_name": player.name,
        "default_hcp": player.default_hcp,
        "gender": player.gender,
        "display_order": display_order,
    }


def _shanklife_setup_payload():
    courses = Course.query.order_by(Course.name.asc()).all()
    players = Player.query.order_by(Player.name.asc()).all()
    return {
        "courses": [_course_summary_payload(course) for course in courses],
        "players": [_player_payload(player, index) for index, player in enumerate(players)],
        "clubs": [
            {
                "id": club.id,
                "name": club.name,
                "sort_order": club.sort_order,
            }
            for club in Club.query.order_by(Club.sort_order.asc(), Club.name.asc()).all()
        ],
        "max_players": 4,
        "drive_distance_options": list(DRIVE_DISTANCE_OPTIONS),
        "putt_options": list(range(0, 6)),
        "last_putt_distance_options": list(LAST_PUTT_DISTANCE_OPTIONS),
    }


def _shanklife_round_detail_payload(round_obj):
    holes = list(round_holes(round_obj))
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

        complete = scored_count == len(holes)
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
            "hole_count": round_obj.played_hole_count or round_obj.course.hole_count,
            "par": course_par,
        },
        "started_at": round_obj.started_at.isoformat() if round_obj.started_at else None,
        "started_at_display": format_server_datetime(round_obj.started_at),
        "finished_at": round_obj.finished_at.isoformat() if round_obj.finished_at else None,
        "finished_at_display": format_server_datetime(round_obj.finished_at) if round_obj.finished_at else None,
        "players": players,
    }


def _shanklife_round_list_item(round_obj):
    payload = _round_payload(round_obj)
    payload["course"] = round_obj.course.name if round_obj.course else "Ukjent bane"
    payload["started_at_display"] = format_server_datetime(round_obj.started_at)
    payload["finished_at_display"] = format_server_datetime(round_obj.finished_at) if round_obj.finished_at else None
    payload["players"] = [
        {
            "id": round_player.player_id,
            "round_player_id": round_player.id,
            "name": round_player.player_name_snapshot,
            "hcp": round_player.hcp_for_round,
            "tee": round_player.selected_tee.name if round_player.selected_tee else None,
            "tracks_stats": bool(round_player.tracks_stats),
            "total_strokes": sum(
                entry.strokes
                for entry in round_player.score_entries
                if entry.strokes is not None
            ) or None,
        }
        for round_player in sorted(round_obj.round_players, key=lambda item: item.id)
    ]
    return payload


def _save_shanklife_hole_payload(round_obj, hole_number, player_payloads):
    if round_obj.status != "ongoing":
        raise ValueError("Runden er allerede fullført.")
    if _is_balletour_round(round_obj):
        raise ValueError("Dette er ikke en Shanklife-runde.")

    hole = next((item for item in round_holes(round_obj) if item.hole_number == hole_number), None)
    if not hole:
        raise ValueError("Fant ikke hullet.")

    round_players = {round_player.id: round_player for round_player in round_obj.round_players}
    stats_players = {
        round_player.id
        for round_player in round_obj.round_players
        if round_player.tracks_stats
    }
    allowed_club_ids = {club.id for club in _club_options_for_round(round_obj)} if stats_players else None

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

        if round_player.id in stats_players:
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


def _create_course_from_payload(data):
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Banenavn må fylles ut.")
    if Course.query.filter(db.func.lower(Course.name) == name.lower()).first():
        raise ValueError("Det finnes allerede en bane med dette navnet.")

    try:
        hole_count = int(data.get("hole_count") or 18)
    except (TypeError, ValueError) as exc:
        raise ValueError("Ugyldig antall hull.") from exc
    if hole_count not in (9, 18):
        raise ValueError("Banen må ha 9 eller 18 hull.")

    holes_payload = data.get("holes") or []
    tees_payload = data.get("tees") or []
    if len(holes_payload) != hole_count:
        raise ValueError(f"Banen må ha {hole_count} hull.")
    if not (1 <= len(tees_payload) <= 6):
        raise ValueError("Banen må ha mellom 1 og 6 tee-sett.")

    seen_indexes = set()
    holes = []
    for index, hole_payload in enumerate(holes_payload, start=1):
        try:
            par = int(hole_payload.get("par"))
            stroke_index = int(hole_payload.get("stroke_index"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Par og index må være gyldige tall for hull {index}.") from exc
        if par < 3 or par > 6:
            raise ValueError(f"Par må være mellom 3 og 6 for hull {index}.")
        if stroke_index < 1 or stroke_index > hole_count:
            raise ValueError(f"Index må være mellom 1 og {hole_count} for hull {index}.")
        if stroke_index in seen_indexes:
            raise ValueError(f"Index {stroke_index} er brukt mer enn én gang.")
        seen_indexes.add(stroke_index)
        holes.append({"hole_number": index, "par": par, "stroke_index": stroke_index})

    tee_names = set()
    tees = []
    for tee_index, tee_payload in enumerate(tees_payload, start=1):
        tee_name = (tee_payload.get("name") or "").strip()
        if not tee_name:
            raise ValueError(f"Navn mangler for tee {tee_index}.")
        if tee_name.lower() in tee_names:
            raise ValueError(f"Tee-navnet '{tee_name}' er brukt mer enn én gang.")
        tee_names.add(tee_name.lower())

        lengths_payload = tee_payload.get("lengths") or {}
        lengths = {}
        for hole_number in range(1, hole_count + 1):
            raw_length = lengths_payload.get(str(hole_number), lengths_payload.get(hole_number))
            try:
                length_meters = int(raw_length)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Lengde må være et heltall for tee '{tee_name}', hull {hole_number}.") from exc
            if length_meters < 50 or length_meters > 650:
                raise ValueError(f"Lengde må være mellom 50 og 650 for tee '{tee_name}', hull {hole_number}.")
            lengths[hole_number] = length_meters
        tees.append({"index": tee_index, "name": tee_name, "lengths": lengths})

    course = Course(name=name, hole_count=hole_count)
    db.session.add(course)
    db.session.flush()

    hole_map = {}
    for hole_data in holes:
        hole = CourseHole(course_id=course.id, **hole_data)
        db.session.add(hole)
        db.session.flush()
        hole_map[hole.hole_number] = hole

    for tee_data in tees:
        tee = CourseTee(course_id=course.id, name=tee_data["name"], display_order=tee_data["index"])
        db.session.add(tee)
        db.session.flush()
        for hole_number, length_meters in tee_data["lengths"].items():
            db.session.add(
                CourseTeeLength(
                    tee_id=tee.id,
                    hole_id=hole_map[hole_number].id,
                    hole_number=hole_number,
                    length_meters=length_meters,
                )
            )

    return course


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
        _shanklife_rounds_query().order_by(Round.started_at.desc())
        .limit(10)
        .all()
    )
    return jsonify({
        "course_count": Course.query.count(),
        "recent_rounds": [_round_payload(round_obj) for round_obj in rounds],
    })


@api_bp.route("/shanklife/setup")
@api_login_required
def shanklife_setup():
    return jsonify(_shanklife_setup_payload())


@api_bp.route("/shanklife/courses")
@api_login_required
def shanklife_courses():
    courses = Course.query.order_by(Course.name.asc()).all()
    return jsonify({"courses": [_course_summary_payload(course) for course in courses]})


@api_bp.route("/shanklife/courses", methods=["POST"])
@api_login_required
def shanklife_create_course():
    data = request.get_json(silent=True) or {}
    try:
        course = _create_course_from_payload(data)
    except ValueError as exc:
        db.session.rollback()
        return _json_error("bad_request", str(exc), 400)

    db.session.commit()
    return jsonify(_course_summary_payload(course)), 201


@api_bp.route("/shanklife/rounds")
@api_login_required
def shanklife_rounds():
    status = request.args.get("status", "all")
    query = _shanklife_rounds_query()
    if status in ("ongoing", "finished"):
        query = query.filter_by(status=status)
    rounds = query.order_by(Round.started_at.desc()).limit(50).all()
    return jsonify({
        "status": status,
        "rounds": [_shanklife_round_list_item(round_obj) for round_obj in rounds],
    })


@api_bp.route("/shanklife/rounds", methods=["POST"])
@api_login_required
def shanklife_create_round():
    data = request.get_json(silent=True) or {}
    try:
        course_id = int(data.get("course_id"))
    except (TypeError, ValueError):
        return _json_error("bad_request", "Du må velge bane.", 400)

    course = Course.query.get(course_id)
    if not course:
        return _json_error("not_found", "Valgt bane finnes ikke.", 404)
    if _balletour_series_or_error() and get_balletour_series().course_id == course.id:
        return _json_error("bad_request", "BalleTour-runder må startes fra BalleTour.", 400)

    try:
        played_hole_count = int(data.get("played_hole_count") or course.hole_count)
    except (TypeError, ValueError):
        return _json_error("bad_request", "Ugyldig valg av antall hull.", 400)
    if played_hole_count not in allowed_round_hole_counts(course):
        return _json_error("bad_request", "Denne banen kan ikke spilles med valgt antall hull.", 400)

    course_tees = {tee.id: tee for tee in course.tees}
    if not course_tees:
        return _json_error("bad_request", "Valgt bane har ingen tees.", 400)

    player_payloads = data.get("players") or []
    if not (1 <= len(player_payloads) <= 4):
        return _json_error("bad_request", "Du må velge mellom 1 og 4 spillere totalt.", 400)

    round_players_payload = []
    seen_names = set()
    try:
        for index, player_payload in enumerate(player_payloads, start=1):
            player = None
            new_name = (player_payload.get("new_player_name") or "").strip()
            if new_name:
                if Player.query.filter(db.func.lower(Player.name) == new_name.lower()).first():
                    raise ValueError(f"Spilleren '{new_name}' finnes allerede.")
                player = Player(name=new_name, default_hcp=_parse_hcp(str(player_payload.get("hcp") or ""), new_name), gender="male")
                db.session.add(player)
                db.session.flush()
            else:
                try:
                    player_id = int(player_payload.get("player_id"))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Ugyldig spiller-valg i slot {index}.") from exc
                player = Player.query.get(player_id)
                if not player:
                    raise ValueError(f"Valgt spiller finnes ikke i slot {index}.")

            player_name = player.name
            if player_name.lower() in seen_names:
                raise ValueError("Du kan ikke ha samme spiller mer enn én gang i samme runde.")
            seen_names.add(player_name.lower())

            hcp = _parse_hcp(str(player_payload.get("hcp") or ""), player_name)
            selected_tee_id = _parse_tee(
                "" if player_payload.get("tee_id") is None else str(player_payload.get("tee_id")),
                course_tees,
                player_name,
            )
            if player.default_hcp != hcp:
                player.default_hcp = hcp

            round_players_payload.append({
                "player": player,
                "player_name": player_name,
                "hcp_for_round": hcp,
                "selected_tee_id": selected_tee_id,
                "tracks_stats": bool(player_payload.get("tracks_stats")),
            })

        round_obj = _create_round(course, round_players_payload, played_hole_count=played_hole_count)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return _json_error("bad_request", str(exc), 400)

    _send_shanklife_round_started_mail(round_obj)
    return jsonify(_shanklife_round_detail_payload(round_obj)), 201


@api_bp.route("/shanklife/rounds/<int:round_id>")
@api_login_required
def shanklife_round_detail(round_id):
    round_obj = _shanklife_rounds_query().filter_by(id=round_id).first()
    if not round_obj:
        return _json_error("not_found", "Fant ikke Shanklife-runden.", 404)
    return jsonify(_shanklife_round_detail_payload(round_obj))


@api_bp.route("/shanklife/rounds/<int:round_id>/holes/<int:hole_number>", methods=["PUT"])
@api_login_required
def shanklife_save_hole(round_id, hole_number):
    round_obj = _shanklife_rounds_query().filter_by(id=round_id).first()
    if not round_obj:
        return _json_error("not_found", "Fant ikke Shanklife-runden.", 404)
    player_payloads = (request.get_json(silent=True) or {}).get("players") or []
    try:
        _save_shanklife_hole_payload(round_obj, hole_number, player_payloads)
    except ValueError as exc:
        db.session.rollback()
        return _json_error("bad_request", str(exc), 400)
    db.session.commit()
    return jsonify(_shanklife_round_detail_payload(round_obj))


@api_bp.route("/shanklife/rounds/<int:round_id>/finish", methods=["POST"])
@api_login_required
def shanklife_finish_round(round_id):
    round_obj = _shanklife_rounds_query().filter_by(id=round_id).first()
    if not round_obj:
        return _json_error("not_found", "Fant ikke Shanklife-runden.", 404)
    if round_obj.status == "finished":
        return jsonify(_shanklife_round_detail_payload(round_obj))

    missing_round_choices = _missing_round_choices(round_obj)
    if missing_round_choices:
        return _json_error(
            "missing_choices",
            "Runden kan ikke fullføres før alle obligatoriske valg er fylt ut.",
            400,
            missing_choices=missing_round_choices,
        )

    round_obj.status = "finished"
    round_obj.finished_at = server_now()
    db.session.commit()
    _send_shanklife_round_finished_mail(round_obj)
    return jsonify(_shanklife_round_detail_payload(round_obj))


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
