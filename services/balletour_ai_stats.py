import json
import os
from collections import defaultdict

from openai import OpenAI

from extensions import db
from models import Club, CourseHole, Round, RoundPlayer, ScoreEntry, ScoreStat


MAX_RECENT_ROUNDS_PER_PLAYER = 12
MAX_CLUB_ROWS_PER_PLAYER = 12


def ask_balletour_stats_ai(series, memberships, prompt, current_user=None):
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Skriv et spørsmål først.")
    api_key = _openai_api_key()
    if not api_key:
        return {
            "answer": (
                "OpenAI-nøkkel mangler på serveren, så jeg kan ikke svare i chatten akkurat nå. "
                "Statistikkgrunnlaget kan likevel bygges lokalt."
            ),
            "data_context": build_balletour_stats_context(series, memberships, current_user=current_user),
            "used_openai": False,
        }

    data_context = build_balletour_stats_context(series, memberships, current_user=current_user)
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4.1"),
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Du er BalleTour sin statistikkassistent. Svar på norsk, konkret og praktisk. "
                            "Bruk bare tall og observasjoner fra JSON-grunnlaget du får. Ikke finn opp runder, "
                            "spillere eller tall. Hvis datagrunnlaget ikke kan svare på spørsmålet, si hva som "
                            "mangler og foreslå nærmeste relevante analyse. Forklar gjerne kort hvordan du tolker "
                            "tallene, og avslutt med 1-3 praktiske observasjoner når det passer."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Spørsmål fra bruker:\n"
                            f"{prompt}\n\n"
                            "BalleTour-statistikkgrunnlag som JSON:\n"
                            f"{json.dumps(data_context, ensure_ascii=False)}"
                        ),
                    }
                ],
            },
        ],
    )
    return {
        "answer": response.output_text.strip(),
        "data_context": data_context,
        "used_openai": True,
    }


def build_balletour_stats_context(series, memberships, current_user=None):
    holes = sorted(series.course.holes, key=lambda hole: hole.hole_number)
    par_by_hole = {hole.hole_number: hole.par for hole in holes}
    player_ids = [membership.player_id for membership in memberships]
    player_names = {membership.player_id: membership.player.name for membership in memberships}
    round_players = _round_players(series, player_ids)
    round_player_ids = [round_player.id for round_player in round_players]
    entry_rows = _entry_rows(round_player_ids)

    by_player = defaultdict(list)
    by_hole = defaultdict(list)
    for row in entry_rows:
        by_player[row["player_id"]].append(row)
        by_hole[row["hole_number"]].append(row)

    completed_rounds_by_player = _completed_rounds_by_player(round_players, par_by_hole, series.course.hole_count)
    players = []
    for membership in memberships:
        player_id = membership.player_id
        rows = by_player.get(player_id, [])
        completed_rounds = completed_rounds_by_player.get(player_id, [])
        if not rows and not completed_rounds:
            continue
        players.append(_player_context(player_id, player_names.get(player_id), rows, completed_rounds, par_by_hole))

    players.sort(key=lambda row: (row["avg_score"] is None, row["avg_score"] or 9999, row["name"]))
    course_par = sum(par_by_hole.values())
    return {
        "course": {
            "name": series.course.name,
            "hole_count": series.course.hole_count,
            "par": course_par,
            "holes": [
                {
                    "hole": hole.hole_number,
                    "par": hole.par,
                    "stroke_index": hole.stroke_index,
                }
                for hole in holes
            ],
        },
        "current_user": _current_user_context(current_user),
        "dataset": {
            "players": len(players),
            "finished_round_players": len(round_players),
            "scored_holes": len(entry_rows),
            "note": "Bare fullførte BalleTour-runder er inkludert i AI-grunnlaget.",
        },
        "leaderboard": [
            {
                "rank": index,
                "name": player["name"],
                "rounds": player["completed_rounds"],
                "avg_score": player["avg_score"],
                "avg_to_par": player["avg_to_par"],
                "best_to_par": player["best_to_par"],
            }
            for index, player in enumerate(players, start=1)
        ],
        "players": players,
        "holes": [_hole_context(hole_number, rows, par_by_hole) for hole_number, rows in sorted(by_hole.items())],
        "field_summary": _field_summary(players, entry_rows),
    }


