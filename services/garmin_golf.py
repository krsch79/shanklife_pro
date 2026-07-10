import os
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func

from extensions import db
from models import Club, GarminRoundSync, ScoreStat
from services.round_length import round_holes
from services.time import server_now


OSLO_TIMEZONE = ZoneInfo("Europe/Oslo")
MAX_START_TIME_DELTA = timedelta(hours=6)
GARMIN_TOKEN_FILENAME = "garmin_tokens.json"

# Garmin's club-type ids are stable catalogue ids. Values match Shanklife's
# existing club names and sort order.
GARMIN_CLUB_TYPE_MAP = {
    1: ("Driver", -30),
    2: ("3-wood", -20),
    3: ("5-wood", -10),
    4: ("7-wood", -5),
    5: ("2 hybrid", 0),
    6: ("3 hybrid", 0),
    7: ("4 hybrid", 0),
    8: ("5 hybrid", 0),
    13: ("Jern 4", 1),
    14: ("Jern 5", 2),
    15: ("Jern 6", 3),
    16: ("Jern 7", 4),
    17: ("Jern 8", 5),
    18: ("Jern 9", 6),
    19: ("PW", 7),
    20: ("GW", 8),
    21: ("SW", 9),
    22: ("LW", 10),
}


class GarminGolfSyncError(ValueError):
    pass


def garmin_token_store_path(user):
    configured_root = os.environ.get("SHANKLIFE_GARMIN_TOKEN_ROOT", "").strip()
    root = Path(configured_root).expanduser() if configured_root else Path.home() / ".config" / "shanklife" / "garmin"
    return root / str(user.id)


def garmin_connection_available(user):
    if not user:
        return False
    return (garmin_token_store_path(user) / GARMIN_TOKEN_FILENAME).is_file()


def _garmin_client_for_user(user):
    token_store = garmin_token_store_path(user)
    if not garmin_connection_available(user):
        raise GarminGolfSyncError("Garmin er ikke koblet til denne Shanklife-brukeren.")

    try:
        from garminconnect import Garmin
        from garminconnect.exceptions import GarminConnectAuthenticationError, GarminConnectConnectionError
    except ImportError as exc:
        raise GarminGolfSyncError("Garmin-integrasjonen mangler på serveren.") from exc

    client = Garmin()
    try:
        client.login(str(token_store))
    except GarminConnectAuthenticationError as exc:
        raise GarminGolfSyncError("Garmin-tilkoblingen er utløpt og må kobles til på nytt.") from exc
    except GarminConnectConnectionError as exc:
        raise GarminGolfSyncError("Kunne ikke kontakte Garmin Connect. Prøv igjen om litt.") from exc
    token_store.chmod(0o700)
    for token_file in token_store.iterdir():
        if token_file.is_file():
            token_file.chmod(0o600)
    return client


