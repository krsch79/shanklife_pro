from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func

from extensions import db
from models import Club, CourseTee, Player, Round, RoundPlayer, ScoreEntry, ScoreStat, User
from routes.auth import login_required
from routes.rounds import _create_round, _parse_hcp, _parse_tee, build_course_tee_options
from services.balletour import get_balletour_memberships, get_balletour_series, is_balletour_player
from services.balletour_test_db import (
    balletour_data_context,
    current_balletour_database_view,
    test_database_exists,
)
from services.version import APP_VERSION

balletour_bp = Blueprint("balletour", __name__, url_prefix="/balletour")


def _balletour_or_404():
    series = get_balletour_series()
    if not series or not series.course:
        abort(404)
    return series


def _require_balletour_player():
    if not is_balletour_player(g.get("current_user")):
        abort(403)


def _balletour_database_context():
    return {
        "balletour_database_view": current_balletour_database_view(),
        "balletour_test_database_available": test_database_exists(),
    }


def _player_display_name(player):
    if player.name == "Christian H":
        return "Christian"
    if player.name == "Kristian S":
        return "Kristian"
    return player.name


def _balletour_new_round_state(series, players):
    course = series.course
    current_player = g.current_user.player
    selected_course_id = str(course.id)
    course_tee_options = build_course_tee_options([course])
    player_hcps = {str(player.id): str(player.default_hcp) for player in players}
    player_genders = {str(player.id): player.gender for player in players}
    yellow_tee = next((tee for tee in course.tees if "gul" in tee.name.lower()), None)
    default_tee = str(yellow_tee.id) if yellow_tee else ""

    other_slots = []
    for i in range(2, 5):
        other_slots.append({
            "slot": i,
            "selected_player": request.form.get(f"player_slot_{i}", "").strip(),
            "existing_hcp": request.form.get(f"hcp_existing_{i}", "").strip(),
            "existing_tee": request.form.get(f"tee_existing_{i}", default_tee).strip(),
        })

    return render_template(
        "balletour_new_round.html",
        series=series,
        course=course,
        players=players,
        current_player=current_player,
        selected_course_id=selected_course_id,
        self_hcp=request.form.get("self_hcp", str(current_player.default_hcp)).strip(),
        self_tee=request.form.get("self_tee", default_tee).strip(),
        other_slots=other_slots,
        course_tee_options=course_tee_options,
        player_hcps=player_hcps,
        player_genders=player_genders,
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


def _score_vs_par(total, par):
    diff = total - par
    if diff == 0:
        return "E"
    return f"+{diff}" if diff > 0 else str(diff)


def _best_hole_score_table(series, memberships):
    players = [membership.player for membership in memberships]
    player_ids = [player.id for player in players]
    best_scores = {}

    if player_ids:
        rows = (
            db.session.query(
                RoundPlayer.player_id,
                ScoreEntry.hole_number,
                func.min(ScoreEntry.strokes),
            )
            .join(ScoreEntry, ScoreEntry.round_player_id == RoundPlayer.id)
            .join(Round, Round.id == RoundPlayer.round_id)
            .filter(Round.course_id == series.course_id)
            .filter(Round.status == "finished")
            .filter(RoundPlayer.player_id.in_(player_ids))
            .filter(ScoreEntry.strokes.isnot(None))
            .group_by(RoundPlayer.player_id, ScoreEntry.hole_number)
            .all()
        )
        best_scores = {
            (player_id, hole_number): best_score
            for player_id, hole_number, best_score in rows
        }

    holes = list(series.course.holes)
    best_by_hole = {}
    totals = {player.id: 0 for player in players}
    complete_totals = {player.id: True for player in players}

    for hole in holes:
        row_scores = []
        for player in players:
            score = best_scores.get((player.id, hole.hole_number))
            if score is None:
                complete_totals[player.id] = False
            else:
                row_scores.append(score)
        best_by_hole[hole.hole_number] = min(row_scores) if row_scores else None

    player_rows = []
    for player in players:
        cells = []
        for hole in holes:
            score = best_scores.get((player.id, hole.hole_number))
            if score is not None:
                totals[player.id] += score
            cells.append({
                "hole_number": hole.hole_number,
                "score": score,
                "is_best": score is not None and score == best_by_hole.get(hole.hole_number),
                "shape_class": _score_shape_class(score, hole.par),
            })
        player_rows.append({
            "player": player,
            "cells": cells,
        })

    total_cells = []
    total_values = [totals[player.id] for player in players if complete_totals[player.id]]
    best_total = min(total_values) if total_values else None
    for player in players:
        total = totals[player.id] if complete_totals[player.id] else None
        total_cells.append({
            "player_id": player.id,
            "score": total,
            "is_best": total is not None and total == best_total,
        })

    total_by_player = {
        cell["player_id"]: cell["score"]
        for cell in total_cells
    }
    player_rows.sort(
        key=lambda row: (
            total_by_player.get(row["player"].id) is None,
            total_by_player.get(row["player"].id) if total_by_player.get(row["player"].id) is not None else 9999,
            row["player"].name,
        )
    )
    total_cell_by_player = {cell["player_id"]: cell for cell in total_cells}
    total_cells = [total_cell_by_player[row["player"].id] for row in player_rows]

    return {
        "players": players,
        "holes": holes,
        "player_rows": player_rows,
        "total_cells": total_cells,
    }


def _balletour_leaderboard_rows(series, memberships):
    course_par = sum(hole.par for hole in series.course.holes)
    players = {membership.player_id: membership.player for membership in memberships}
    rows = []

    for player_id, player in players.items():
        round_players = (
            RoundPlayer.query.join(Round)
            .filter(Round.course_id == series.course_id)
            .filter(Round.status == "finished")
            .filter(RoundPlayer.player_id == player_id)
            .all()
        )
        totals = []
        for round_player in round_players:
            entries = [entry for entry in round_player.score_entries if entry.strokes is not None]
            if len(entries) == series.course.hole_count:
                totals.append(sum(entry.strokes for entry in entries))
        if not totals:
            rows.append({
                "player": player,
                "rounds_played": 0,
                "total_strokes": None,
                "total_vs_par": None,
                "total_vs_par_display": "-",
                "avg_round": None,
                "best_round": None,
                "qualified": False,
            })
            continue
        total_strokes = sum(totals)
        rounds_played = len(totals)
        total_par = rounds_played * course_par
        rows.append({
            "player": player,
            "rounds_played": rounds_played,
            "total_strokes": total_strokes,
            "total_vs_par": total_strokes - total_par,
            "total_vs_par_display": _score_vs_par(total_strokes, total_par),
            "avg_round": round(total_strokes / rounds_played, 2),
            "best_round": min(totals),
            "qualified": rounds_played >= series.min_qualifying_rounds,
        })

    rows.sort(key=lambda row: (
        row["total_vs_par"] is None,
        row["total_vs_par"] if row["total_vs_par"] is not None else 9999,
        row["avg_round"] if row["avg_round"] is not None else 9999,
        row["player"].name,
    ))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def _percent(numerator, denominator):
    if denominator == 0:
        return None
    return round((numerator / denominator) * 100, 1)


def _avg(values):
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _green_parts(raw_value):
    raw_value = (raw_value or "hit").strip()
    status, separator, direction_text = raw_value.partition(":")
    if status not in ("hit", "miss", "bunker"):
        if status in ("left", "right", "short", "long"):
            return "miss", {status}
        return "hit", set()
    directions = set()
    if separator:
        directions = {
            item for item in direction_text.split(",")
            if item in ("pin", "left", "right", "short", "long")
        }
    return status, directions


def _green_point(status, directions, index):
    if "pin" in directions:
        x, y = 50, 50
    else:
        if "long" in directions:
            vertical = "long"
        elif "short" in directions:
            vertical = "short"
        else:
            vertical = ""

        if "left" in directions:
            horizontal = "left"
        elif "right" in directions:
            horizontal = "right"
        else:
            horizontal = ""

        direction_key = "_".join(part for part in (vertical, horizontal) if part) or "center"
        if direction_key == "center" and status in ("bunker", "miss"):
            direction_key = ("long", "right", "short", "left")[index % 4]

        anchors = {
            "hit": {
                "center": (50, 50),
                "long": (50, 39),
                "short": (50, 61),
                "left": (39, 50),
                "right": (61, 50),
                "long_left": (41, 41),
                "long_right": (59, 41),
                "short_left": (41, 60),
                "short_right": (59, 60),
            },
            "bunker": {
                "long": (50, 19),
                "short": (50, 81),
                "left": (20, 50),
                "right": (80, 50),
                "long_left": (30, 20),
                "long_right": (70, 20),
                "short_left": (30, 80),
                "short_right": (70, 80),
                "center": (50, 19),
            },
            "miss": {
                "long": (50, 10),
                "short": (50, 91),
                "left": (10, 50),
                "right": (90, 50),
                "long_left": (22, 10),
                "long_right": (78, 10),
                "short_left": (22, 90),
                "short_right": (78, 90),
                "center": (50, 91),
            },
        }
        x, y = anchors.get(status, anchors["hit"]).get(direction_key, anchors["hit"]["center"])

    jitter_range = 5 if status == "hit" else 3
    jitter_x = ((index * 17) % jitter_range) - (jitter_range // 2)
    jitter_y = ((index * 29) % jitter_range) - (jitter_range // 2)
    return {
        "status": status,
        "x": max(8, min(92, x + jitter_x)),
        "y": max(8, min(92, y + jitter_y)),
    }


def _green_bucket(status, directions):
    if status == "hit":
        return "hit"
    if status == "bunker":
        return "bunker"
    vertical = "short" if "short" in directions else "long" if "long" in directions else ""
    horizontal = "left" if "left" in directions else "right" if "right" in directions else ""
    if vertical and horizontal:
        return f"miss_{horizontal}_{vertical}"
    if horizontal:
        return f"miss_{horizontal}"
    if vertical:
        return f"miss_{vertical}"
    return "miss"


def _completed_balletour_round_players(series, player_ids=None):
    query = (
        RoundPlayer.query.join(Round)
        .filter(Round.course_id == series.course_id)
        .filter(Round.status == "finished")
    )
    if player_ids:
        query = query.filter(RoundPlayer.player_id.in_(player_ids))

    round_players = query.all()
    round_player_ids = [round_player.id for round_player in round_players]
    entries = (
        ScoreEntry.query.filter(ScoreEntry.round_player_id.in_(round_player_ids)).all()
        if round_player_ids else []
    )
    entries_by_round_player = {}
    for entry in entries:
        entries_by_round_player.setdefault(entry.round_player_id, []).append(entry)

    completed = []
    for round_player in round_players:
        scored_entries = [
            entry for entry in entries_by_round_player.get(round_player.id, [])
            if entry.strokes is not None
        ]
        if len(scored_entries) == series.course.hole_count:
            completed.append(round_player)
    return completed


def _avg_by_key(rows):
    totals = {}
    counts = {}
    for key, value in rows:
        if value is None:
            continue
        totals[key] = totals.get(key, 0) + value
        counts[key] = counts.get(key, 0) + 1
    return {
        key: totals[key] / counts[key]
        for key in totals
        if counts[key]
    }


def _balletour_sg_baselines(series, memberships):
    player_ids = [membership.player_id for membership in memberships]
    completed_round_players = _completed_balletour_round_players(series, player_ids)
    round_player_ids = [round_player.id for round_player in completed_round_players]
    rows = (
        db.session.query(ScoreEntry, ScoreStat)
        .outerjoin(ScoreStat, ScoreStat.score_entry_id == ScoreEntry.id)
        .filter(ScoreEntry.round_player_id.in_(round_player_ids))
        .filter(ScoreEntry.strokes.isnot(None))
        .all()
        if round_player_ids else []
    )

    strokes_by_hole = []
    putts_by_hole = []
    non_putts_by_hole = []
    strokes_by_green_result = []
    for entry, stat in rows:
        strokes_by_hole.append((entry.hole_number, entry.strokes))
        if stat and stat.putts is not None:
            putts_by_hole.append((entry.hole_number, stat.putts))
            non_putts_by_hole.append((entry.hole_number, entry.strokes - stat.putts))
        if stat and stat.fairway_result:
            status, directions = _green_parts(stat.fairway_result)
            strokes_by_green_result.append(((entry.hole_number, _green_bucket(status, directions)), entry.strokes))

    return {
        "strokes_by_hole": _avg_by_key(strokes_by_hole),
        "putts_by_hole": _avg_by_key(putts_by_hole),
        "non_putts_by_hole": _avg_by_key(non_putts_by_hole),
        "strokes_by_green_result": _avg_by_key(strokes_by_green_result),
    }


def _strokes_gained_stats(series, memberships, selected_player, selected_hole_number=None, baselines=None):
    if not selected_player:
        return {}

    baselines = baselines or _balletour_sg_baselines(series, memberships)
    completed_round_players = _completed_balletour_round_players(series, [selected_player.id])
    round_player_ids = [round_player.id for round_player in completed_round_players]
    stats_rows = (
        db.session.query(ScoreEntry, ScoreStat)
        .outerjoin(ScoreStat, ScoreStat.score_entry_id == ScoreEntry.id)
        .filter(ScoreEntry.round_player_id.in_(round_player_ids))
        .filter(ScoreEntry.strokes.isnot(None))
        .all()
        if round_player_ids else []
    )
    if selected_hole_number:
        stats_rows = [
            (entry, stat) for entry, stat in stats_rows
            if entry.hole_number == selected_hole_number
        ]

    totals = {
        "total": 0,
        "putting": 0,
        "tee_to_green": 0,
        "green_result": 0,
    }
    counts = {
        "total": 0,
        "putting": 0,
        "tee_to_green": 0,
        "green_result": 0,
    }

    for entry, stat in stats_rows:
        hole_avg = baselines["strokes_by_hole"].get(entry.hole_number)
        if hole_avg is not None:
            totals["total"] += hole_avg - entry.strokes
            counts["total"] += 1

        if stat and stat.putts is not None:
            putt_avg = baselines["putts_by_hole"].get(entry.hole_number)
            if putt_avg is not None:
                totals["putting"] += putt_avg - stat.putts
                counts["putting"] += 1
            non_putt_avg = baselines["non_putts_by_hole"].get(entry.hole_number)
            if non_putt_avg is not None:
                totals["tee_to_green"] += non_putt_avg - (entry.strokes - stat.putts)
                counts["tee_to_green"] += 1

        if stat and stat.fairway_result and hole_avg is not None:
            status, directions = _green_parts(stat.fairway_result)
            bucket = _green_bucket(status, directions)
            result_avg = baselines["strokes_by_green_result"].get((entry.hole_number, bucket))
            if result_avg is not None:
                totals["green_result"] += hole_avg - result_avg
                counts["green_result"] += 1

    divisor = len({entry.round_id for entry, stat in stats_rows}) if not selected_hole_number else counts["total"]
    if not divisor:
        divisor = None

    def per_unit(key):
        if not divisor or not counts[key]:
            return None
        return round(totals[key] / divisor, 2)

    return {
        "unit_label": "per hull" if selected_hole_number else "per runde",
        "total": per_unit("total"),
        "tee_to_green": per_unit("tee_to_green"),
        "putting": per_unit("putting"),
        "green_result": per_unit("green_result"),
    }


def _balletour_player_stats(series, memberships, selected_player, selected_hole_number=None):
    holes = list(series.course.holes)
    course_par = sum(hole.par for hole in holes)
    par_by_hole = {hole.hole_number: hole.par for hole in holes}
    player_ids = [membership.player_id for membership in memberships]
    selected_player = selected_player or (memberships[0].player if memberships else None)
    if not selected_player:
        return {}

    round_players = (
        RoundPlayer.query.join(Round)
        .filter(Round.course_id == series.course_id)
        .filter(RoundPlayer.player_id == selected_player.id)
        .filter(Round.status == "finished")
        .order_by(Round.started_at.desc())
        .all()
    )
    round_ids = [round_player.round_id for round_player in round_players]
    round_player_ids = [round_player.id for round_player in round_players]
    entries = (
        ScoreEntry.query.filter(ScoreEntry.round_player_id.in_(round_player_ids)).all()
        if round_player_ids else []
    )

    completed_totals = []
    completed_round_ids = set()
    entries_by_round = {}
    for entry in entries:
        entries_by_round.setdefault(entry.round_id, []).append(entry)
    for round_player in round_players:
        round_entries = entries_by_round.get(round_player.round_id, [])
        scored_entries = [entry for entry in round_entries if entry.strokes is not None]
        if len(scored_entries) == series.course.hole_count:
            completed_totals.append(sum(entry.strokes for entry in scored_entries))
            completed_round_ids.add(round_player.round_id)

    scored_entries = [entry for entry in entries if entry.strokes is not None]
    score_diffs = [
        entry.strokes - par_by_hole.get(entry.hole_number, 3)
        for entry in scored_entries
    ]
    birdies_or_better = sum(1 for diff in score_diffs if diff < 0)
    pars = sum(1 for diff in score_diffs if diff == 0)
    bogeys_or_worse = sum(1 for diff in score_diffs if diff > 0)

    best_by_hole = {}
    for hole in holes:
        values = [
            entry.strokes for entry in scored_entries
            if entry.hole_number == hole.hole_number
        ]
        best_by_hole[hole.hole_number] = min(values) if values else None

    stats_query = (
        db.session.query(ScoreStat, ScoreEntry)
        .join(ScoreEntry, ScoreStat.score_entry_id == ScoreEntry.id)
        .filter(ScoreEntry.round_player_id.in_(round_player_ids))
    )
    if selected_hole_number:
        stats_query = stats_query.filter(ScoreEntry.hole_number == selected_hole_number)
    stats_rows = stats_query.all() if round_player_ids else []
    green_counts = {"hit": 0, "miss": 0, "bunker": 0, "pin": 0, "left": 0, "right": 0, "short": 0, "long": 0}
    green_bucket_labels = [
        ("hit", "Greentreff"),
        ("miss_right_short", "Miss høyre kort"),
        ("miss_right_long", "Miss høyre lang"),
        ("miss_right", "Miss høyre"),
        ("miss_left_short", "Miss venstre kort"),
        ("miss_left_long", "Miss venstre lang"),
        ("miss_left", "Miss venstre"),
        ("miss_short", "Miss kort"),
        ("miss_long", "Miss lang"),
        ("miss", "Miss uten retning"),
        ("bunker", "Bunker"),
    ]
    green_bucket_counts = {key: 0 for key, label in green_bucket_labels}
    green_points = []
    sand_save_attempts = 0
    sand_saves = 0
    for index, (stat, entry) in enumerate(stats_rows):
        status, directions = _green_parts(stat.fairway_result)
        green_counts[status] += 1
        bucket = _green_bucket(status, directions)
        green_bucket_counts[bucket] = green_bucket_counts.get(bucket, 0) + 1
        if "pin" in directions:
            green_counts["pin"] += 1
        for direction in ("left", "right", "short", "long"):
            if direction in directions:
                green_counts[direction] += 1
        green_points.append(_green_point(status, directions, index))
        if status == "bunker":
            sand_save_attempts += 1
            if entry.strokes is not None and entry.strokes <= par_by_hole.get(entry.hole_number, 3):
                sand_saves += 1

    club_rows = (
        db.session.query(
            Club.name,
            func.count(ScoreEntry.id),
            func.avg(ScoreEntry.strokes),
        )
        .join(ScoreEntry, ScoreEntry.tee_club_id == Club.id)
        .filter(ScoreEntry.round_player_id.in_(round_player_ids))
        .filter(ScoreEntry.strokes.isnot(None))
        .group_by(Club.id, Club.name, Club.sort_order)
        .order_by(func.avg(ScoreEntry.strokes).asc(), func.count(ScoreEntry.id).desc(), Club.sort_order.asc())
        .all()
        if round_player_ids else []
    )
    completed_round_player_ids = [
        round_player.id
        for round_player in round_players
        if round_player.round_id in completed_round_ids
    ]
    completed_stats_rows = (
        db.session.query(ScoreStat, ScoreEntry)
        .join(ScoreEntry, ScoreStat.score_entry_id == ScoreEntry.id)
        .filter(ScoreEntry.round_player_id.in_(completed_round_player_ids))
        .all()
        if completed_round_player_ids else []
    )
    putt_distance_by_round = {round_id: 0 for round_id in completed_round_ids}
    for stat, entry in completed_stats_rows:
        if stat.last_putt_distance_m is not None:
            putt_distance_by_round[entry.round_id] += stat.last_putt_distance_m
    avg_putt_meters_per_round = (
        round(sum(putt_distance_by_round.values()) / len(putt_distance_by_round), 2)
        if putt_distance_by_round else None
    )

    green_attempts = len(stats_rows)
    green_distribution = [
        {
            "key": key,
            "label": label,
            "count": green_bucket_counts.get(key, 0),
            "percent": _percent(green_bucket_counts.get(key, 0), green_attempts),
        }
        for key, label in green_bucket_labels
        if green_bucket_counts.get(key, 0) or key in ("hit", "bunker")
    ]

    strokes_gained = _strokes_gained_stats(series, memberships, selected_player, selected_hole_number)

    return {
        "selected_player": selected_player,
        "selected_hole_number": selected_hole_number,
        "holes": holes,
        "round_count": len(round_players),
        "completed_round_count": len(completed_totals),
        "avg_round": round(sum(completed_totals) / len(completed_totals), 1) if completed_totals else None,
        "best_round": min(completed_totals) if completed_totals else None,
        "best_round_vs_par": min(completed_totals) - course_par if completed_totals else None,
        "scored_holes": len(scored_entries),
        "birdies_or_better": birdies_or_better,
        "pars": pars,
        "bogeys_or_worse": bogeys_or_worse,
        "green_counts": green_counts,
        "green_attempts": len(stats_rows),
        "green_hit_percent": _percent(green_counts["hit"], len(stats_rows)),
        "bunker_percent": _percent(green_counts["bunker"], len(stats_rows)),
        "sand_save_attempts": sand_save_attempts,
        "sand_saves": sand_saves,
        "sand_save_percent": _percent(sand_saves, sand_save_attempts),
        "avg_putts": _avg([stat.putts for stat, entry in stats_rows if stat.putts is not None]),
        "avg_last_putt_distance": _avg([stat.last_putt_distance_m for stat, entry in stats_rows if stat.last_putt_distance_m is not None]),
        "avg_putt_meters_per_round": avg_putt_meters_per_round,
        "strokes_gained": strokes_gained,
        "green_points": green_points[-160:],
        "green_distribution": green_distribution,
        "best_by_hole": best_by_hole,
        "club_rows": [
            {"name": name, "count": count, "avg": round(avg, 2)}
            for name, count, avg in club_rows
        ],
        "player_ids": player_ids,
    }


def _balletour_all_player_stats(series, memberships):
    baselines = _balletour_sg_baselines(series, memberships)
    rows = []
    for membership in memberships:
        player = membership.player
        stats = _balletour_player_stats(series, memberships, player)
        strokes_gained = _strokes_gained_stats(series, memberships, player, baselines=baselines)
        rows.append({
            "player": player,
            "completed_round_count": stats.get("completed_round_count"),
            "avg_round": stats.get("avg_round"),
            "best_round": stats.get("best_round"),
            "green_hit_percent": stats.get("green_hit_percent"),
            "bunker_percent": stats.get("bunker_percent"),
            "sand_save_percent": stats.get("sand_save_percent"),
            "avg_putts": stats.get("avg_putts"),
            "avg_last_putt_distance": stats.get("avg_last_putt_distance"),
            "avg_putt_meters_per_round": stats.get("avg_putt_meters_per_round"),
            "birdies_or_better": stats.get("birdies_or_better"),
            "pars": stats.get("pars"),
            "bogeys_or_worse": stats.get("bogeys_or_worse"),
            "strokes_gained": strokes_gained,
        })
    rows.sort(key=lambda row: (
        row["avg_round"] is None,
        row["avg_round"] if row["avg_round"] is not None else 9999,
        row["player"].name,
    ))
    return rows


def _round_score_card(round_obj):
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
        has_total = False
        for hole in holes:
            entry = entries.get(hole.hole_number)
            score = entry.strokes if entry else None
            if score is not None:
                total += score
                has_total = True
            cells.append({
                "hole_number": hole.hole_number,
                "score": score,
                "shape_class": _score_shape_class(score, par_by_hole.get(hole.hole_number, 3)),
            })
        rows.append({
            "player_name": round_player.player_name_snapshot,
            "cells": cells,
            "total": total if has_total else None,
        })
    return {
        "round": round_obj,
        "holes": holes,
        "rows": rows,
    }


@balletour_bp.route("/")
@login_required
def index():
    _require_balletour_player()
    with balletour_data_context():
        series = _balletour_or_404()
        memberships = get_balletour_memberships()
        round_count = Round.query.filter_by(course_id=series.course_id).count()
        finished_round_count = Round.query.filter_by(
            course_id=series.course_id,
            status="finished",
        ).count()
        best_hole_score_table = _best_hole_score_table(series, memberships)
        leaderboard_rows = _balletour_leaderboard_rows(series, memberships)
        return render_template(
            "balletour_index.html",
            series=series,
            memberships=memberships,
            round_count=round_count,
            finished_round_count=finished_round_count,
            best_hole_score_table=best_hole_score_table,
            leaderboard_rows=leaderboard_rows,
            display_name=_player_display_name,
            app_version=APP_VERSION,
            **_balletour_database_context(),
        )


@balletour_bp.route("/new-round", methods=["GET", "POST"])
@login_required
def new_round():
    _require_balletour_player()
    series = _balletour_or_404()
    course = series.course
    players = [membership.player for membership in get_balletour_memberships()]
    allowed_player_ids = {player.id for player in players}
    course_tees = {tee.id: tee for tee in course.tees}

    if not course_tees:
        flash("BalleTour-banen har ingen tees. Legg til minst ett tee-sett først.", "error")
        return redirect(url_for("balletour.index"))

    if request.method == "POST":
        current_player = g.current_user.player
        try:
            self_hcp = _parse_hcp(request.form.get("self_hcp", "").strip(), current_player.name)
            self_tee_id = _parse_tee(request.form.get("self_tee", "").strip(), course_tees, current_player.name)
        except ValueError as exc:
            flash(str(exc), "error")
            return _balletour_new_round_state(series, players)

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
            player_id_raw = request.form.get(f"player_slot_{i}", "").strip()
            if not player_id_raw:
                continue

            try:
                player_id = int(player_id_raw)
            except ValueError:
                flash(f"Ugyldig spiller-valg i slot {i}.", "error")
                return _balletour_new_round_state(series, players)

            if player_id not in allowed_player_ids:
                flash("Du kan bare velge BalleTour-spillere.", "error")
                return _balletour_new_round_state(series, players)

            player = Player.query.get(player_id)
            if not player:
                flash(f"Valgt spiller finnes ikke i slot {i}.", "error")
                return _balletour_new_round_state(series, players)

            try:
                round_hcp = _parse_hcp(request.form.get(f"hcp_existing_{i}", "").strip(), player.name)
                selected_tee_id = _parse_tee(
                    request.form.get(f"tee_existing_{i}", "").strip(),
                    course_tees,
                    player.name,
                )
            except ValueError as exc:
                flash(str(exc), "error")
                return _balletour_new_round_state(series, players)

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

        names_lower = [payload["player_name"].lower() for payload in round_players_payload]
        if len(names_lower) != len(set(names_lower)):
            flash("Du kan ikke ha samme spiller mer enn én gang i samme runde.", "error")
            return _balletour_new_round_state(series, players)

        round_obj = _create_round(course, round_players_payload, stats_user_id=g.current_user.id)
        db.session.commit()
        flash("BalleTour-runde opprettet.", "success")
        return redirect(url_for("rounds.round_hole", round_id=round_obj.id, hole_number=1))

    return _balletour_new_round_state(series, players)


@balletour_bp.route("/rounds")
@login_required
def rounds():
    return finished_rounds()


@balletour_bp.route("/rounds/ongoing")
@login_required
def ongoing_rounds():
    _require_balletour_player()
    with balletour_data_context():
        series = _balletour_or_404()
        rows = (
            Round.query.filter_by(course_id=series.course_id, status="ongoing")
            .order_by(Round.started_at.desc())
            .all()
        )
        return render_template(
            "balletour_ongoing_rounds.html",
            series=series,
            rounds=rows,
            **_balletour_database_context(),
        )


@balletour_bp.route("/rounds/finished")
@login_required
def finished_rounds():
    _require_balletour_player()
    with balletour_data_context():
        series = _balletour_or_404()
        rows = (
            Round.query.filter_by(course_id=series.course_id, status="finished")
            .order_by(Round.started_at.desc())
            .all()
        )
        score_cards = [_round_score_card(round_obj) for round_obj in rows]
        return render_template(
            "balletour_rounds.html",
            series=series,
            score_cards=score_cards,
            **_balletour_database_context(),
        )


@balletour_bp.route("/stats")
@login_required
def stats():
    _require_balletour_player()
    with balletour_data_context():
        series = _balletour_or_404()
        memberships = get_balletour_memberships()
        players = [membership.player for membership in memberships]
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

        player_stats = _balletour_player_stats(series, memberships, selected_player, selected_hole_number)
        return render_template(
            "balletour_stats.html",
            series=series,
            memberships=memberships,
            players=players,
            selected_player=selected_player,
            selected_hole_number=selected_hole_number,
            stats=player_stats,
            display_name=_player_display_name,
            **_balletour_database_context(),
        )


@balletour_bp.route("/stats/all")
@login_required
def all_stats():
    _require_balletour_player()
    with balletour_data_context():
        series = _balletour_or_404()
        memberships = get_balletour_memberships()
        rows = _balletour_all_player_stats(series, memberships)
        return render_template(
            "balletour_all_stats.html",
            series=series,
            rows=rows,
            display_name=_player_display_name,
            **_balletour_database_context(),
        )


@balletour_bp.route("/players")
@login_required
def players():
    _require_balletour_player()
    with balletour_data_context():
        series = _balletour_or_404()
        memberships = get_balletour_memberships()
        users_by_player_id = {}
        for user in User.query.join(Player).order_by(func.lower(User.username)).all():
            users_by_player_id.setdefault(user.player_id, []).append(user)

        return render_template(
            "balletour_players.html",
            series=series,
            memberships=memberships,
            users_by_player_id=users_by_player_id,
            display_name=_player_display_name,
            **_balletour_database_context(),
        )
