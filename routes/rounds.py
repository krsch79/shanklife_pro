import json
from pathlib import Path
from secrets import token_hex

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for, jsonify
from sqlalchemy import func
from sqlalchemy.orm import aliased
from werkzeug.utils import secure_filename

from extensions import db
from models import (
    Club,
    Course,
    CourseHole,
    CourseTeeLength,
    Player,
    PlayerHoleDefaultClub,
    Round,
    RoundImage,
    RoundImageTag,
    RoundPlayer,
    ScoreEntry,
    ScoreStat,
    ShotMeasurement,
)
from routes.auth import login_required
from services.handicap import calculate_playing_handicap_for_course, received_strokes_for_round, strokes_received_for_hole
from services.live_score import score_to_par_for_entries
from services.round_completion import missing_saved_entry_choices, validate_score_putts
from services.round_length import (
    allowed_round_hole_counts,
    course_supports_nine_hole_round,
    round_handicap_stroke_index,
    round_hole_count,
    round_holes,
)
from services.round_summary import build_round_summary
from services.balletour import get_balletour_course_id, get_balletour_memberships, get_balletour_series
from services.physical_holes import physical_hole_filter_values, physical_hole_label
from services.play_formats import (
    MATCHPLAY,
    MATCHPLAY_HOLE_RESULT_LABELS,
    MATCHPLAY_HOLE_RESULTS,
    PLAY_FORMAT_LABELS,
    STROKE_PLAY,
    is_matchplay_round,
    normalize_play_format,
)
from services.shot_measurements import parse_shot_measurements
from services.time import format_server_datetime, server_now
from services.user_notifications import (
    send_balletour_round_finished_notifications,
    send_shanklife_round_finished_notifications,
    send_shanklife_round_started_notifications,
)
from services.weather import summarize_weather_payload

rounds_bp = Blueprint("rounds", __name__)

ALLOWED_ROUND_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
GREEN_DIRECTIONS = ("pin", "long", "short", "left", "right")
LAST_PUTT_DISTANCE_OPTIONS = tuple(round(value / 10, 1) for value in range(1, 151))
DEFAULT_LAST_PUTT_DISTANCE = 0.5
LAST_PUTT_METER_OPTIONS = tuple(range(0, 16))
LAST_PUTT_DECIMETER_OPTIONS = tuple(range(0, 10))
DRIVE_DISTANCE_OPTIONS = tuple(range(25, 401, 5))


def _normalize_image_tags(raw_tags):
    tags = []
    seen = set()
    for raw_tag in (raw_tags or "").replace("\n", ",").replace(";", ",").split(","):
        tag = " ".join(raw_tag.strip().strip("#").split())
        if not tag:
            continue
        if len(tag) > 80:
            raise ValueError("Tag kan maks være 80 tegn.")
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            tags.append(tag)
    return tags


def _round_image_tag_choices(round_obj):
    balletour_round = _is_balletour_round(round_obj)
    if balletour_round:
        players = [membership.player for membership in get_balletour_memberships()]
    else:
        players = [round_player.player for round_player in round_obj.round_players if round_player.player]

    existing_tags = (
        db.session.query(RoundImageTag.tag)
        .join(RoundImage)
        .join(Round)
        .filter(Round.course_id == round_obj.course_id)
        .order_by(func.lower(RoundImageTag.tag).asc())
        .distinct()
        .all()
    )
    player_names = {player.name.lower() for player in players}
    tags = [
        tag
        for (tag,) in existing_tags
        if tag and tag.lower() not in player_names
    ]
    return {
        "players": sorted(players, key=lambda player: player.name.lower()),
        "tags": tags,
    }


def build_course_tee_options(courses):
    options = {}
    for course in courses:
        total_par = sum(hole.par for hole in course.holes)
        options[str(course.id)] = [
            {
                "id": str(tee.id),
                "name": tee.name,
                "total_length_meters": sum(length.length_meters for length in tee.lengths),
                "total_par": total_par,
                "hole_count": course.hole_count,
                "supports_nine_hole_round": course_supports_nine_hole_round(course),
                "ratings": {
                    rating.gender: {
                        "slope": rating.slope,
                        "course_rating": rating.course_rating,
                    }
                    for rating in tee.ratings
                },
            }
            for tee in sorted(course.tees, key=lambda t: t.display_order)
        ]
    return options


def new_round_form_state(courses, players):
    selected_course_id = request.form.get("course_id", "").strip()
    selected_play_format = request.form.get("play_format", STROKE_PLAY).strip() or STROKE_PLAY
    course_tee_options = build_course_tee_options(courses)
    player_hcps = {str(player.id): str(player.default_hcp) for player in players}
    player_genders = {str(player.id): player.gender for player in players}

    player_slots = []
    for i in range(1, 5):
        default_player_id = str(g.current_user.player_id) if request.method == "GET" and i == 1 else ""
        slot_value = request.form.get(f"player_slot_{i}", default_player_id).strip()
        player_slots.append({
            "slot": i,
            "selected_player": slot_value,
            "new_name": request.form.get(f"new_player_name_{i}", "").strip(),
            "new_hcp": request.form.get(f"new_player_hcp_{i}", "").strip(),
            "new_tee": request.form.get(f"new_player_tee_{i}", "").strip(),
            "existing_hcp": request.form.get(f"hcp_existing_{i}", "").strip(),
            "existing_tee": request.form.get(f"tee_existing_{i}", "").strip(),
            "tracks_stats": (
                request.form.get(f"track_stats_{i}") == "1"
                if request.method == "POST"
                else i == 1
            ),
        })

    return render_template(
        "new_round.html",
        courses=courses,
        players=players,
        selected_course_id=selected_course_id,
        player_slots=player_slots,
        course_tee_options=course_tee_options,
        player_hcps=player_hcps,
        player_genders=player_genders,
        selected_round_hole_count=request.form.get("round_hole_count", "").strip(),
        play_format_options=PLAY_FORMAT_LABELS.items(),
        selected_play_format=selected_play_format,
    )


def _parse_hcp(raw_value, player_name):
    if not raw_value:
        raise ValueError(f"HCP mangler for {player_name}.")
    try:
        return float(raw_value.replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"HCP må være et gyldig tall for {player_name}.") from exc


def _parse_tee(raw_value, course_tees, player_name):
    if not raw_value:
        raise ValueError(f"Du må velge tee for {player_name}.")
    try:
        selected_tee_id = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"Ugyldig tee-valg for {player_name}.") from exc
    if selected_tee_id not in course_tees:
        raise ValueError(f"Valgt tee for {player_name} finnes ikke på banen.")
    return selected_tee_id


def _create_round(course, round_players_payload, stats_user_id=None, played_hole_count=None, play_format=STROKE_PLAY):
    selected_hole_count = played_hole_count or course.hole_count
    play_format = normalize_play_format(play_format)
    round_obj = Round(
        course_id=course.id,
        status="ongoing",
        play_format=play_format,
        started_at=server_now(),
        played_hole_count=selected_hole_count,
        stats_user_id=stats_user_id,
    )
    db.session.add(round_obj)
    db.session.flush()

    round_player_rows = []
    for payload in round_players_payload:
        rp = RoundPlayer(
            round_id=round_obj.id,
            player_id=payload["player"].id,
            selected_tee_id=payload["selected_tee_id"],
            player_name_snapshot=payload["player_name"],
            hcp_for_round=payload["hcp_for_round"],
            tracks_stats=bool(payload.get("tracks_stats")),
        )
        db.session.add(rp)
        db.session.flush()
        round_player_rows.append(rp)

    for rp in round_player_rows:
        for hole in range(1, selected_hole_count + 1):
            db.session.add(
                ScoreEntry(
                    round_id=round_obj.id,
                    round_player_id=rp.id,
                    hole_number=hole,
                    strokes=None,
                )
            )

    return round_obj


def _parse_round_hole_count(course):
    raw_value = request.form.get("round_hole_count", "").strip()
    try:
        selected_hole_count = int(raw_value or course.hole_count)
    except ValueError as exc:
        raise ValueError("Ugyldig valg av antall hull.") from exc

    if selected_hole_count not in allowed_round_hole_counts(course):
        raise ValueError("Denne banen kan ikke spilles med valgt antall hull.")
    return selected_hole_count


def _current_user_can_track_stats(round_obj):
    return bool(g.get("current_user") and round_obj.stats_user_id == g.current_user.id)


def _stats_round_player(round_obj):
    if not round_obj.stats_user:
        return None

    return next(
        (rp for rp in round_obj.round_players if rp.player_id == round_obj.stats_user.player_id),
        None,
    )


def _round_player_tracks_stats(round_obj, round_player, stats_rp=None):
    if _is_balletour_round(round_obj):
        return True
    return bool(round_player.tracks_stats or (stats_rp and round_player.id == stats_rp.id))


def _round_is_matchplay(round_obj):
    return is_matchplay_round(round_obj)


def _parse_matchplay_hole_result(raw_value, player_name):
    value = (raw_value or "").strip()
    if not value:
        return None
    if value not in MATCHPLAY_HOLE_RESULTS:
        raise ValueError(f"Ugyldig hullresultat for {player_name}.")
    return value


def _stat_form_has_any_value(round_player, hole, scoped=False):
    fields = [
        _stat_field_name("stat_drive", round_player, scoped),
        _stat_field_name("stat_putts", round_player, scoped),
        _stat_field_name("stat_last_putt_distance", round_player, scoped),
    ]
    if hole.par == 3:
        fields.extend([
            _stat_field_name("stat_green_status", round_player, scoped),
            _stat_field_name("stat_green_horizontal", round_player, scoped),
            _stat_field_name("stat_green_vertical", round_player, scoped),
        ])
    elif hole.par in (4, 5):
        fields.append(_stat_field_name("stat_fairway", round_player, scoped))
    return any(request.form.get(field, "").strip() for field in fields)


