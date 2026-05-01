from flask import Blueprint, g, render_template

from models import CourseHole, Round, RoundPlayer, ScoreEntry, ScoreStat
from routes.auth import login_required

profile_bp = Blueprint("profile", __name__)


def _percent(numerator, denominator):
    if denominator == 0:
        return None
    return round((numerator / denominator) * 100, 1)


def _avg(values):
    if not values:
        return None
    return round(sum(values) / len(values), 2)


@profile_bp.route("/me")
@login_required
def me():
    player = g.current_user.player
    round_players = (
        RoundPlayer.query.filter_by(player_id=player.id)
        .join(Round)
        .order_by(Round.started_at.desc())
        .all()
    )

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
    )
