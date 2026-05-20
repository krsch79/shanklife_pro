from datetime import datetime

from sqlalchemy import func

from models import CourseHole, Player, Round, RoundPlayer, ScoreEntry, ScoreStat
from services.balletour import get_balletour_memberships, get_balletour_series
from services.tee_filters import selected_tee_key, tee_ids_for_key
from services.time import format_server_datetime


def _display_name(player):
    if player.name == "Christian H":
        return "Christian"
    if player.name == "Kristian S":
        return "Kristian"
    return player.name


def _to_par_display(value):
    if value is None:
        return "-"
    if value == 0:
        return "E"
    return f"+{value}" if value > 0 else str(value)


def _round_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _series_or_error():
    series = get_balletour_series()
    if not series or not series.course:
        raise ValueError("Fant ikke BalleTour-serien eller tilhørende bane.")
    return series


def _tee_context(series, tee):
    tee_key = selected_tee_key(tee)
    return tee_key, tee_ids_for_key(series.course, tee_key)


def _completed_round_totals(series, player_id, tee_ids=None):
    query = (
        RoundPlayer.query.join(Round)
        .filter(Round.course_id == series.course_id)
        .filter(Round.status == "finished")
        .filter(RoundPlayer.player_id == player_id)
    )
    if tee_ids:
        query = query.filter(RoundPlayer.selected_tee_id.in_(tee_ids))

    totals = []
    for round_player in query.all():
        entries = [entry for entry in round_player.score_entries if entry.strokes is not None]
        if len(entries) == series.course.hole_count:
            totals.append(sum(entry.strokes for entry in entries))
    return totals


def _leaderboard_rows(series, tee_ids=None):
    course_par = sum(hole.par for hole in series.course.holes)
    rows = []

    for membership in get_balletour_memberships():
        player = membership.player
        totals = _completed_round_totals(series, player.id, tee_ids)
        if not totals:
            rows.append(
                {
                    "player_id": player.id,
                    "player_name": _display_name(player),
                    "rounds_played": 0,
                    "total_strokes": None,
                    "total_vs_par": None,
                    "total_vs_par_display": "-",
                    "average_round": None,
                    "best_round": None,
                    "qualified": False,
                }
            )
            continue

        total_strokes = sum(totals)
        total_par = len(totals) * course_par
        rows.append(
            {
                "player_id": player.id,
                "player_name": _display_name(player),
                "rounds_played": len(totals),
                "total_strokes": total_strokes,
                "total_vs_par": total_strokes - total_par,
                "total_vs_par_display": _to_par_display(total_strokes - total_par),
                "average_round": round(total_strokes / len(totals), 2),
                "best_round": min(totals),
                "qualified": len(totals) >= series.min_qualifying_rounds,
            }
        )

    rows.sort(
        key=lambda row: (
            row["total_vs_par"] is None,
            row["total_vs_par"] if row["total_vs_par"] is not None else 999999,
            row["rounds_played"] * -1,
            row["player_name"].lower(),
        )
    )
    for index, row in enumerate(rows, start=1):
        row["rank"] = index if row["rounds_played"] else None
    return rows


def get_balletour_overview(tee="gul"):
    series = _series_or_error()
    tee_key, tee_ids = _tee_context(series, tee)

    round_query = Round.query.join(RoundPlayer).filter(Round.course_id == series.course_id)
    if tee_ids:
        round_query = round_query.filter(RoundPlayer.selected_tee_id.in_(tee_ids))

    finished_round_count = round_query.filter(Round.status == "finished").distinct().count()
    ongoing_round_count = round_query.filter(Round.status == "ongoing").distinct().count()

    return {
        "series": series.name,
        "course": {
            "id": series.course.id,
            "name": series.course.name,
            "hole_count": series.course.hole_count,
            "par": sum(hole.par for hole in series.course.holes),
        },
        "tee": tee_key,
        "player_count": len(get_balletour_memberships()),
        "finished_round_count": finished_round_count,
        "ongoing_round_count": ongoing_round_count,
        "min_qualifying_rounds": series.min_qualifying_rounds,
        "leaderboard": _leaderboard_rows(series, tee_ids),
    }


def list_balletour_players():
    players = []
    for membership in get_balletour_memberships():
        player = membership.player
        players.append(
            {
                "id": player.id,
                "name": player.name,
                "display_name": _display_name(player),
                "default_hcp": player.default_hcp,
                "gender": player.gender,
                "display_order": membership.display_order,
            }
        )
    return {"players": players}


def _find_balletour_player(player_name):
    normalized = (player_name or "").strip().lower()
    if not normalized:
        return None

    for membership in get_balletour_memberships():
        player = membership.player
        names = {player.name.lower(), _display_name(player).lower()}
        if normalized in names:
            return player
    return None