def _round_uses_scoped_stat_fields(round_obj):
    if _is_balletour_round(round_obj):
        return True
    return any(round_player.tracks_stats for round_player in round_obj.round_players)


def _parse_optional_int(raw_value, min_value, max_value):
    raw_value = (raw_value or "").strip()
    if raw_value == "":
        return None
    value = int(raw_value)
    if value < min_value or value > max_value:
        raise ValueError
    return value


def _parse_putts_for_score(raw_value, entry):
    raw_value = (raw_value or "").strip()
    if raw_value == "":
        return 0

    try:
        putts = int(raw_value)
    except ValueError as exc:
        raise ValueError("Antall putter må være et heltall.") from exc

    if putts < 0:
        raise ValueError("Antall putter kan ikke være negativt.")

    if putts > 0 and entry.strokes is not None and putts > entry.strokes - 1:
        raise ValueError("Antall putter må være 0, eller mellom 1 og score minus 1.")

    return putts


def _parse_last_putt_distance(raw_value="", meters_raw=None, decimeters_raw=None):
    if meters_raw is not None or decimeters_raw is not None:
        meters_text = (meters_raw or "").strip()
        decimeters_text = (decimeters_raw or "").strip()
        if meters_text == "" and decimeters_text == "":
            return None

        try:
            meters = int(meters_text or "0")
            decimeters = int(decimeters_text or "0")
        except ValueError as exc:
            raise ValueError("Avstand på siste putt må være et gyldig valg.") from exc

        if meters not in LAST_PUTT_METER_OPTIONS or decimeters not in LAST_PUTT_DECIMETER_OPTIONS:
            raise ValueError("Avstand på siste putt må være et gyldig valg.")

        total_decimeters = meters * 10 + decimeters
        if total_decimeters == 0:
            return None

        return round(total_decimeters / 10, 1)

    raw_value = (raw_value or "").strip()
    if raw_value == "":
        return None
    try:
        distance = float(raw_value.replace(",", "."))
    except ValueError as exc:
        raise ValueError("Avstand på siste putt må være et gyldig valg.") from exc
    total_decimeters = round(distance * 10)
    if abs(distance * 10 - total_decimeters) > 0.0001:
        raise ValueError("Avstand på siste putt må være et gyldig valg.")
    if total_decimeters == 0:
        return None
    distance = round(total_decimeters / 10, 1)
    if distance not in LAST_PUTT_DISTANCE_OPTIONS:
        raise ValueError("Avstand på siste putt må være et gyldig valg.")
    return distance


def _last_putt_distance_select_value(distance):
    if distance is None:
        return None
    return round(distance, 1)


def _validate_score_stat_rules(entry, hole, fairway_result, putts, score=None):
    score = entry.strokes if score is None else score
    validate_score_putts(putts, score)


def _validate_existing_stat_for_score(entry, hole, score):
    if score is None or not entry.detailed_stat:
        return
    _validate_score_stat_rules(
        entry,
        hole,
        entry.detailed_stat.fairway_result,
        entry.detailed_stat.putts,
        score=score,
    )


def _green_stat_parts(raw_value):
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return "hit", set()
    if raw_value in ("hit", "miss", "bunker"):
        return raw_value, set()
    if raw_value in ("left", "right", "short", "long"):
        return "miss", {raw_value}

    status, separator, direction_text = raw_value.partition(":")
    if not separator or status not in ("hit", "miss", "bunker"):
        return "hit", set()
    directions = {
        direction
        for direction in direction_text.split(",")
        if direction in GREEN_DIRECTIONS
    }
    return status, directions


def _encode_green_stat(status_raw, direction_values):
    status = (status_raw or "hit").strip()
    if status not in ("hit", "miss", "bunker"):
        raise ValueError("Green må være greentreff, miss eller bunker.")

    directions = []
    seen = set()
    for direction in direction_values:
        direction = (direction or "").strip()
        if direction not in GREEN_DIRECTIONS:
            raise ValueError("Green-retning har ugyldig verdi.")
        if direction not in seen:
            seen.add(direction)
            directions.append(direction)

    if "pin" in seen and ("left" in seen or "right" in seen):
        raise ValueError("På flagget kan ikke kombineres med venstre eller høyre.")
    if "short" in seen and "long" in seen:
        raise ValueError("Green kan ikke være både kort og lang.")
    if "left" in seen and "right" in seen:
        raise ValueError("Green kan ikke være både venstre og høyre.")

    if not directions:
        return status
    ordered = [direction for direction in GREEN_DIRECTIONS if direction in seen]
    return f"{status}:{','.join(ordered)}"


def _green_stat_from_form(status_field, direction_field):
    return _encode_green_stat(
        request.form.get(status_field, "hit"),
        request.form.getlist(direction_field),
    )


def _green_stat_from_grouped_form(status_field, pin_field, horizontal_field, vertical_field):
    directions = []
    horizontal = request.form.get(horizontal_field, "").strip()
    if request.form.get(pin_field) or horizontal == "pin":
        directions.append("pin")
    vertical = request.form.get(vertical_field, "").strip()
    if horizontal in ("left", "right"):
        directions.append(horizontal)
    if vertical:
        directions.append(vertical)
    return _encode_green_stat(request.form.get(status_field, "hit"), directions)


def _stat_field_name(base_name, round_player=None, scoped=False):
    if scoped and round_player:
        return f"{base_name}_{round_player.id}"
    return base_name


def _stat_form_value(base_name, round_player=None, scoped=False):
    return request.form.get(_stat_field_name(base_name, round_player, scoped), "")


def _green_stat_from_form_for_round_player(round_player, scoped=False, prefix="stat"):
    base = f"{prefix}_green"
    if scoped:
        return _green_stat_from_grouped_form(
            _stat_field_name(f"{base}_status", round_player, True),
            _stat_field_name(f"{base}_pin", round_player, True),
            _stat_field_name(f"{base}_horizontal", round_player, True),
            _stat_field_name(f"{base}_vertical", round_player, True),
        )
    return _green_stat_from_grouped_form(
        f"{base}_status",
        f"{base}_pin",
        f"{base}_horizontal",
        f"{base}_vertical",
    )


def _stat_view_values(stat):
    green_status, green_directions = _green_stat_parts(stat.fairway_result if stat else "")
    horizontal = "left" if "left" in green_directions else "right" if "right" in green_directions else ""
    vertical = "short" if "short" in green_directions else "long" if "long" in green_directions else ""
    return {
        "drive_distance_m": stat.drive_distance_m if stat else None,
        "fairway_result": stat.fairway_result if stat else "",
        "green_status": green_status,
        "green_directions": green_directions,
        "green_horizontal": horizontal,
        "green_vertical": vertical,
        "putts": stat.putts if stat else None,
        "last_putt_distance_m": stat.last_putt_distance_m if stat else None,
        "last_putt_distance": _last_putt_distance_select_value(stat.last_putt_distance_m if stat else None),
    }


def _score_bounds_for_par(par):
    if par == 3:
        return 1, 9
    if par == 4:
        return 2, 9
    if par == 5:
        return 3, 10
    return 1, 12


def _score_options_for_par(par):
    min_score, max_score = _score_bounds_for_par(par)
    return list(range(min_score, max_score + 1))


def _vs_par_display(value):
    if value == 0:
        return "E"
    return f"+{value}" if value > 0 else str(value)


def _live_vs_par_rows(round_obj, round_players, hole_number):
    par_by_hole = {
        hole.hole_number: hole.par
        for hole in round_holes(round_obj)
    }
    entries = ScoreEntry.query.filter_by(round_id=round_obj.id).all()
    entries_by_player = {}
    for entry in entries:
        entries_by_player.setdefault(entry.round_player_id, []).append(entry)

    rows = []
    for round_player in round_players:
        value = score_to_par_for_entries(
            entries_by_player.get(round_player.id, []),
            par_by_hole,
            excluded_hole_number=hole_number,
        )
        rows.append({
            "player": round_player,
            "value": value,
            "display": _vs_par_display(value),
        })
    return rows


def _parse_score_for_hole(raw_value, hole, player_name):
    raw_value = (raw_value or "").strip()
    if raw_value == "":
        return None

    try:
        strokes = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"Score må være et heltall for {player_name}.") from exc

    min_score, max_score = _score_bounds_for_par(hole.par)
    if strokes < min_score or strokes > max_score:
        raise ValueError(
            f"Score må være mellom {min_score} og {max_score} for {player_name} på par {hole.par}."
        )

    return strokes


def _save_score_stat(
    entry,
    hole,
    drive_distance_raw,
    fairway_result_raw,
    putts_raw,
    last_putt_distance_raw="",
    last_putt_meters_raw=None,
    last_putt_decimeters_raw=None,
):
    try:
        drive_distance = _parse_optional_int(drive_distance_raw, 1, 500)
    except ValueError as exc:
        raise ValueError("Utslagslengde må være et heltall mellom 1 og 500 meter.") from exc

    fairway_result = None
    if hole.par == 3:
        fairway_result = (fairway_result_raw or "hit").strip()
        # Validate and normalize old single-value green misses as well as new combinations.
        status, directions = _green_stat_parts(fairway_result)
        fairway_result = _encode_green_stat(status, directions)
    elif hole.par in (4, 5):
        fairway_result = (fairway_result_raw or "").strip()
        if fairway_result not in ("", "hit", "left", "right"):
            raise ValueError
        fairway_result = fairway_result or None

    putts = _parse_putts_for_score(putts_raw, entry)
    _validate_score_stat_rules(entry, hole, fairway_result, putts)
    last_putt_distance = _parse_last_putt_distance(
        last_putt_distance_raw,
        last_putt_meters_raw,
        last_putt_decimeters_raw,
    )
    if putts == 0:
        last_putt_distance = None

    stat = entry.detailed_stat
    if not stat and any(value is not None for value in (drive_distance, fairway_result, putts, last_putt_distance)):
        stat = ScoreStat(score_entry_id=entry.id)
        db.session.add(stat)

    if stat:
        stat.drive_distance_m = drive_distance
        stat.fairway_result = fairway_result
        stat.putts = putts
        stat.last_putt_distance_m = last_putt_distance