def _openai_api_key():
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ.get("OPENAI_API_KEY")
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return ""
    with open(env_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "OPENAI_API_KEY":
                return value.strip().strip('"').strip("'")
    return ""


def _round_players(series, player_ids):
    if not player_ids:
        return []
    return (
        RoundPlayer.query.join(Round)
        .filter(Round.course_id == series.course_id)
        .filter(Round.status == "finished")
        .filter(RoundPlayer.player_id.in_(player_ids))
        .order_by(Round.started_at.desc(), RoundPlayer.id.asc())
        .all()
    )


def _entry_rows(round_player_ids):
    if not round_player_ids:
        return []
    rows = (
        db.session.query(ScoreEntry, RoundPlayer, Round, CourseHole, ScoreStat, Club)
        .join(RoundPlayer, RoundPlayer.id == ScoreEntry.round_player_id)
        .join(Round, Round.id == ScoreEntry.round_id)
        .join(
            CourseHole,
            (CourseHole.course_id == Round.course_id)
            & (CourseHole.hole_number == ScoreEntry.hole_number),
        )
        .outerjoin(ScoreStat, ScoreStat.score_entry_id == ScoreEntry.id)
        .outerjoin(Club, Club.id == ScoreEntry.tee_club_id)
        .filter(ScoreEntry.round_player_id.in_(round_player_ids))
        .filter(ScoreEntry.strokes.isnot(None))
        .order_by(Round.started_at.desc(), RoundPlayer.id.asc(), ScoreEntry.hole_number.asc())
        .all()
    )
    return [
        {
            "entry_id": entry.id,
            "round_id": round_obj.id,
            "round_player_id": round_player.id,
            "player_id": round_player.player_id,
            "player_name": round_player.player_name_snapshot,
            "started_at": round_obj.started_at.date().isoformat() if round_obj.started_at else "",
            "tee": round_player.selected_tee.name if round_player.selected_tee else "",
            "hole_number": entry.hole_number,
            "par": hole.par,
            "stroke_index": hole.stroke_index,
            "strokes": entry.strokes,
            "to_par": entry.strokes - hole.par,
            "putts": stat.putts if stat else None,
            "last_putt_distance_m": stat.last_putt_distance_m if stat else None,
            "green_result_raw": stat.fairway_result if stat else "",
            "green_result": _green_result_label(stat.fairway_result if stat else ""),
            "club": club.name if club else "",
        }
        for entry, round_player, round_obj, hole, stat, club in rows
    ]


def _completed_rounds_by_player(round_players, par_by_hole, hole_count):
    completed = defaultdict(list)
    for round_player in round_players:
        entries = [
            entry for entry in round_player.score_entries
            if entry.strokes is not None and entry.hole_number in par_by_hole
        ]
        if len(entries) != hole_count:
            continue
        total = sum(entry.strokes for entry in entries)
        par = sum(par_by_hole[entry.hole_number] for entry in entries)
        completed[round_player.player_id].append(
            {
                "round_id": round_player.round_id,
                "date": round_player.round.started_at.date().isoformat() if round_player.round.started_at else "",
                "tee": round_player.selected_tee.name if round_player.selected_tee else "",
                "score": total,
                "to_par": total - par,
            }
        )
    return completed


def _player_context(player_id, player_name, rows, completed_rounds, par_by_hole):
    score_diffs = [row["to_par"] for row in rows]
    par_groups = {
        par: [row["strokes"] for row in rows if row["par"] == par]
        for par in (3, 4, 5)
    }
    green_rows = [row for row in rows if row["green_result_raw"]]
    putt_rows = [row for row in rows if row["putts"] is not None]
    by_hole = defaultdict(list)
    by_club = defaultdict(list)
    for row in rows:
        by_hole[row["hole_number"]].append(row)
        if row["club"]:
            by_club[row["club"]].append(row)

    return {
        "player_id": player_id,
        "name": player_name,
        "completed_rounds": len(completed_rounds),
        "scored_holes": len(rows),
        "avg_score": _round(_avg([row["score"] for row in completed_rounds]), 2),
        "avg_to_par": _round(_avg([row["to_par"] for row in completed_rounds]), 2),
        "best_score": min((row["score"] for row in completed_rounds), default=None),
        "best_to_par": min((row["to_par"] for row in completed_rounds), default=None),
        "worst_to_par": max((row["to_par"] for row in completed_rounds), default=None),
        "score_distribution": _score_distribution(score_diffs),
        "par_type_averages": {
            str(par): _round(_avg(values), 2)
            for par, values in par_groups.items()
        },
        "putting": {
            "holes_with_putts": len(putt_rows),
            "avg_putts": _round(_avg([row["putts"] for row in putt_rows]), 2),
            "avg_last_putt_distance_m": _round(_avg([row["last_putt_distance_m"] for row in rows if row["last_putt_distance_m"] is not None]), 2),
        },
        "green": _green_summary(green_rows),
        "holes": [_player_hole_context(hole_number, hole_rows, par_by_hole) for hole_number, hole_rows in sorted(by_hole.items())],
        "clubs": [_club_context(club, club_rows) for club, club_rows in _top_items(by_club, MAX_CLUB_ROWS_PER_PLAYER)],
        "recent_rounds": completed_rounds[:MAX_RECENT_ROUNDS_PER_PLAYER],
    }


def _player_hole_context(hole_number, rows, par_by_hole):
    par = par_by_hole.get(hole_number)
    scores = [row["strokes"] for row in rows]
    diffs = [row["to_par"] for row in rows]
    return {
        "hole": hole_number,
        "par": par,
        "played": len(rows),
        "avg_score": _round(_avg(scores), 2),
        "avg_to_par": _round(_avg(diffs), 2),
        "best": min(scores, default=None),
        "worst": max(scores, default=None),
        "distribution": _score_distribution(diffs),
        "green": _green_summary([row for row in rows if row["green_result_raw"]]),
    }


def _hole_context(hole_number, rows, par_by_hole):
    context = _player_hole_context(hole_number, rows, par_by_hole)
    context["players"] = [
        {
            "name": name,
            "played": len(player_rows),
            "avg_score": _round(_avg([row["strokes"] for row in player_rows]), 2),
            "avg_to_par": _round(_avg([row["to_par"] for row in player_rows]), 2),
            "best": min((row["strokes"] for row in player_rows), default=None),
        }
        for name, player_rows in sorted(_group_by(rows, "player_name").items())
    ]
    context["clubs"] = [_club_context(club, club_rows) for club, club_rows in _top_items(_group_by(rows, "club"), 10) if club]
    return context


def _club_context(club_name, rows):
    fairway_rows = [row for row in rows if row["green_result_raw"]]
    return {
        "club": club_name,
        "shots": len(rows),
        "avg_score": _round(_avg([row["strokes"] for row in rows]), 2),
        "avg_to_par": _round(_avg([row["to_par"] for row in rows]), 2),
        "green": _green_summary(fairway_rows),
    }


def _field_summary(players, rows):
    return {
        "avg_round": _round(_avg([player["avg_score"] for player in players if player["avg_score"] is not None]), 2),
        "avg_to_par": _round(_avg([player["avg_to_par"] for player in players if player["avg_to_par"] is not None]), 2),
        "scored_holes": len(rows),
        "score_distribution": _score_distribution([row["to_par"] for row in rows]),
        "green": _green_summary([row for row in rows if row["green_result_raw"]]),
        "putting": {
            "avg_putts": _round(_avg([row["putts"] for row in rows if row["putts"] is not None]), 2),
            "avg_last_putt_distance_m": _round(_avg([row["last_putt_distance_m"] for row in rows if row["last_putt_distance_m"] is not None]), 2),
        },
    }


def _green_summary(rows):
    if not rows:
        return {
            "attempts": 0,
            "hit_percent": None,
            "miss_percent": None,
            "bunker_percent": None,
            "left_percent": None,
            "right_percent": None,
            "short_percent": None,
            "long_percent": None,
        }
    counts = defaultdict(int)
    for row in rows:
        status, directions = _green_parts(row["green_result_raw"])
        counts[status] += 1
        for direction in directions:
            counts[direction] += 1
    attempts = len(rows)
    return {
        "attempts": attempts,
        "hit_percent": _percent(counts["hit"], attempts),
        "miss_percent": _percent(counts["miss"], attempts),
        "bunker_percent": _percent(counts["bunker"], attempts),
        "left_percent": _percent(counts["left"], attempts),
        "right_percent": _percent(counts["right"], attempts),
        "short_percent": _percent(counts["short"], attempts),
        "long_percent": _percent(counts["long"], attempts),
    }


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


def _green_result_label(raw_value):
    status, directions = _green_parts(raw_value)
    labels = {"hit": "treff", "miss": "miss", "bunker": "bunker"}
    direction_labels = {
        "pin": "på flagget",
        "left": "venstre",
        "right": "høyre",
        "short": "kort",
        "long": "lang",
    }
    parts = [labels.get(status, status)]
    parts.extend(direction_labels[direction] for direction in sorted(directions) if direction in direction_labels)
    return ", ".join(parts)


def _score_distribution(diffs):
    return {
        "eagle_or_better": sum(1 for diff in diffs if diff <= -2),
        "birdie": sum(1 for diff in diffs if diff == -1),
        "par": sum(1 for diff in diffs if diff == 0),
        "bogey": sum(1 for diff in diffs if diff == 1),
        "double_or_worse": sum(1 for diff in diffs if diff >= 2),
    }


def _current_user_context(current_user):
    if not current_user:
        return {}
    return {
        "username": current_user.username,
        "player_id": current_user.player_id,
        "player_name": current_user.player.name if current_user.player else "",
    }


def _group_by(rows, key):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.get(key)].append(row)
    return grouped


def _top_items(grouped, limit):
    return sorted(
        grouped.items(),
        key=lambda item: (-len(item[1]), str(item[0] or "")),
    )[:limit]


def _avg(values):
    values = [value for value in values if value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _round(value, digits):
    if value is None:
        return None
    return round(value, digits)


def _percent(numerator, denominator):
    if not denominator:
        return None
    return round((numerator / denominator) * 100, 1)