def _garmin_summaries(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        rows = payload.get("scorecardSummaries")
        if isinstance(rows, list):
            return rows
    return []


def _parse_garmin_start(value):
    raw_value = (value or "").strip()
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(OSLO_TIMEZONE).replace(tzinfo=None)


def _course_tokens(value):
    translated = (
        (value or "")
        .lower()
        .replace("blå", "blue")
        .replace("rød", "red")
        .replace("gul", "yellow")
    )
    normalized = unicodedata.normalize("NFKD", translated).encode("ascii", "ignore").decode("ascii")
    ignored = {"golf", "golfklubb", "golfbane", "gk", "club", "course"}
    return {token for token in re.findall(r"[a-z0-9]+", normalized) if token not in ignored}


def _round_total(round_player):
    strokes = [entry.strokes for entry in round_player.score_entries if entry.strokes is not None]
    return sum(strokes) if strokes else None


def _round_pars(round_obj):
    return "".join(str(hole.par) for hole in round_holes(round_obj))


def match_garmin_scorecard(round_obj, round_player, payload):
    local_start = round_obj.started_at
    local_course_tokens = _course_tokens(round_obj.course.name)
    local_holes = len(round_holes(round_obj))
    local_total = _round_total(round_player)
    local_pars = _round_pars(round_obj)
    candidates = []

    for summary in _garmin_summaries(payload):
        if summary.get("roundInProgress"):
            continue
        if int(summary.get("holesCompleted") or 0) != local_holes:
            continue
        if local_total is not None and int(summary.get("strokes") or -1) != local_total:
            continue
        garmin_pars = str(summary.get("holePars") or "")
        if garmin_pars and len(garmin_pars) == len(local_pars) and garmin_pars != local_pars:
            continue

        garmin_start = _parse_garmin_start(summary.get("startTime"))
        if not garmin_start or garmin_start.date() != local_start.date():
            continue
        time_delta = abs(garmin_start - local_start)
        if time_delta > MAX_START_TIME_DELTA:
            continue

        garmin_course_tokens = _course_tokens(summary.get("courseName"))
        common_tokens = local_course_tokens & garmin_course_tokens
        if local_course_tokens and garmin_course_tokens and not common_tokens:
            continue
        similarity = len(common_tokens) / max(len(local_course_tokens | garmin_course_tokens), 1)
        candidates.append((time_delta, -similarity, summary))

    if not candidates:
        raise GarminGolfSyncError("Fant ingen Garmin-runde som matcher dato, bane, hull og score.")

    candidates.sort(key=lambda item: (item[0], item[1]))
    best = candidates[0]
    if len(candidates) > 1 and abs(candidates[1][0] - best[0]) <= timedelta(minutes=10):
        raise GarminGolfSyncError("Fant flere mulige Garmin-runder. Rundene ligger for tett til å velge trygt.")
    return best[2]


def _first_tee_shot(payload, hole_number):
    hole_rows = payload.get("holeShots") if isinstance(payload, dict) else None
    if not isinstance(hole_rows, list):
        return None, {}
    hole_row = next((row for row in hole_rows if int(row.get("holeNumber") or 0) == hole_number), None)
    if not hole_row:
        return None, {}
    shots = [shot for shot in (hole_row.get("shots") or []) if not shot.get("excludeFromStats")]
    tee_shot = next((shot for shot in shots if int(shot.get("shotOrder") or 0) == 1), None)
    if not tee_shot:
        tee_shot = next((shot for shot in shots if shot.get("shotType") == "TEE"), None)
    club_details = {
        int(row.get("id") or 0): row
        for row in (payload.get("clubDetails") or [])
        if isinstance(row, dict)
    }
    return tee_shot, club_details


def _club_for_garmin_type(club_type_id):
    mapped = GARMIN_CLUB_TYPE_MAP.get(int(club_type_id or 0))
    if not mapped:
        return None
    name, sort_order = mapped
    club = Club.query.filter(func.lower(Club.name) == name.lower()).first()
    if not club:
        club = Club(name=name, sort_order=sort_order)
        db.session.add(club)
        db.session.flush()
    return club


def sync_round_from_garmin(round_obj, round_player, user, client=None):
    if round_obj.status != "finished":
        raise GarminGolfSyncError("Runden må være fullført før Garmin-data kan hentes.")
    if round_player.round_id != round_obj.id:
        raise GarminGolfSyncError("Spilleren tilhører ikke denne runden.")

    client = client or _garmin_client_for_user(user)
    try:
        summary_payload = client.get_golf_summary(0, 50)
        matched = match_garmin_scorecard(round_obj, round_player, summary_payload)
    except GarminGolfSyncError:
        raise
    except Exception as exc:
        raise GarminGolfSyncError("Kunne ikke hente golfrunder fra Garmin Connect.") from exc

    entries = {entry.hole_number: entry for entry in round_player.score_entries}
    target_holes = [hole for hole in round_holes(round_obj) if hole.par in (4, 5)]
    distances_updated = 0
    clubs_updated = 0
    unmapped_clubs = 0

    for hole in target_holes:
        entry = entries.get(hole.hole_number)
        if not entry:
            continue
        try:
            shot_payload = client.get_golf_shot_data(matched["id"], str(hole.hole_number))
        except Exception as exc:
            raise GarminGolfSyncError(f"Kunne ikke hente Garmin-slag for hull {hole.hole_number}.") from exc

        tee_shot, club_details = _first_tee_shot(shot_payload, hole.hole_number)
        if not tee_shot:
            continue
        meters = tee_shot.get("meters")
        try:
            distance_m = int(round(float(meters)))
        except (TypeError, ValueError):
            distance_m = 0
        if 1 <= distance_m <= 500:
            stat = entry.detailed_stat
            if not stat:
                stat = ScoreStat(score_entry=entry)
                db.session.add(stat)
            stat.drive_distance_m = distance_m
            distances_updated += 1

        club_id = int(tee_shot.get("clubId") or 0)
        club_type_id = int((club_details.get(club_id) or {}).get("clubTypeId") or 0)
        if club_type_id:
            club = _club_for_garmin_type(club_type_id)
            if club:
                entry.tee_club = club
                clubs_updated += 1
            else:
                unmapped_clubs += 1

    round_player.tracks_stats = True
    sync_row = GarminRoundSync.query.filter_by(round_id=round_obj.id).first()
    if not sync_row:
        sync_row = GarminRoundSync(round_id=round_obj.id, user_id=user.id, scorecard_id=int(matched["id"]))
        db.session.add(sync_row)
    sync_row.user_id = user.id
    sync_row.scorecard_id = int(matched["id"])
    sync_row.matched_course_name = (matched.get("courseName") or "")[:255]
    sync_row.distances_updated = distances_updated
    sync_row.clubs_updated = clubs_updated
    sync_row.synced_at = server_now()

    return {
        "scorecard_id": int(matched["id"]),
        "course_name": matched.get("courseName") or "",
        "distances_updated": distances_updated,
        "clubs_updated": clubs_updated,
        "unmapped_clubs": unmapped_clubs,
    }