def _shot_measurement_view_values(entry):
    if not entry:
        return []
    return [
        {
            "shot_number": measurement.shot_number,
            "distance_m": round(measurement.distance_m, 1),
            "start": {
                "lat": measurement.start_lat,
                "lng": measurement.start_lng,
                "accuracy_m": measurement.start_accuracy_m,
            },
            "end": {
                "lat": measurement.end_lat,
                "lng": measurement.end_lng,
                "accuracy_m": measurement.end_accuracy_m,
            },
        }
        for measurement in entry.shot_measurements
    ]


def _save_shot_measurements(entry, raw_json):
    rows = parse_shot_measurements(raw_json)
    ShotMeasurement.query.filter_by(score_entry_id=entry.id).delete(synchronize_session=False)
    db.session.flush()
    for row in rows:
        db.session.add(ShotMeasurement(score_entry_id=entry.id, **row))


def _round_uses_club_tracking(round_obj):
    if round_obj.stats_user_id:
        return True
    if any(round_player.tracks_stats for round_player in round_obj.round_players):
        return True
    balletour_series = get_balletour_series()
    if balletour_series and round_obj.course_id == balletour_series.course_id:
        return True
    if round_obj.course.legacy_source == "golftracker":
        return True
    return PlayerHoleDefaultClub.query.filter_by(course_id=round_obj.course_id).first() is not None


def _is_balletour_round(round_obj):
    balletour_course_id = get_balletour_course_id()
    return bool(balletour_course_id and round_obj.course_id == balletour_course_id)


def _shanklife_rounds_query():
    query = Round.query
    balletour_course_id = get_balletour_course_id()
    if balletour_course_id:
        query = query.filter(Round.course_id != balletour_course_id)
    return query


def _balletour_round_summary(round_obj):
    rows = []
    course_par = sum(hole.par for hole in round_holes(round_obj))
    for round_player in sorted(round_obj.round_players, key=lambda rp: rp.id):
        entries = [
            entry for entry in round_player.score_entries
            if entry.strokes is not None
        ]
        total = sum(entry.strokes for entry in entries) if entries else None
        if total is None:
            score_text = "ikke fullført"
        else:
            score_text = f"{total} ({total - course_par:+d})"
        rows.append(f"- {round_player.player_name_snapshot}: {score_text}")
    return "\n".join(rows)


def _send_balletour_round_finished_mail(round_obj):
    if not _is_balletour_round(round_obj):
        return
    send_balletour_round_finished_notifications(
        round_obj,
        f"BalleTour-runde fullført: {round_obj.course.name}",
        _balletour_round_finished_mail_body(round_obj),
    )


def _round_players_text(round_obj):
    return "\n".join(
        f"- {round_player.player_name_snapshot} (hcp {round_player.hcp_for_round:.1f}, tee {round_player.selected_tee.name if round_player.selected_tee else '—'})"
        for round_player in sorted(round_obj.round_players, key=lambda item: item.id)
    )


def _current_user_round_player(round_obj):
    current_user = g.get("current_user")
    if not current_user:
        return None
    return next((rp for rp in round_obj.round_players if rp.player_id == current_user.player_id), None)


def _after_finish_redirect(round_obj):
    if _current_user_round_player(round_obj) and not _round_is_matchplay(round_obj):
        return redirect(url_for("golfbox_scores.prepare", round_id=round_obj.id))
    return redirect(url_for("rounds.round_score", round_id=round_obj.id))


def _send_shanklife_round_started_mail(round_obj):
    if _is_balletour_round(round_obj):
        return
    body = (
        "En ny Shanklife-runde er startet.\n\n"
        f"Runde: #{round_obj.id}\n"
        f"Bane: {round_obj.course.name}\n"
        f"Start: {format_server_datetime(round_obj.started_at)}\n\n"
        "Spillere:\n"
        f"{_round_players_text(round_obj)}"
    )
    send_shanklife_round_started_notifications(
        f"Shanklife-runde startet: {round_obj.course.name}",
        body,
    )


def _send_shanklife_round_finished_mail(round_obj):
    if _is_balletour_round(round_obj):
        return
    body = (
        "En Shanklife-runde er fullført.\n\n"
        f"Runde: #{round_obj.id}\n"
        f"Bane: {round_obj.course.name}\n"
        f"Start: {format_server_datetime(round_obj.started_at)}\n"
        f"Slutt: {format_server_datetime(round_obj.finished_at)}\n\n"
        "Score:\n"
        f"{_balletour_round_summary(round_obj)}"
    )
    send_shanklife_round_finished_notifications(
        f"Shanklife-runde fullført: {round_obj.course.name}",
        body,
    )


def _balletour_round_finished_mail_body(round_obj):
    return (
        "En BalleTour-runde er fullført.\n\n"
        f"Runde: #{round_obj.id}\n"
        f"Bane: {round_obj.course.name}\n"
        f"Start: {format_server_datetime(round_obj.started_at)}\n"
        f"Slutt: {format_server_datetime(round_obj.finished_at)}\n"
        f"Vær: {_round_weather_summary(round_obj)}\n\n"
        "Score:\n"
        f"{_balletour_round_summary(round_obj)}\n\n"
        "Scorekort:\n"
        f"{_balletour_round_scorecard_text(round_obj)}"
    )


def _balletour_round_scorecard_text(round_obj):
    scorecard = _balletour_round_scorecard(round_obj)
    holes = scorecard["holes"]
    header = ["Spiller"] + [str(hole.hole_number) for hole in holes] + ["Tot"]
    par_row = ["Par"] + [str(hole.par) for hole in holes] + [str(sum(hole.par for hole in holes))]
    rows = [header, par_row]

    for row in scorecard["rows"]:
        rows.append(
            [row["player_name"]]
            + [str(cell["score"]) if cell["score"] is not None else "-" for cell in row["cells"]]
            + [str(row["total"]) if row["total"] is not None else "-"]
        )

    widths = [max(len(item[index]) for item in rows) for index in range(len(header))]
    lines = []
    for row_index, row in enumerate(rows):
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 1:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)


def _score_shape_class(score, par):
    if score is None:
        return "plain"
    diff = score - par
    if diff <= -2:
        return "double-circle"
    if diff == -1:
        return "circle"
    if diff == 1:
        return "square"
    if diff >= 2:
        return "double-square"
    return "plain"


def _balletour_round_scorecard(round_obj):
    return _round_scorecard_rows(round_obj)


def _round_score_card(round_obj):
    scorecard = _round_scorecard_rows(round_obj)
    scorecard.update({
        "round": round_obj,
        "weather_summary": _round_weather_summary(round_obj),
    })
    return scorecard


def _round_scorecard_rows(round_obj):
    holes = round_holes(round_obj)
    par_by_hole = {hole.hole_number: hole.par for hole in holes}
    rows = []

    for round_player in sorted(round_obj.round_players, key=lambda item: item.id):
        entries = {
            entry.hole_number: entry
            for entry in round_player.score_entries
        }
        cells = []
        total = 0
        has_score = False
        for hole in holes:
            entry = entries.get(hole.hole_number)
            score = entry.strokes if entry else None
            if score is not None:
                total += score
                has_score = True
            cells.append({
                "hole_number": hole.hole_number,
                "score": score,
                "shape_class": _score_shape_class(score, par_by_hole.get(hole.hole_number, 3)),
            })
        rows.append({
            "player_name": round_player.player_name_snapshot,
            "cells": cells,
            "total": total if has_score else None,
        })

    return {
        "holes": holes,
        "rows": rows,
    }


def _round_weather_summary(round_obj):
    return summarize_weather_payload(round_obj.weather_json)


def _weather_json(payload):
    return json.dumps(payload, ensure_ascii=False) if payload else None


def _save_tee_club(entry, raw_value, player_name, allowed_club_ids=None):
    raw_value = (raw_value or "").strip()
    if raw_value == "":
        entry.tee_club_id = None
        return

    try:
        club_id = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"Ugyldig køllevalg for {player_name}.") from exc

    if not Club.query.get(club_id) or (allowed_club_ids is not None and club_id not in allowed_club_ids):
        raise ValueError(f"Valgt kølle for {player_name} finnes ikke.")

    entry.tee_club_id = club_id


def _club_options_for_round(round_obj):
    query = Club.query
    if _is_balletour_round(round_obj):
        query = query.filter(Club.sort_order >= 1)
    return query.order_by(Club.sort_order.asc(), Club.name.asc()).all()


def _score_totals(round_obj, round_player_id):
    score_entries = (
        ScoreEntry.query.filter_by(
            round_id=round_obj.id,
            round_player_id=round_player_id,
        )
        .order_by(ScoreEntry.hole_number.asc())
        .all()
    )

    total_strokes = 0
    out_total = 0
    in_total = 0

    for score_entry in score_entries:
        if score_entry.strokes is None:
            continue

        total_strokes += score_entry.strokes

        if score_entry.hole_number <= 9:
            out_total += score_entry.strokes
        else:
            in_total += score_entry.strokes

    return {
        "out": out_total if round_hole_count(round_obj) >= 9 else total_strokes,
        "in": in_total if round_hole_count(round_obj) > 9 else None,
        "total": total_strokes,
    }


def _next_unscored_hole_number(round_obj):
    round_player_ids = [round_player.id for round_player in round_obj.round_players]
    if not round_player_ids:
        return 1

    entries = ScoreEntry.query.filter(
        ScoreEntry.round_id == round_obj.id,
        ScoreEntry.round_player_id.in_(round_player_ids),
    ).all()
    scored_by_hole = {}
    for entry in entries:
        if entry.strokes is not None:
            scored_by_hole.setdefault(entry.hole_number, set()).add(entry.round_player_id)

    expected_player_count = len(round_player_ids)
    for hole in round_holes(round_obj):
        if len(scored_by_hole.get(hole.hole_number, set())) < expected_player_count:
            return hole.hole_number
    return round_hole_count(round_obj)