def list_balletour_rounds(status="finished", player_name=None, limit=10, tee="gul"):
    series = _series_or_error()
    tee_key, tee_ids = _tee_context(series, tee)
    status = (status or "finished").strip().lower()
    if status not in {"finished", "ongoing", "all"}:
        raise ValueError("status må være finished, ongoing eller all.")

    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit må være et heltall.") from exc
    limit = max(1, min(limit, 50))

    selected_player = _find_balletour_player(player_name)
    query = Round.query.filter(Round.course_id == series.course_id)
    if status != "all":
        query = query.filter(Round.status == status)
    if tee_ids or selected_player:
        query = query.join(RoundPlayer)
    if tee_ids:
        query = query.filter(RoundPlayer.selected_tee_id.in_(tee_ids))
    if selected_player:
        query = query.filter(RoundPlayer.player_id == selected_player.id)

    rounds = query.distinct().order_by(Round.started_at.desc()).limit(limit).all()
    return {
        "status": status,
        "tee": tee_key,
        "player_name": _display_name(selected_player) if selected_player else None,
        "rounds": [_round_summary(round_obj) for round_obj in rounds],
    }


def _round_summary(round_obj):
    course_par = sum(hole.par for hole in round_obj.course.holes)
    players = []
    for round_player in round_obj.round_players:
        entries = [entry for entry in round_player.score_entries if entry.strokes is not None]
        total = sum(entry.strokes for entry in entries) if entries else None
        complete = len(entries) == round_obj.course.hole_count
        players.append(
            {
                "player_id": round_player.player_id,
                "player_name": _display_name(round_player.player),
                "tee": round_player.selected_tee.name if round_player.selected_tee else None,
                "hcp": round_player.hcp_for_round,
                "completed_holes": len(entries),
                "total_strokes": total if complete else None,
                "to_par": total - course_par if complete and total is not None else None,
                "to_par_display": _to_par_display(total - course_par) if complete and total is not None else "-",
            }
        )

    return {
        "id": round_obj.id,
        "status": round_obj.status,
        "course": round_obj.course.name,
        "started_at": _round_datetime(round_obj.started_at),
        "started_at_display": format_server_datetime(round_obj.started_at),
        "finished_at": _round_datetime(round_obj.finished_at),
        "players": players,
    }


def get_balletour_player_summary(player_name, tee="gul"):
    series = _series_or_error()
    tee_key, tee_ids = _tee_context(series, tee)
    player = _find_balletour_player(player_name)
    if not player:
        raise ValueError("Fant ikke BalleTour-spilleren.")

    totals = _completed_round_totals(series, player.id, tee_ids)
    round_players = (
        RoundPlayer.query.join(Round)
        .filter(Round.course_id == series.course_id)
        .filter(RoundPlayer.player_id == player.id)
    )
    if tee_ids:
        round_players = round_players.filter(RoundPlayer.selected_tee_id.in_(tee_ids))
    round_players = round_players.all()
    round_player_ids = [round_player.id for round_player in round_players]

    score_rows = []
    stats_rows = []
    if round_player_ids:
        score_rows = (
            ScoreEntry.query.join(RoundPlayer, ScoreEntry.round_player_id == RoundPlayer.id)
            .join(Round, ScoreEntry.round_id == Round.id)
            .join(
                CourseHole,
                (CourseHole.course_id == Round.course_id)
                & (CourseHole.hole_number == ScoreEntry.hole_number),
            )
            .outerjoin(ScoreStat, ScoreStat.score_entry_id == ScoreEntry.id)
            .filter(Round.course_id == series.course_id)
            .filter(RoundPlayer.id.in_(round_player_ids))
            .filter(ScoreEntry.strokes.isnot(None))
            .with_entities(ScoreEntry.strokes, CourseHole.par, ScoreStat.putts)
            .all()
        )
        stats_rows = (
            ScoreStat.query.join(ScoreEntry)
            .join(RoundPlayer, ScoreEntry.round_player_id == RoundPlayer.id)
            .filter(RoundPlayer.id.in_(round_player_ids))
            .all()
        )

    scores_by_par = {3: [], 4: [], 5: []}
    gir_hits = 0
    gir_attempts = 0
    for strokes, par, putts in score_rows:
        if par in scores_by_par:
            scores_by_par[par].append(strokes)
        if putts is not None:
            gir_attempts += 1
            if strokes - putts <= par - 2:
                gir_hits += 1

    putts = [row.putts for row in stats_rows if row.putts is not None]
    drive_distances = [row.drive_distance_m for row in stats_rows if row.drive_distance_m is not None]

    return {
        "player": {
            "id": player.id,
            "name": player.name,
            "display_name": _display_name(player),
            "default_hcp": player.default_hcp,
        },
        "tee": tee_key,
        "rounds_played": len(round_players),
        "finished_rounds": len(totals),
        "average_round": round(sum(totals) / len(totals), 1) if totals else None,
        "best_round": min(totals) if totals else None,
        "tracked_holes": len(stats_rows),
        "average_putts": round(sum(putts) / len(putts), 2) if putts else None,
        "average_drive_distance": round(sum(drive_distances) / len(drive_distances), 1) if drive_distances else None,
        "gir_percent": round((gir_hits / gir_attempts) * 100, 1) if gir_attempts else None,
        "average_par_3": _average(scores_by_par[3]),
        "average_par_4": _average(scores_by_par[4]),
        "average_par_5": _average(scores_by_par[5]),
    }


def _average(values):
    if not values:
        return None
    return round(sum(values) / len(values), 2)
