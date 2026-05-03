from pathlib import Path
from secrets import token_hex

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for, jsonify
from sqlalchemy import func
from werkzeug.utils import secure_filename

from extensions import db
from models import (
    Club,
    Course,
    CourseTeeLength,
    Player,
    PlayerHoleDefaultClub,
    Round,
    RoundImage,
    RoundPlayer,
    ScoreEntry,
    ScoreStat,
)
from routes.auth import login_required
from services.handicap import calculate_playing_handicap_for_course, received_strokes_for_round, strokes_received_for_hole
from services.balletour import get_balletour_series
from services.mailer import send_mail
from services.time import server_now

rounds_bp = Blueprint("rounds", __name__)

ALLOWED_ROUND_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
GREEN_DIRECTIONS = ("pin", "long", "short", "left", "right")
LAST_PUTT_METER_OPTIONS = tuple(range(0, 16))
LAST_PUTT_DECIMETER_OPTIONS = tuple(range(0, 10))


def build_course_tee_options(courses):
    options = {}
    for course in courses:
        total_par = sum(hole.par for hole in course.holes)
        options[str(course.id)] = [
            {
                "id": str(tee.id),
                "name": tee.name,
                "total_par": total_par,
                "hole_count": course.hole_count,
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
    course_tee_options = build_course_tee_options(courses)
    player_hcps = {str(player.id): str(player.default_hcp) for player in players}
    player_genders = {str(player.id): player.gender for player in players}

    player_slots = []
    for i in range(1, 5):
        slot_value = request.form.get(f"player_slot_{i}", "").strip()
        player_slots.append({
            "slot": i,
            "selected_player": slot_value,
            "new_name": request.form.get(f"new_player_name_{i}", "").strip(),
            "new_hcp": request.form.get(f"new_player_hcp_{i}", "").strip(),
            "new_tee": request.form.get(f"new_player_tee_{i}", "").strip(),
            "existing_hcp": request.form.get(f"hcp_existing_{i}", "").strip(),
            "existing_tee": request.form.get(f"tee_existing_{i}", "").strip(),
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


def _create_round(course, round_players_payload, stats_user_id=None):
    round_obj = Round(
        course_id=course.id,
        status="ongoing",
        started_at=server_now(),
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
        )
        db.session.add(rp)
        db.session.flush()
        round_player_rows.append(rp)

    for rp in round_player_rows:
        for hole in range(1, course.hole_count + 1):
            db.session.add(
                ScoreEntry(
                    round_id=round_obj.id,
                    round_player_id=rp.id,
                    hole_number=hole,
                    strokes=None,
                )
            )

    return round_obj


def _current_user_can_track_stats(round_obj):
    return bool(g.get("current_user") and round_obj.stats_user_id == g.current_user.id)


def _stats_round_player(round_obj):
    if not round_obj.stats_user:
        return None

    return next(
        (rp for rp in round_obj.round_players if rp.player_id == round_obj.stats_user.player_id),
        None,
    )


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

    if putts == 0:
        return putts

    if entry.strokes is None or entry.strokes < 1:
        raise ValueError("Legg inn score før du legger inn putter.")

    if putts > entry.strokes - 1:
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
    meters = total_decimeters // 10
    decimeters = total_decimeters % 10
    if total_decimeters == 0:
        return None
    if meters not in LAST_PUTT_METER_OPTIONS or decimeters not in LAST_PUTT_DECIMETER_OPTIONS:
        raise ValueError("Avstand på siste putt må være et gyldig valg.")
    return round(total_decimeters / 10, 1)


def _last_putt_distance_select_values(distance):
    if distance is None:
        return None, None
    total_decimeters = round(distance * 10)
    return total_decimeters // 10, total_decimeters % 10


def _validate_score_stat_rules(entry, hole, fairway_result, putts, score=None):
    score = entry.strokes if score is None else score
    putts = putts or 0

    if putts > 0:
        if score is None or score < 1:
            raise ValueError("Legg inn score før du legger inn putter.")
        if putts > score - 1:
            raise ValueError("Antall putter må være 0, eller mellom 1 og score minus 1.")

    if hole.par != 3:
        return

    status, _directions = _green_stat_parts(fairway_result)
    if status == "hit":
        return

    if score is None or score < 1:
        raise ValueError("Legg inn score før du registrerer miss eller bunker.")

    min_score = putts + 2
    if score < min_score:
        raise ValueError("Ved miss eller bunker må total score være minst 2 slag pluss antall putter.")


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
        raise ValueError

    directions = []
    seen = set()
    for direction in direction_values:
        direction = (direction or "").strip()
        if direction not in GREEN_DIRECTIONS:
            raise ValueError
        if direction == "pin" and status != "hit":
            raise ValueError
        if direction not in seen:
            seen.add(direction)
            directions.append(direction)

    if "pin" in seen and len(seen) > 1:
        raise ValueError
    if "short" in seen and "long" in seen:
        raise ValueError
    if "left" in seen and "right" in seen:
        raise ValueError

    if not directions:
        return status
    ordered = [direction for direction in GREEN_DIRECTIONS if direction in seen]
    return f"{status}:{','.join(ordered)}"


def _green_stat_from_form(status_field, direction_field):
    return _encode_green_stat(
        request.form.get(status_field, "hit"),
        request.form.getlist(direction_field),
    )


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
    drive_distance = None
    fairway_result = None
    if hole.par == 3:
        fairway_result = (fairway_result_raw or "hit").strip()
        # Validate and normalize old single-value green misses as well as new combinations.
        status, directions = _green_stat_parts(fairway_result)
        fairway_result = _encode_green_stat(status, directions)
    elif hole.par in (4, 5):
        drive_distance = _parse_optional_int(drive_distance_raw, 1, 500)
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


def _round_uses_club_tracking(round_obj):
    balletour_series = get_balletour_series()
    if balletour_series and round_obj.course_id == balletour_series.course_id:
        return True
    if round_obj.course.legacy_source == "golftracker":
        return True
    return PlayerHoleDefaultClub.query.filter_by(course_id=round_obj.course_id).first() is not None


def _is_balletour_round(round_obj):
    balletour_series = get_balletour_series()
    return bool(balletour_series and round_obj.course_id == balletour_series.course_id)


def _balletour_round_summary(round_obj):
    rows = []
    course_par = sum(hole.par for hole in round_obj.course.holes)
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
    send_mail(
        f"BalleTour-runde fullført: {round_obj.course.name}",
        (
            "En BalleTour-runde er fullført.\n\n"
            f"Runde: #{round_obj.id}\n"
            f"Bane: {round_obj.course.name}\n"
            f"Fullført: {round_obj.finished_at.strftime('%d.%m.%Y %H:%M') if round_obj.finished_at else '-'}\n\n"
            "Score:\n"
            f"{_balletour_round_summary(round_obj)}"
        ),
    )


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
    holes = list(round_obj.course.holes)
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


def _save_tee_club(entry, raw_value, player_name):
    raw_value = (raw_value or "").strip()
    if raw_value == "":
        entry.tee_club_id = None
        return

    try:
        club_id = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"Ugyldig køllevalg for {player_name}.") from exc

    if not Club.query.get(club_id):
        raise ValueError(f"Valgt kølle for {player_name} finnes ikke.")

    entry.tee_club_id = club_id


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
        "out": out_total if round_obj.course.hole_count >= 9 else total_strokes,
        "in": in_total if round_obj.course.hole_count > 9 else None,
        "total": total_strokes,
    }


def _save_hole_from_form(round_obj, hole_number, stats_rp=None):
    hole = next((item for item in round_obj.course.holes if item.hole_number == hole_number), None)
    if not hole:
        raise ValueError("Fant ikke hullet.")

    round_players = sorted(round_obj.round_players, key=lambda rp: rp.id)
    club_tracking_enabled = _round_uses_club_tracking(round_obj)

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

        if club_tracking_enabled:
            _save_tee_club(
                entry,
                request.form.get(f"tee_club_{rp.id}", ""),
                rp.player_name_snapshot,
            )

        if stats_rp and rp.id == stats_rp.id:
            try:
                _save_score_stat(
                    entry,
                    hole,
                    request.form.get("stat_drive", ""),
                    _green_stat_from_form("stat_green_status", "stat_green_direction") if hole.par == 3 else request.form.get("stat_fairway", ""),
                    request.form.get("stat_putts", ""),
                    request.form.get("stat_last_putt_distance", ""),
                    request.form.get("stat_last_putt_meters", ""),
                    request.form.get("stat_last_putt_decimeters", ""),
                )
            except ValueError as exc:
                message = str(exc) or "Ugyldig statistikk."
                raise ValueError(f"{message} ({rp.player_name_snapshot})") from exc


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
    all_rounds = Round.query.order_by(Round.started_at.desc()).all()
    return render_template("rounds.html", rounds=all_rounds, title="Alle runder")


@rounds_bp.route("/rounds/ongoing")
def ongoing_rounds():
    rows = Round.query.filter_by(status="ongoing").order_by(Round.started_at.desc()).all()
    return render_template("rounds.html", rounds=rows, title="Pågående runder")


@rounds_bp.route("/rounds/finished")
def finished_rounds():
    rows = Round.query.filter_by(status="finished").order_by(Round.started_at.desc()).all()
    return render_template("rounds.html", rounds=rows, title="Fullførte runder")


@rounds_bp.route("/rounds/new", methods=["GET", "POST"])
def new_round():
    courses = Course.query.order_by(Course.name.asc()).all()
    players = Player.query.order_by(Player.name.asc()).all()
    course_tee_options = build_course_tee_options(courses)

    if request.method == "POST":
        course_id_raw = request.form.get("course_id", "").strip()

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

        round_obj = _create_round(course, round_players_payload)
        db.session.commit()
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

        round_obj = _create_round(course, round_players_payload, stats_user_id=g.current_user.id)
        db.session.commit()
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
    return render_template("round_detail.html", round=round_obj)


@rounds_bp.route("/rounds/<int:round_id>/hole/<int:hole_number>", methods=["GET", "POST"])
def round_hole(round_id, hole_number):
    round_obj = Round.query.get_or_404(round_id)
    course = round_obj.course

    if hole_number < 1 or hole_number > course.hole_count:
        flash("Ugyldig hullnummer.", "error")
        return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=1))

    stats_rp = _stats_round_player(round_obj)

    if request.method == "POST":
        if round_obj.status != "ongoing":
            flash("Runden er allerede fullført.", "error")
            return redirect(url_for("rounds.round_score", round_id=round_obj.id))

        action = request.form.get("action", "next")

        try:
            _save_hole_from_form(round_obj, hole_number, stats_rp)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=hole_number))

        if action == "finish":
            round_obj.status = "finished"
            round_obj.finished_at = server_now()
            db.session.commit()
            _send_balletour_round_finished_mail(round_obj)
            flash("Runden er fullført.", "success")
            return redirect(url_for("rounds.round_score", round_id=round_obj.id))

        db.session.commit()

        if action == "previous":
            target_hole = max(1, hole_number - 1)
        else:
            target_hole = min(course.hole_count, hole_number + 1)

        return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=target_hole))

    hole = next((item for item in course.holes if item.hole_number == hole_number), None)
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

    stats_entry = score_entries.get(stats_rp.id) if stats_rp else None
    stat = stats_entry.detailed_stat if stats_entry and stats_entry.detailed_stat else None
    stats_values = {
        "drive_distance_m": stat.drive_distance_m if stat else None,
        "fairway_result": stat.fairway_result if stat else "",
        "putts": stat.putts if stat else None,
        "last_putt_distance_m": stat.last_putt_distance_m if stat else None,
    }
    last_putt_meters, last_putt_decimeters = _last_putt_distance_select_values(stats_values["last_putt_distance_m"])
    stats_values["last_putt_meters"] = last_putt_meters
    stats_values["last_putt_decimeters"] = last_putt_decimeters
    green_status, green_directions = _green_stat_parts(stats_values["fairway_result"])
    stats_values["green_status"] = green_status
    stats_values["green_directions"] = green_directions
    clubs = Club.query.order_by(Club.sort_order.asc(), Club.name.asc()).all() if club_tracking_enabled else []
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
        round_players=round_players,
        score_entries=score_entries,
        stats_round_player_id=stats_rp.id if stats_rp else None,
        stats_values=stats_values,
        score_options=score_options,
        last_putt_meter_options=LAST_PUTT_METER_OPTIONS,
        last_putt_decimeter_options=LAST_PUTT_DECIMETER_OPTIONS,
        club_tracking_enabled=club_tracking_enabled,
        clubs=clubs,
        club_defaults=_hole_club_defaults(round_obj, round_players, hole_number) if club_tracking_enabled else {},
        player_details=_hole_player_details(round_players, hole_number),
        hole_images=hole_images,
        is_balletour_scoring_page=_is_balletour_round(round_obj),
        previous_hole=hole_number - 1 if hole_number > 1 else None,
        next_hole=hole_number + 1 if hole_number < course.hole_count else None,
    )