def _save_hole_from_form(round_obj, hole_number, stats_rp=None):
    hole = next((item for item in round_obj.course.holes if item.hole_number == hole_number), None)
    if not hole:
        raise ValueError("Fant ikke hullet.")

    round_players = sorted(round_obj.round_players, key=lambda rp: rp.id)
    club_tracking_enabled = _round_uses_club_tracking(round_obj)
    balletour_round = _is_balletour_round(round_obj)
    allowed_tee_club_ids = {
        club.id for club in _club_options_for_round(round_obj)
    } if club_tracking_enabled else None
    scoped_stats = _round_uses_scoped_stat_fields(round_obj)
    matchplay_round = _round_is_matchplay(round_obj)

    for rp in round_players:
        raw_value = request.form.get(f"score_{rp.id}", "").strip()
        entry = ScoreEntry.query.filter_by(
            round_id=round_obj.id,
            round_player_id=rp.id,
            hole_number=hole_number,
        ).first()

        if not entry:
            raise ValueError(f"Fant ikke scorelinje for {rp.player_name_snapshot}.")

        entry.strokes = _parse_score_for_hole(raw_value, hole, rp.player_name_snapshot)
        entry.hole_result = _parse_matchplay_hole_result(
            request.form.get(f"hole_result_{rp.id}", ""),
            rp.player_name_snapshot,
        ) if matchplay_round else None

        tracks_stats = _round_player_tracks_stats(round_obj, rp, stats_rp)

        if club_tracking_enabled and (balletour_round or tracks_stats):
            _save_tee_club(
                entry,
                request.form.get(f"tee_club_{rp.id}", ""),
                rp.player_name_snapshot,
                allowed_tee_club_ids,
            )

        save_optional_stats = tracks_stats and (not matchplay_round or _stat_form_has_any_value(rp, hole, scoped_stats))
        if save_optional_stats:
            try:
                _save_score_stat(
                    entry,
                    hole,
                    _stat_form_value("stat_drive", rp, scoped_stats),
                    _green_stat_from_form_for_round_player(rp, scoped_stats) if hole.par == 3 else _stat_form_value("stat_fairway", rp, scoped_stats),
                    _stat_form_value("stat_putts", rp, scoped_stats),
                    _stat_form_value("stat_last_putt_distance", rp, scoped_stats),
                )
            except ValueError as exc:
                message = str(exc) or "Ugyldig statistikk."
                raise ValueError(f"{message} ({rp.player_name_snapshot})") from exc

        if tracks_stats and not balletour_round:
            try:
                _save_shot_measurements(entry, request.form.get(f"shot_measurements_{rp.id}", ""))
            except ValueError as exc:
                message = str(exc) or "Ugyldig GPS-måling."
                raise ValueError(f"{message} ({rp.player_name_snapshot})") from exc


def _missing_hole_choices(round_obj, hole, stats_rp=None, require_scores=True):
    missing_by_player = []
    round_players = sorted(round_obj.round_players, key=lambda rp: rp.id)
    club_tracking_enabled = _round_uses_club_tracking(round_obj)
    balletour_round = _is_balletour_round(round_obj)
    scoped_stats = _round_uses_scoped_stat_fields(round_obj)
    matchplay_round = _round_is_matchplay(round_obj)

    for rp in round_players:
        missing = []
        if matchplay_round:
            if not request.form.get(f"hole_result_{rp.id}", "").strip():
                missing_by_player.append(f"{rp.player_name_snapshot}: hullresultat")
            continue
        if not request.form.get(f"score_{rp.id}", "").strip():
            if require_scores:
                missing_by_player.append(f"{rp.player_name_snapshot}: score")
            continue
        tracks_stats = _round_player_tracks_stats(round_obj, rp, stats_rp)
        if club_tracking_enabled and (balletour_round or tracks_stats) and not request.form.get(f"tee_club_{rp.id}", "").strip():
            missing.append("kølle")

        if tracks_stats:
            if hole.par == 3:
                green_status_name = _stat_field_name("stat_green_status", rp, scoped_stats)
                green_horizontal_name = _stat_field_name("stat_green_horizontal", rp, scoped_stats)
                green_vertical_name = _stat_field_name("stat_green_vertical", rp, scoped_stats)
                if green_status_name not in request.form or not request.form.get(green_status_name, "").strip():
                    missing.append("green")
                if green_horizontal_name not in request.form:
                    missing.append("retning")
                if green_vertical_name not in request.form:
                    missing.append("lengde")
            elif hole.par in (4, 5):
                fairway_name = _stat_field_name("stat_fairway", rp, scoped_stats)
                if not request.form.get(fairway_name, "").strip():
                    missing.append("fairway")

            putts_name = _stat_field_name("stat_putts", rp, scoped_stats)
            last_putt_name = _stat_field_name("stat_last_putt_distance", rp, scoped_stats)
            putts_raw = request.form.get(putts_name, "").strip()
            if putts_raw != "":
                try:
                    putts = int(putts_raw)
                except ValueError:
                    putts = None
                if putts and not request.form.get(last_putt_name, "").strip():
                    missing.append("siste putt")

        if missing:
            missing_by_player.append(f"{rp.player_name_snapshot}: {', '.join(missing)}")

    return missing_by_player


def _missing_round_choices(round_obj, stats_rp=None):
    missing_rows = []
    round_players = sorted(round_obj.round_players, key=lambda rp: rp.id)
    entries = {
        (entry.round_player_id, entry.hole_number): entry
        for entry in ScoreEntry.query.filter_by(round_id=round_obj.id).all()
    }
    club_tracking_enabled = _round_uses_club_tracking(round_obj)
    balletour_round = _is_balletour_round(round_obj)
    matchplay_round = _round_is_matchplay(round_obj)

    for hole in round_holes(round_obj):
        for rp in round_players:
            tracks_stats = _round_player_tracks_stats(round_obj, rp, stats_rp)
            club_required = club_tracking_enabled and (balletour_round or tracks_stats)
            missing = missing_saved_entry_choices(
                entries.get((rp.id, hole.hole_number)),
                hole,
                tracks_stats,
                club_required,
                require_score=not matchplay_round,
                require_hole_result=matchplay_round,
            )
            if missing:
                missing_rows.append({
                    "hole_number": hole.hole_number,
                    "message": f"Hull {hole.hole_number}, {rp.player_name_snapshot}: {', '.join(missing)}",
                })
    return missing_rows


def _hole_player_details(round_players, hole_number):
    details = {}
    for rp in round_players:
        length_meters = None
        length = CourseTeeLength.query.filter_by(
            tee_id=rp.selected_tee_id,
            hole_number=hole_number,
        ).first() if rp.selected_tee_id else None
        if length:
            length_meters = length.length_meters
        details[rp.id] = {
            "tee_name": rp.selected_tee.name if rp.selected_tee else "—",
            "length": length_meters,
        }
    return details


def _hole_club_defaults(round_obj, round_players, hole_number):
    defaults = {}
    rows = PlayerHoleDefaultClub.query.filter_by(
        course_id=round_obj.course_id,
        hole_number=hole_number,
    ).all()
    default_by_player = {row.player_id: row.club_id for row in rows}

    for rp in round_players:
        defaults[rp.id] = default_by_player.get(rp.player_id)
    return defaults


def _green_direction_label(directions):
    directions = set(directions)
    vertical = "kort" if "short" in directions else "lang" if "long" in directions else ""
    if "left" in directions or "right" in directions:
        if not vertical:
            vertical = "pin high"
        horizontal = "venstre" if "left" in directions else "høyre"
    elif "pin" in directions:
        horizontal = "på flagget"
    else:
        horizontal = ""
    return " ".join(part for part in (vertical, horizontal) if part)


def _hole_result_label(hole, raw_result):
    if not raw_result:
        return "—"
    if hole.par == 3:
        status, directions = _green_stat_parts(raw_result)
        if status == "hit":
            result_label = "Greentreff"
        elif status == "bunker":
            result_label = "Bunker"
        else:
            result_label = "Miss"
        direction_label = _green_direction_label(directions)
        return f"{result_label} · {direction_label}" if direction_label else result_label
    return {
        "hit": "Fairwaytreff",
        "left": "Miss fairway venstre",
        "right": "Miss fairway høyre",
    }.get(raw_result, raw_result)


def _previous_hole_history(round_obj, round_players, hole):
    if _is_balletour_round(round_obj):
        return []

    physical_filter = physical_hole_filter_values(hole)
    history_hole = aliased(CourseHole)
    balletour_course_id = get_balletour_course_id()
    history = []
    for rp in round_players:
        if not rp.player_id:
            continue
        query = (
            db.session.query(ScoreEntry, Round, ScoreStat, Club)
            .join(Round, Round.id == ScoreEntry.round_id)
            .join(RoundPlayer, RoundPlayer.id == ScoreEntry.round_player_id)
            .join(
                history_hole,
                (history_hole.course_id == Round.course_id)
                & (history_hole.hole_number == ScoreEntry.hole_number),
            )
            .outerjoin(ScoreStat, ScoreStat.score_entry_id == ScoreEntry.id)
            .outerjoin(Club, Club.id == ScoreEntry.tee_club_id)
            .filter(Round.id != round_obj.id)
            .filter(Round.status == "finished")
            .filter(Round.play_format != MATCHPLAY)
            .filter(RoundPlayer.player_id == rp.player_id)
            .filter(ScoreEntry.strokes.isnot(None))
        )
        if balletour_course_id:
            query = query.filter(Round.course_id != balletour_course_id)
        if physical_filter:
            group, loop, physical_hole_number = physical_filter
            query = query.filter(func.lower(history_hole.physical_course_group) == group)
            query = query.filter(func.lower(history_hole.physical_loop) == loop)
            query = query.filter(history_hole.physical_hole_number == physical_hole_number)
        else:
            query = query.filter(Round.course_id == round_obj.course_id)
            query = query.filter(ScoreEntry.hole_number == hole.hole_number)

        rows = query.order_by(Round.started_at.desc()).limit(8).all()
        if not rows:
            continue

        score_values = [entry.strokes for entry, _round_row, _stat, _club in rows if entry.strokes is not None]
        drive_values = [
            stat.drive_distance_m
            for _entry, _round_row, stat, _club in rows
            if stat and stat.drive_distance_m is not None
        ]
        putt_values = [
            stat.putts
            for _entry, _round_row, stat, _club in rows
            if stat and stat.putts is not None
        ]
        history.append({
            "player": rp,
            "summary": {
                "rounds": len(rows),
                "avg_score": round(sum(score_values) / len(score_values), 1) if score_values else None,
                "best_score": min(score_values) if score_values else None,
                "avg_drive": round(sum(drive_values) / len(drive_values), 1) if drive_values else None,
                "avg_putts": round(sum(putt_values) / len(putt_values), 1) if putt_values else None,
            },
            "rows": [
                {
                    "date": round_row.started_at.strftime("%Y-%m-%d") if round_row.started_at else "",
                    "source": (
                        f"{round_row.course.name} hull {entry.hole_number}"
                        if round_row.course_id != round_obj.course_id or entry.hole_number != hole.hole_number
                        else None
                    ),
                    "score": entry.strokes,
                    "to_par": entry.strokes - hole.par if entry.strokes is not None else None,
                    "club": club.name if club else None,
                    "drive_distance": stat.drive_distance_m if stat else None,
                    "result": _hole_result_label(hole, stat.fairway_result if stat else None),
                    "putts": stat.putts if stat else None,
                    "last_putt_distance": stat.last_putt_distance_m if stat else None,
                }
                for entry, round_row, stat, club in rows
            ],
        })

    if not history:
        return None

    return {
        "label": physical_hole_label(hole),
        "items": history,
    }


def _round_image_extension(filename):
    if "." not in filename:
        return None
    extension = filename.rsplit(".", 1)[1].lower()
    return extension if extension in ALLOWED_ROUND_IMAGE_EXTENSIONS else None


def _save_round_image_file(file_storage, round_id):
    extension = _round_image_extension(file_storage.filename or "")
    if not extension:
        raise ValueError("Bildet må være JPG, PNG eller WebP.")

    upload_root = Path(current_app.config["UPLOAD_FOLDER"]) / "round-images"
    upload_root.mkdir(parents=True, exist_ok=True)

    original_name = secure_filename(file_storage.filename or "round-image")
    stem = Path(original_name).stem or "round-image"
    filename = f"round-{round_id}-{server_now():%Y%m%d%H%M%S}-{token_hex(4)}-{stem}.{extension}"
    file_storage.save(upload_root / filename)
    return filename


@rounds_bp.route("/rounds")
def rounds():
    all_rounds = _shanklife_rounds_query().order_by(Round.started_at.desc()).all()
    return render_template("rounds.html", rounds=all_rounds, title="Alle runder")


@rounds_bp.route("/rounds/ongoing")
def ongoing_rounds():
    rows = (
        _shanklife_rounds_query()
        .filter_by(status="ongoing")
        .order_by(Round.started_at.desc())
        .all()
    )
    return render_template("rounds.html", rounds=rows, title="Pågående runder")


@rounds_bp.route("/rounds/finished")
def finished_rounds():
    rows = (
        _shanklife_rounds_query()
        .filter_by(status="finished")
        .order_by(Round.started_at.desc())
        .all()
    )
    score_cards = [_round_score_card(round_obj) for round_obj in rows]
    return render_template("finished_rounds.html", score_cards=score_cards, title="Fullførte runder")


@rounds_bp.route("/rounds/new", methods=["GET", "POST"])
def new_round():
    courses = Course.query.order_by(Course.name.asc()).all()
    players = Player.query.order_by(Player.name.asc()).all()
    course_tee_options = build_course_tee_options(courses)

    if request.method == "POST":
        course_id_raw = request.form.get("course_id", "").strip()
        try:
            play_format = normalize_play_format(request.form.get("play_format", STROKE_PLAY))
        except ValueError as exc:
            flash(str(exc), "error")
            return new_round_form_state(courses, players)

        if not course_id_raw:
            flash("Du må velge bane.", "error")
            return new_round_form_state(courses, players)

        try:
            course_id = int(course_id_raw)
        except ValueError:
            flash("Ugyldig banevalg.", "error")
            return new_round_form_state(courses, players)

        course = Course.query.get(course_id)
        if not course:
            flash("Valgt bane finnes ikke.", "error")
            return new_round_form_state(courses, players)

        try:
            selected_hole_count = _parse_round_hole_count(course)
        except ValueError as exc:
            flash(str(exc), "error")
            return new_round_form_state(courses, players)

        course_tees = {tee.id: tee for tee in course.tees}
        if not course_tees:
            flash("Valgt bane har ingen tees. Legg til minst ett tee-sett på banen først.", "error")
            return new_round_form_state(courses, players)

        round_players_payload = []

        for i in range(1, 5):
            slot_value = request.form.get(f"player_slot_{i}", "").strip()
            if not slot_value:
                continue

            if slot_value == "new":
                # New player
                new_name = request.form.get(f"new_player_name_{i}", "").strip()
                new_hcp_raw = request.form.get(f"new_player_hcp_{i}", "").strip()
                new_tee_raw = request.form.get(f"new_player_tee_{i}", "").strip()

                if not new_name:
                    flash(f"Navn mangler for ny spiller i slot {i}.", "error")
                    return new_round_form_state(courses, players)

                if not new_hcp_raw:
                    flash(f"HCP mangler for ny spiller '{new_name}'.", "error")
                    return new_round_form_state(courses, players)

                if not new_tee_raw:
                    flash(f"Du må velge tee for ny spiller '{new_name}'.", "error")
                    return new_round_form_state(courses, players)

                existing_name_match = Player.query.filter(
                    func.lower(Player.name) == new_name.lower()
                ).first()
                if existing_name_match:
                    flash(f"Spilleren '{new_name}' finnes allerede. Velg spilleren fra listen i stedet.", "error")
                    return new_round_form_state(courses, players)

                try:
                    new_hcp = float(new_hcp_raw.replace(",", "."))
                except ValueError:
                    flash(f"HCP må være et gyldig tall for ny spiller '{new_name}'.", "error")
                    return new_round_form_state(courses, players)

                try:
                    selected_tee_id = int(new_tee_raw)
                except ValueError:
                    flash(f"Ugyldig tee-valg for ny spiller '{new_name}'.", "error")
                    return new_round_form_state(courses, players)

                if selected_tee_id not in course_tees:
                    flash(f"Valgt tee for ny spiller '{new_name}' finnes ikke på banen.", "error")
                    return new_round_form_state(courses, players)

                new_player = Player(name=new_name, default_hcp=new_hcp, gender="male")
                db.session.add(new_player)
                db.session.flush()

                round_players_payload.append(
                    {
                        "player": new_player,
                        "player_name": new_player.name,
                        "hcp_for_round": new_hcp,
                        "selected_tee_id": selected_tee_id,
                        "tracks_stats": request.form.get(f"track_stats_{i}") == "1",
                    }
                )
            else:
                # Existing player
                try:
                    player_id = int(slot_value)
                except ValueError:
                    flash(f"Ugyldig spiller-valg i slot {i}.", "error")
                    return new_round_form_state(courses, players)

                player = Player.query.get(player_id)
                if not player:
                    flash(f"Valgt spiller finnes ikke i slot {i}.", "error")
                    return new_round_form_state(courses, players)

                hcp_raw = request.form.get(f"hcp_existing_{i}", "").strip()
                tee_raw = request.form.get(f"tee_existing_{i}", "").strip()

                if not hcp_raw:
                    flash(f"HCP mangler for {player.name}.", "error")
                    return new_round_form_state(courses, players)

                try:
                    round_hcp = float(hcp_raw.replace(",", "."))
                except ValueError:
                    flash(f"HCP må være et gyldig tall for {player.name}.", "error")
                    return new_round_form_state(courses, players)

                if not tee_raw:
                    flash(f"Du må velge tee for {player.name}.", "error")
                    return new_round_form_state(courses, players)

                try:
                    selected_tee_id = int(tee_raw)
                except ValueError:
                    flash(f"Ugyldig tee-valg for {player.name}.", "error")
                    return new_round_form_state(courses, players)

                if selected_tee_id not in course_tees:
                    flash(f"Valgt tee for {player.name} finnes ikke på banen.", "error")
                    return new_round_form_state(courses, players)

                round_players_payload.append(
                    {
                        "player": player,
                        "player_name": player.name,
                        "hcp_for_round": round_hcp,
                        "selected_tee_id": selected_tee_id,
                        "tracks_stats": request.form.get(f"track_stats_{i}") == "1",
                    }
                )

                # Update default HCP if changed
                if round_hcp != player.default_hcp:
                    player.default_hcp = round_hcp

        names_lower = [p["player_name"].lower() for p in round_players_payload]
        if len(names_lower) != len(set(names_lower)):
            flash("Du kan ikke ha samme spiller mer enn én gang i samme runde.", "error")
            return new_round_form_state(courses, players)

        if not (1 <= len(round_players_payload) <= 4):
            flash("Du må velge mellom 1 og 4 spillere totalt.", "error")
            return new_round_form_state(courses, players)

        round_obj = _create_round(
            course,
            round_players_payload,
            played_hole_count=selected_hole_count,
            play_format=play_format,
        )
        db.session.commit()
        _send_shanklife_round_started_mail(round_obj)
        flash("Runde opprettet.", "success")
        return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=1))

    return new_round_form_state(courses, players)