@rounds_bp.route("/rounds/<int:round_id>/hole/<int:hole_number>/images", methods=["POST"])
def upload_round_hole_image(round_id, hole_number):
    round_obj = Round.query.get_or_404(round_id)
    course = round_obj.course

    if hole_number < 1 or hole_number > course.hole_count:
        flash("Ugyldig hullnummer.", "error")
        return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=1))

    image_file = request.files.get("round_image")
    if not image_file or not image_file.filename:
        flash("Velg et bilde først.", "error")
        return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=hole_number))

    tagged_player_id = None
    tagged_player_raw = request.form.get("tagged_player_id", "").strip()
    if tagged_player_raw:
        try:
            tagged_player_id = int(tagged_player_raw)
        except ValueError:
            flash("Ugyldig spiller-tag.", "error")
            return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=hole_number))

        if not any(rp.player_id == tagged_player_id for rp in round_obj.round_players):
            flash("Spilleren finnes ikke i denne runden.", "error")
            return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=hole_number))

    try:
        filename = _save_round_image_file(image_file, round_obj.id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=hole_number))

    db.session.add(
        RoundImage(
            round_id=round_obj.id,
            filename=filename,
            hole_number=hole_number,
            tagged_player_id=tagged_player_id,
        )
    )
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

    if hole_number < 1 or hole_number > round_obj.course.hole_count:
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

    if not stats_rp:
        return jsonify({"ok": False, "error": "Du kan ikke føre statistikk på denne runden."}), 403

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
        round_player_id=stats_rp.id,
        hole_number=hole_number,
    ).first()

    if not entry:
        return jsonify({"ok": False, "error": "Fant ikke scorelinje."}), 404

    try:
        _save_score_stat(
            entry,
            hole,
            request.form.get("drive_distance", ""),
            _green_stat_from_form("green_status", "green_direction") if hole.par == 3 else request.form.get("fairway_result", ""),
            request.form.get("putts", ""),
            request.form.get("last_putt_distance", ""),
            request.form.get("last_putt_meters", ""),
            request.form.get("last_putt_decimeters", ""),
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
    if return_hole < 1 or return_hole > round_obj.course.hole_count:
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

    if request.method == "POST":
        for rp in round_players:
            for hole in range(1, course.hole_count + 1):
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
                            _green_stat_from_form(f"stat_green_status_{hole}", f"stat_green_direction_{hole}") if hole_obj.par == 3 else request.form.get(f"stat_fairway_{hole}", ""),
                            request.form.get(f"stat_putts_{hole}", ""),
                            request.form.get(f"stat_last_putt_distance_{hole}", ""),
                            request.form.get(f"stat_last_putt_meters_{hole}", ""),
                            request.form.get(f"stat_last_putt_decimeters_{hole}", ""),
                        )
                    except ValueError as exc:
                        message = str(exc) or "Ugyldig statistikk."
                        flash(f"{message} ({rp.player_name_snapshot}, hull {hole})", "error")
                        return redirect(url_for("rounds.round_score", round_id=round_obj.id))

        action = request.form.get("action", "save")

        was_ongoing = round_obj.status == "ongoing"
        if action == "finish":
            round_obj.status = "finished"
            round_obj.finished_at = server_now()
            flash("Runden er fullført.", "success")
        else:
            flash("Score lagret.", "success")

        db.session.commit()
        if action == "finish" and was_ongoing:
            _send_balletour_round_finished_mail(round_obj)
        return redirect(url_for("rounds.round_score", round_id=round_obj.id))

    score_map = {}
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
        out_total = 0
        in_total = 0
        grand_total = 0

        for hole in range(1, course.hole_count + 1):
            entry = entries.get(hole)
            strokes = entry.strokes if entry else None
            player_scores[hole] = strokes
            score_entry_id_map.setdefault(rp.id, {})[hole] = entry.id if entry else None

            if stats_rp and rp.id == stats_rp.id:
                stat = entry.detailed_stat if entry else None
                green_status, green_directions = _green_stat_parts(stat.fairway_result if stat else "")
                stats_map[hole] = {
                    "drive_distance_m": stat.drive_distance_m if stat else None,
                    "fairway_result": stat.fairway_result if stat else "",
                    "green_status": green_status,
                    "green_directions": green_directions,
                    "putts": stat.putts if stat else None,
                    "last_putt_distance_m": stat.last_putt_distance_m if stat else None,
                }
                last_putt_meters, last_putt_decimeters = _last_putt_distance_select_values(
                    stats_map[hole]["last_putt_distance_m"]
                )
                stats_map[hole]["last_putt_meters"] = last_putt_meters
                stats_map[hole]["last_putt_decimeters"] = last_putt_decimeters

            if strokes is not None:
                grand_total += strokes
                if hole <= 9:
                    out_total += strokes
                else:
                    in_total += strokes

        score_map[rp.id] = player_scores
        totals[rp.id] = {
            "out": out_total if course.hole_count >= 9 else grand_total,
            "in": in_total if course.hole_count > 9 else None,
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
            course.hole_count,
        )
        playing_handicap_map[rp.id] = received_strokes_for_round(playing_handicap, course.hole_count)
        received_strokes_map[rp.id] = {}
        for hole_obj in course.holes:
            received_strokes = 0
            if playing_handicap is not None:
                received_strokes = strokes_received_for_hole(
                    playing_handicap,
                    hole_obj.stroke_index,
                    course.hole_count,
                )
            received_strokes_map[rp.id][hole_obj.hole_number] = max(received_strokes, 0)

    return render_template(
        "round_score.html",
        round=round_obj,
        course=course,
        round_players=round_players,
        score_map=score_map,
        totals=totals,
        tee_length_columns=tee_length_columns,
        playing_handicap_map=playing_handicap_map,
        received_strokes_map=received_strokes_map,
        score_entry_id_map=score_entry_id_map,
        stats_round_player_id=stats_rp.id if stats_rp else None,
        stats_map=stats_map,
        score_options_by_hole={
            hole.hole_number: _score_options_for_par(hole.par)
            for hole in course.holes
        },
        putt_options=list(range(0, 6)),
        last_putt_meter_options=LAST_PUTT_METER_OPTIONS,
        last_putt_decimeter_options=LAST_PUTT_DECIMETER_OPTIONS,
        is_balletour_scoring_page=_is_balletour_round(round_obj),
    )