def new_stats_round_form_state(courses, players):
    selected_course_id = request.form.get("course_id", "").strip()
    course_tee_options = build_course_tee_options(courses)
    player_hcps = {str(player.id): str(player.default_hcp) for player in players}
    player_genders = {str(player.id): player.gender for player in players}
    current_player = g.current_user.player

    other_slots = []
    for i in range(2, 5):
        slot_value = request.form.get(f"player_slot_{i}", "").strip()
        other_slots.append({
            "slot": i,
            "selected_player": slot_value,
            "new_name": request.form.get(f"new_player_name_{i}", "").strip(),
            "new_hcp": request.form.get(f"new_player_hcp_{i}", "").strip(),
            "new_tee": request.form.get(f"new_player_tee_{i}", "").strip(),
            "existing_hcp": request.form.get(f"hcp_existing_{i}", "").strip(),
            "existing_tee": request.form.get(f"tee_existing_{i}", "").strip(),
        })

    return render_template(
        "new_stats_round.html",
        courses=courses,
        players=players,
        current_player=current_player,
        selected_course_id=selected_course_id,
        self_hcp=request.form.get("self_hcp", str(current_player.default_hcp)).strip(),
        self_tee=request.form.get("self_tee", "").strip(),
        other_slots=other_slots,
        course_tee_options=course_tee_options,
        player_hcps=player_hcps,
        player_genders=player_genders,
    )


@rounds_bp.route("/rounds/new-with-stats", methods=["GET", "POST"])
@login_required
def new_stats_round():
    if request.method == "GET":
        return redirect(url_for("rounds.new_round"))

    courses = Course.query.order_by(Course.name.asc()).all()
    players = Player.query.order_by(Player.name.asc()).all()
    current_player = g.current_user.player

    if request.method == "POST":
        course_id_raw = request.form.get("course_id", "").strip()
        if not course_id_raw:
            flash("Du må velge bane.", "error")
            return new_stats_round_form_state(courses, players)

        try:
            course_id = int(course_id_raw)
        except ValueError:
            flash("Ugyldig banevalg.", "error")
            return new_stats_round_form_state(courses, players)

        course = Course.query.get(course_id)
        if not course:
            flash("Valgt bane finnes ikke.", "error")
            return new_stats_round_form_state(courses, players)

        try:
            selected_hole_count = _parse_round_hole_count(course)
        except ValueError as exc:
            flash(str(exc), "error")
            return new_stats_round_form_state(courses, players)

        course_tees = {tee.id: tee for tee in course.tees}
        if not course_tees:
            flash("Valgt bane har ingen tees. Legg til minst ett tee-sett på banen først.", "error")
            return new_stats_round_form_state(courses, players)

        try:
            self_hcp = _parse_hcp(request.form.get("self_hcp", "").strip(), current_player.name)
            self_tee_id = _parse_tee(request.form.get("self_tee", "").strip(), course_tees, current_player.name)
        except ValueError as exc:
            flash(str(exc), "error")
            return new_stats_round_form_state(courses, players)

        round_players_payload = [
            {
                "player": current_player,
                "player_name": current_player.name,
                "hcp_for_round": self_hcp,
                "selected_tee_id": self_tee_id,
                "tracks_stats": True,
            }
        ]

        if self_hcp != current_player.default_hcp:
            current_player.default_hcp = self_hcp

        for i in range(2, 5):
            slot_value = request.form.get(f"player_slot_{i}", "").strip()
            if not slot_value:
                continue

            if slot_value == "new":
                new_name = request.form.get(f"new_player_name_{i}", "").strip()
                new_hcp_raw = request.form.get(f"new_player_hcp_{i}", "").strip()
                new_tee_raw = request.form.get(f"new_player_tee_{i}", "").strip()

                if not new_name:
                    flash(f"Navn mangler for ny spiller i slot {i}.", "error")
                    return new_stats_round_form_state(courses, players)

                existing_name_match = Player.query.filter(func.lower(Player.name) == new_name.lower()).first()
                if existing_name_match:
                    flash(f"Spilleren '{new_name}' finnes allerede. Velg spilleren fra listen i stedet.", "error")
                    return new_stats_round_form_state(courses, players)

                try:
                    new_hcp = _parse_hcp(new_hcp_raw, new_name)
                    selected_tee_id = _parse_tee(new_tee_raw, course_tees, new_name)
                except ValueError as exc:
                    flash(str(exc), "error")
                    return new_stats_round_form_state(courses, players)

                new_player = Player(name=new_name, default_hcp=new_hcp, gender="male")
                db.session.add(new_player)
                db.session.flush()
                round_players_payload.append(
                    {
                        "player": new_player,
                        "player_name": new_player.name,
                        "hcp_for_round": new_hcp,
                        "selected_tee_id": selected_tee_id,
                    }
                )
            else:
                try:
                    player_id = int(slot_value)
                except ValueError:
                    flash(f"Ugyldig spiller-valg i slot {i}.", "error")
                    return new_stats_round_form_state(courses, players)

                player = Player.query.get(player_id)
                if not player:
                    flash(f"Valgt spiller finnes ikke i slot {i}.", "error")
                    return new_stats_round_form_state(courses, players)

                try:
                    round_hcp = _parse_hcp(request.form.get(f"hcp_existing_{i}", "").strip(), player.name)
                    selected_tee_id = _parse_tee(request.form.get(f"tee_existing_{i}", "").strip(), course_tees, player.name)
                except ValueError as exc:
                    flash(str(exc), "error")
                    return new_stats_round_form_state(courses, players)

                round_players_payload.append(
                    {
                        "player": player,
                        "player_name": player.name,
                        "hcp_for_round": round_hcp,
                        "selected_tee_id": selected_tee_id,
                    }
                )
                if round_hcp != player.default_hcp:
                    player.default_hcp = round_hcp

        names_lower = [p["player_name"].lower() for p in round_players_payload]
        if len(names_lower) != len(set(names_lower)):
            flash("Du kan ikke ha samme spiller mer enn én gang i samme runde.", "error")
            return new_stats_round_form_state(courses, players)

        round_obj = _create_round(
            course,
            round_players_payload,
            stats_user_id=g.current_user.id,
            played_hole_count=selected_hole_count,
        )
        db.session.commit()
        _send_shanklife_round_started_mail(round_obj)
        flash("Runde med statistikk opprettet.", "success")
        return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=1))

    return new_stats_round_form_state(courses, players)


@rounds_bp.route("/rounds/<int:round_id>/delete", methods=["POST"])
@login_required
def delete_round(round_id):
    if not g.current_user.is_admin:
        flash("Du har ikke tilgang til å slette runder.", "error")
        return redirect(url_for("main.index"))

    round_obj = Round.query.get_or_404(round_id)
    next_url = request.form.get("next", "").strip()
    if not next_url.startswith("/"):
        next_url = url_for("rounds.rounds")

    db.session.delete(round_obj)
    db.session.commit()
    flash(f"Runde {round_id} slettet.", "success")
    return redirect(next_url)


@rounds_bp.route("/rounds/<int:round_id>")
def round_detail(round_id):
    round_obj = Round.query.get_or_404(round_id)
    if round_obj.status == "finished" and not _is_balletour_round(round_obj):
        return redirect(url_for("rounds.round_score", round_id=round_obj.id))
    return render_template("round_detail.html", round=round_obj)


@rounds_bp.route("/rounds/<int:round_id>/continue")
def continue_round(round_id):
    round_obj = Round.query.get_or_404(round_id)
    if round_obj.status != "ongoing":
        return redirect(url_for("rounds.round_score", round_id=round_obj.id))
    return redirect(url_for(
        "rounds.round_hole",
        round_id=round_obj.id,
        hole_number=_next_unscored_hole_number(round_obj),
    ))


@rounds_bp.route("/rounds/<int:round_id>/hole/<int:hole_number>", methods=["GET", "POST"])
def round_hole(round_id, hole_number):
    round_obj = Round.query.get_or_404(round_id)
    course = round_obj.course
    played_hole_count = round_hole_count(round_obj)
    admin_edit_mode = bool(
        request.args.get("edit") == "1"
        and round_obj.status == "finished"
        and g.get("current_user")
        and g.current_user.is_admin
        and not _is_balletour_round(round_obj)
    )

    def edit_url(target_hole):
        values = {"round_id": round_obj.id, "hole_number": target_hole}
        if admin_edit_mode:
            values["edit"] = "1"
        return url_for("rounds.round_hole", **values)

    if hole_number < 1 or hole_number > played_hole_count:
        flash("Ugyldig hullnummer.", "error")
        return redirect(edit_url(1))

    stats_rp = _stats_round_player(round_obj)
    hole = next((item for item in course.holes if item.hole_number == hole_number), None)

    if request.method == "POST":
        if round_obj.status != "ongoing" and not admin_edit_mode:
            flash("Runden er allerede fullført.", "error")
            return redirect(url_for("rounds.round_score", round_id=round_obj.id))

        action = request.form.get("action", "next")
        if admin_edit_mode and action not in ("previous", "next"):
            flash("Ugyldig redigeringshandling.", "error")
            return redirect(edit_url(hole_number))

        if action in ("next", "finish") or admin_edit_mode:
            missing_choices = _missing_hole_choices(
                round_obj,
                hole,
                stats_rp,
                require_scores=action == "finish" or admin_edit_mode,
            )
            if missing_choices:
                flash("Mangler valg: " + " | ".join(missing_choices), "error")
                return redirect(edit_url(hole_number))

        try:
            _save_hole_from_form(round_obj, hole_number, stats_rp)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(edit_url(hole_number))

        if action == "finish":
            missing_round_choices = _missing_round_choices(round_obj, stats_rp)
            if missing_round_choices:
                db.session.commit()
                shown_messages = [row["message"] for row in missing_round_choices[:8]]
                remaining = len(missing_round_choices) - len(shown_messages)
                if remaining:
                    shown_messages.append(f"og {remaining} mangler til")
                flash("Runden kan ikke fullføres. " + " | ".join(shown_messages), "error")
                return redirect(url_for(
                    "rounds.round_hole",
                    round_id=round_obj.id,
                    hole_number=missing_round_choices[0]["hole_number"],
                ))
            round_obj.status = "finished"
            round_obj.finished_at = server_now()
            db.session.commit()
            if _is_balletour_round(round_obj):
                _send_balletour_round_finished_mail(round_obj)
            else:
                _send_shanklife_round_finished_mail(round_obj)
            flash("Runden er fullført.", "success")
            return _after_finish_redirect(round_obj)

        db.session.commit()

        if action == "previous":
            target_hole = played_hole_count if hole_number == 1 else hole_number - 1
        else:
            target_hole = 1 if hole_number == played_hole_count else hole_number + 1

        return redirect(edit_url(target_hole))

    round_players = sorted(round_obj.round_players, key=lambda rp: rp.id)
    club_tracking_enabled = _round_uses_club_tracking(round_obj)
    score_entries = {
        entry.round_player_id: entry
        for entry in ScoreEntry.query.filter_by(
            round_id=round_obj.id,
            hole_number=hole_number,
        ).all()
    }
    score_options = _score_options_for_par(hole.par)
    scoped_stats_fields = _round_uses_scoped_stat_fields(round_obj)

    stats_values_by_player = {}
    shot_measurements_by_player = {}
    for rp in round_players:
        if not _round_player_tracks_stats(round_obj, rp, stats_rp):
            continue
        entry = score_entries.get(rp.id)
        stats_values_by_player[rp.id] = _stat_view_values(entry.detailed_stat if entry else None)
        if not _is_balletour_round(round_obj):
            shot_measurements_by_player[rp.id] = _shot_measurement_view_values(entry)
    stats_values = stats_values_by_player.get(stats_rp.id if stats_rp else None, {})
    clubs = _club_options_for_round(round_obj) if club_tracking_enabled else []
    hole_images = (
        RoundImage.query.filter_by(round_id=round_obj.id, hole_number=hole_number)
        .order_by(RoundImage.uploaded_at.desc())
        .all()
    )

    return render_template(
        "round_hole.html",
        round=round_obj,
        course=course,
        hole=hole,
        display_stroke_index=round_handicap_stroke_index(round_obj, hole),
        round_players=round_players,
        live_vs_par_rows=_live_vs_par_rows(round_obj, round_players, hole_number),
        score_entries=score_entries,
        stats_round_player_id=stats_rp.id if stats_rp else None,
        stats_values=stats_values,
        score_options=score_options,
        stats_values_by_player=stats_values_by_player,
        shot_measurements_by_player=shot_measurements_by_player,
        scoped_stats_fields=scoped_stats_fields,
        last_putt_distance_options=LAST_PUTT_DISTANCE_OPTIONS,
        drive_distance_options=DRIVE_DISTANCE_OPTIONS,
        club_tracking_enabled=club_tracking_enabled,
        clubs=clubs,
        club_defaults=_hole_club_defaults(round_obj, round_players, hole_number) if club_tracking_enabled else {},
        player_details=_hole_player_details(round_players, hole_number),
        previous_hole_history=_previous_hole_history(round_obj, round_players, hole),
        hole_images=hole_images,
        image_tag_choices=_round_image_tag_choices(round_obj),
        is_balletour_scoring_page=_is_balletour_round(round_obj),
        is_matchplay_round=_round_is_matchplay(round_obj),
        matchplay_hole_result_labels=MATCHPLAY_HOLE_RESULT_LABELS,
        admin_edit_mode=admin_edit_mode,
        score_entry_editable=round_obj.status == "ongoing" or admin_edit_mode,
        played_hole_count=played_hole_count,
        previous_hole=played_hole_count if hole_number == 1 else hole_number - 1,
        next_hole=1 if hole_number == played_hole_count else hole_number + 1,
    )


@rounds_bp.route("/rounds/<int:round_id>/hole/<int:hole_number>/images", methods=["POST"])
@login_required
def upload_round_hole_image(round_id, hole_number):
    round_obj = Round.query.get_or_404(round_id)
    course = round_obj.course

    if hole_number < 1 or hole_number > round_hole_count(round_obj):
        flash("Ugyldig hullnummer.", "error")
        return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=1))

    image_file = request.files.get("round_image")
    if not image_file or not image_file.filename:
        flash("Velg et bilde først.", "error")
        return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=hole_number))

    selected_tag = request.form.get("image_tag", "").strip()
    tagged_player_id = None
    tags = []
    if selected_tag.startswith("player:"):
        try:
            tagged_player_id = int(selected_tag.removeprefix("player:"))
        except ValueError:
            flash("Ugyldig tag.", "error")
            return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=hole_number))

        allowed_player_ids = (
            {membership.player_id for membership in get_balletour_memberships()}
            if _is_balletour_round(round_obj)
            else {rp.player_id for rp in round_obj.round_players}
        )
        if tagged_player_id not in allowed_player_ids:
            flash("Spilleren finnes ikke blant tilgjengelige tags.", "error")
            return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=hole_number))
        tagged_player = Player.query.get(tagged_player_id)
        if tagged_player:
            tags.append(tagged_player.name)
    elif selected_tag.startswith("tag:"):
        try:
            tags.extend(_normalize_image_tags(selected_tag.removeprefix("tag:")))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=hole_number))
    elif selected_tag:
        flash("Ugyldig tag.", "error")
        return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=hole_number))

    try:
        tags.extend(_normalize_image_tags(request.form.get("new_tags", "")))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=hole_number))

    try:
        filename = _save_round_image_file(image_file, round_obj.id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=hole_number))

    image = RoundImage(
        round_id=round_obj.id,
        filename=filename,
        hole_number=hole_number,
        tagged_player_id=tagged_player_id,
    )
    db.session.add(image)
    db.session.flush()
    seen_tags = set()
    for tag in tags:
        key = tag.lower()
        if key in seen_tags:
            continue
        seen_tags.add(key)
        db.session.add(RoundImageTag(image_id=image.id, tag=tag))
    db.session.commit()
    flash(f"Bilde lagt til for {course.name}, hull {hole_number}.", "success")
    return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=hole_number))


@rounds_bp.route("/rounds/<int:round_id>/autosave", methods=["POST"])
def autosave_score(round_id):
    round_obj = Round.query.get_or_404(round_id)

    if round_obj.status != "ongoing":
        return jsonify({"ok": False, "error": "Runden er fullført."}), 400

    round_player_id_raw = request.form.get("round_player_id", "").strip()
    hole_number_raw = request.form.get("hole_number", "").strip()
    strokes_raw = request.form.get("strokes", "").strip()

    try:
        round_player_id = int(round_player_id_raw)
        hole_number = int(hole_number_raw)
    except ValueError:
        return jsonify({"ok": False, "error": "Ugyldige data."}), 400

    round_player = RoundPlayer.query.filter_by(
        id=round_player_id,
        round_id=round_obj.id,
    ).first()

    if not round_player:
        return jsonify({"ok": False, "error": "Fant ikke spiller i runden."}), 404

    if hole_number < 1 or hole_number > round_hole_count(round_obj):
        return jsonify({"ok": False, "error": "Ugyldig hullnummer."}), 400

    hole = next((item for item in round_obj.course.holes if item.hole_number == hole_number), None)
    if not hole:
        return jsonify({"ok": False, "error": "Fant ikke hullet."}), 404

    entry = ScoreEntry.query.filter_by(
        round_id=round_obj.id,
        round_player_id=round_player_id,
        hole_number=hole_number,
    ).first()

    if not entry:
        return jsonify({"ok": False, "error": "Fant ikke scorelinje."}), 404

    try:
        parsed_strokes = _parse_score_for_hole(strokes_raw, hole, round_player.player_name_snapshot)
        _validate_existing_stat_for_score(entry, hole, parsed_strokes)
        entry.strokes = parsed_strokes
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "round_player_id": round_player_id,
            "hole_number": hole_number,
            "saved_value": entry.strokes,
            "totals": _score_totals(round_obj, round_player_id),
        }
    )


@rounds_bp.route("/rounds/<int:round_id>/stats-autosave", methods=["POST"])
@login_required
def autosave_score_stat(round_id):
    round_obj = Round.query.get_or_404(round_id)
    stats_rp = _stats_round_player(round_obj)

    if round_obj.status != "ongoing":
        return jsonify({"ok": False, "error": "Runden er fullført."}), 400

    if not stats_rp and not _is_balletour_round(round_obj) and not any(rp.tracks_stats for rp in round_obj.round_players):
        return jsonify({"ok": False, "error": "Du kan ikke føre statistikk på denne runden."}), 403

    round_player = stats_rp
    round_player_id_raw = request.form.get("round_player_id", "").strip()
    if round_player_id_raw:
        try:
            round_player_id = int(round_player_id_raw)
        except ValueError:
            return jsonify({"ok": False, "error": "Ugyldig spiller."}), 400
        round_player = RoundPlayer.query.filter_by(id=round_player_id, round_id=round_obj.id).first()
        if not round_player:
            return jsonify({"ok": False, "error": "Fant ikke spiller i runden."}), 404
        if not _round_player_tracks_stats(round_obj, round_player, stats_rp):
            return jsonify({"ok": False, "error": "Spilleren fører ikke statistikk på denne runden."}), 403

    if not round_player:
        return jsonify({"ok": False, "error": "Fant ikke statistikkspiller i runden."}), 404

    hole_number_raw = request.form.get("hole_number", "").strip()
    try:
        hole_number = int(hole_number_raw)
    except ValueError:
        return jsonify({"ok": False, "error": "Ugyldig hullnummer."}), 400

    hole = next((item for item in round_obj.course.holes if item.hole_number == hole_number), None)
    if not hole:
        return jsonify({"ok": False, "error": "Fant ikke hullet."}), 404

    entry = ScoreEntry.query.filter_by(
        round_id=round_obj.id,
        round_player_id=round_player.id,
        hole_number=hole_number,
    ).first()

    if not entry:
        return jsonify({"ok": False, "error": "Fant ikke scorelinje."}), 404

    try:
        _save_score_stat(
            entry,
            hole,
            request.form.get("drive_distance", ""),
            _green_stat_from_grouped_form("green_status", "green_pin", "green_horizontal", "green_vertical") if hole.par == 3 else request.form.get("fairway_result", ""),
            request.form.get("putts", ""),
            request.form.get("last_putt_distance", ""),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc) or "Statistikkfelt har ugyldig verdi."}), 400

    db.session.commit()
    return jsonify({"ok": True, "hole_number": hole_number})


@rounds_bp.route("/rounds/<int:round_id>/balletour-scorecard")
def balletour_round_scorecard(round_id):
    round_obj = Round.query.get_or_404(round_id)
    if not _is_balletour_round(round_obj):
        return redirect(url_for("rounds.round_score", round_id=round_obj.id))

    hole_number_raw = request.args.get("hole", "").strip()
    try:
        return_hole = int(hole_number_raw)
    except ValueError:
        return_hole = 1
    if return_hole < 1 or return_hole > round_hole_count(round_obj):
        return_hole = 1

    return render_template(
        "balletour_scorecard_popup.html",
        round=round_obj,
        scorecard=_balletour_round_scorecard(round_obj),
        return_hole=return_hole,
        is_balletour_scoring_page=True,
    )


@rounds_bp.route("/rounds/<int:round_id>/score", methods=["GET", "POST"])
def round_score(round_id):
    round_obj = Round.query.get_or_404(round_id)
    course = round_obj.course
    round_players = sorted(round_obj.round_players, key=lambda rp: rp.id)
    stats_rp = _stats_round_player(round_obj)
    played_holes = round_holes(round_obj)
    played_hole_count = round_hole_count(round_obj)

    if request.method == "POST":
        action = request.form.get("action", "save")
        for rp in round_players:
            for hole in range(1, played_hole_count + 1):
                field_name = f"score_{rp.id}_{hole}"
                raw_value = request.form.get(field_name, "").strip()

                entry = ScoreEntry.query.filter_by(
                    round_id=round_obj.id,
                    round_player_id=rp.id,
                    hole_number=hole,
                ).first()

                hole_obj = next((item for item in course.holes if item.hole_number == hole), None)
                try:
                    parsed_strokes = _parse_score_for_hole(raw_value, hole_obj, rp.player_name_snapshot)
                    _validate_existing_stat_for_score(entry, hole_obj, parsed_strokes)
                    entry.strokes = parsed_strokes
                except ValueError as exc:
                    flash(str(exc), "error")
                    return redirect(url_for("rounds.round_score", round_id=round_obj.id))

                if stats_rp and rp.id == stats_rp.id:
                    try:
                        _save_score_stat(
                            entry,
                            hole_obj,
                            request.form.get(f"stat_drive_{hole}", ""),
                            _green_stat_from_grouped_form(
                                f"stat_green_status_{hole}",
                                f"stat_green_pin_{hole}",
                                f"stat_green_horizontal_{hole}",
                                f"stat_green_vertical_{hole}",
                            ) if hole_obj.par == 3 else request.form.get(f"stat_fairway_{hole}", ""),
                            request.form.get(f"stat_putts_{hole}", ""),
                            request.form.get(f"stat_last_putt_distance_{hole}", ""),
                        )
                    except ValueError as exc:
                        message = str(exc) or "Ugyldig statistikk."
                        flash(f"{message} ({rp.player_name_snapshot}, hull {hole})", "error")
                        return redirect(url_for("rounds.round_score", round_id=round_obj.id))

                if _round_is_matchplay(round_obj):
                    try:
                        entry.hole_result = _parse_matchplay_hole_result(
                            request.form.get(f"hole_result_{rp.id}_{hole}", ""),
                            rp.player_name_snapshot,
                        )
                    except ValueError as exc:
                        flash(str(exc), "error")
                        return redirect(url_for("rounds.round_score", round_id=round_obj.id))

        was_ongoing = round_obj.status == "ongoing"
        if action == "finish":
            missing_round_choices = _missing_round_choices(round_obj, stats_rp)
            if missing_round_choices:
                db.session.commit()
                flash(
                    "Runden kan ikke fullføres før alle hull og obligatoriske felt er fylt ut.",
                    "error",
                )
                return redirect(url_for(
                    "rounds.round_hole",
                    round_id=round_obj.id,
                    hole_number=missing_round_choices[0]["hole_number"],
                ))
            round_obj.status = "finished"
            round_obj.finished_at = server_now()
            flash("Runden er fullført.", "success")
        else:
            flash("Score lagret.", "success")

        db.session.commit()
        if action == "finish" and was_ongoing:
            if _is_balletour_round(round_obj):
                _send_balletour_round_finished_mail(round_obj)
            else:
                _send_shanklife_round_finished_mail(round_obj)
            return _after_finish_redirect(round_obj)
        return redirect(url_for("rounds.round_score", round_id=round_obj.id))

    score_map = {}
    hole_result_map = {}
    totals = {}
    received_strokes_map = {}
    playing_handicap_map = {}
    score_entry_id_map = {}
    stats_map = {}

    visible_tees = []
    visible_tee_ids = set()
    tee_length_columns = []

    for rp in round_players:
        if rp.selected_tee and rp.selected_tee.id not in visible_tee_ids:
            visible_tee_ids.add(rp.selected_tee.id)
            visible_tees.append(rp.selected_tee)

    for tee in visible_tees:
        lengths = {}
        tee_lengths = (
            CourseTeeLength.query.filter_by(tee_id=tee.id)
            .order_by(CourseTeeLength.hole_number.asc())
            .all()
        )
        for length in tee_lengths:
            lengths[length.hole_number] = length.length_meters

        tee_length_columns.append(
            {
                "tee_id": tee.id,
                "tee_name": tee.name,
                "lengths": lengths,
            }
        )

    for rp in round_players:
        entries = {
            e.hole_number: e
            for e in ScoreEntry.query.filter_by(
                round_id=round_obj.id,
                round_player_id=rp.id,
            ).all()
        }

        player_scores = {}
        player_hole_results = {}
        out_total = 0
        in_total = 0
        grand_total = 0

        for hole in range(1, played_hole_count + 1):
            entry = entries.get(hole)
            strokes = entry.strokes if entry else None
            player_scores[hole] = strokes
            player_hole_results[hole] = entry.hole_result if entry else None
            score_entry_id_map.setdefault(rp.id, {})[hole] = entry.id if entry else None

            if stats_rp and rp.id == stats_rp.id:
                stat = entry.detailed_stat if entry else None
                stats_map[hole] = _stat_view_values(stat)

            if strokes is not None:
                grand_total += strokes
                if hole <= 9:
                    out_total += strokes
                else:
                    in_total += strokes

        score_map[rp.id] = player_scores
        hole_result_map[rp.id] = player_hole_results
        totals[rp.id] = {
            "out": out_total if played_hole_count >= 9 else grand_total,
            "in": in_total if played_hole_count > 9 else None,
            "total": grand_total,
        }

        gender = rp.player.gender if rp.player and rp.player.gender else "male"
        rating = None
        if rp.selected_tee:
            for candidate in rp.selected_tee.ratings:
                if candidate.gender == gender:
                    rating = candidate
                    break

        total_par = sum(hole.par for hole in course.holes)
        playing_handicap = calculate_playing_handicap_for_course(
            rp.hcp_for_round,
            rating,
            total_par,
            played_hole_count,
        )
        playing_handicap_map[rp.id] = received_strokes_for_round(playing_handicap, played_hole_count)
        received_strokes_map[rp.id] = {}
        for hole_obj in played_holes:
            received_strokes = 0
            if playing_handicap is not None:
                received_strokes = strokes_received_for_hole(
                    playing_handicap,
                    round_handicap_stroke_index(round_obj, hole_obj),
                    played_hole_count,
                )
            received_strokes_map[rp.id][hole_obj.hole_number] = max(received_strokes, 0)

    template_name = "round_score.html"
    round_summary = None
    if round_obj.status == "finished" and not _is_balletour_round(round_obj):
        template_name = "finished_round_detail.html"
        round_summary = build_round_summary(round_obj)

    return render_template(
        template_name,
        round=round_obj,
        course=course,
        played_holes=played_holes,
        played_hole_count=played_hole_count,
        hole_index_map={
            hole.hole_number: round_handicap_stroke_index(round_obj, hole)
            for hole in played_holes
        },
        round_players=round_players,
        score_map=score_map,
        hole_result_map=hole_result_map,
        totals=totals,
        tee_length_columns=tee_length_columns,
        playing_handicap_map=playing_handicap_map,
        received_strokes_map=received_strokes_map,
        score_entry_id_map=score_entry_id_map,
        stats_round_player_id=stats_rp.id if stats_rp else None,
        stats_map=stats_map,
        score_options_by_hole={
            hole.hole_number: _score_options_for_par(hole.par)
            for hole in played_holes
        },
        putt_options=list(range(0, 6)),
        last_putt_distance_options=LAST_PUTT_DISTANCE_OPTIONS,
        drive_distance_options=DRIVE_DISTANCE_OPTIONS,
        is_balletour_scoring_page=_is_balletour_round(round_obj),
        is_matchplay_round=_round_is_matchplay(round_obj),
        matchplay_hole_result_labels=MATCHPLAY_HOLE_RESULT_LABELS,
        current_user_round_player=_current_user_round_player(round_obj),
        round_summary=round_summary,
        weather_summary=_round_weather_summary(round_obj),
    )
