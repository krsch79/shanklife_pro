import json
import os
from collections import defaultdict

from openai import OpenAI, RateLimitError

from extensions import db
from models import Club, Course, CourseHole, Round, RoundPlayer, ScoreEntry, ScoreStat
from services.balletour import get_balletour_course_id


MAX_PLAYERS = 30
MAX_COURSES = 12
MAX_RECENT_ROUNDS = 6
MAX_CLUBS = 8
MAX_HOLE_PLAYERS = 8


def ask_shanklife_stats_ai(prompt, current_user=None):
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Skriv et spørsmål først.")

    data_context = build_shanklife_stats_context(prompt=prompt, current_user=current_user)
    api_key = _openai_api_key()
    if not api_key:
        return {
            "answer": "OpenAI-nøkkel mangler på serveren, så jeg kan ikke svare i chatten akkurat nå.",
            "data_context": data_context,
            "used_openai": False,
        }

    try:
        response = OpenAI(api_key=api_key).responses.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4.1"),
            input=[
                {
                    "role": "system",
                    "content": [{
                        "type": "input_text",
                        "text": (
                            "Du er Shanklife Pro sin statistikkassistent. Svar på norsk, konkret og praktisk. "
                            "Bruk bare tall og observasjoner i JSON-grunnlaget. Ikke finn opp data. Grunnlaget "
                            "utelater alle BalleTour/Ballerud-runder. Score-only-runder har scoredata, mens "
                            "statistikkrunder kan ha putting, GIR, fairway og køllevalg. Skill mellom baner og "
                            "teer når det påvirker analysen. Hvis spørsmålet nevner en bane eller tee, prioriter "
                            "den delen av grunnlaget. Oppgi tydelig når datamengden er liten eller et felt mangler."
                        ),
                    }],
                },
                {
                    "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": (
                            f"Spørsmål fra bruker:\n{prompt}\n\n"
                            "Shanklife-statistikkgrunnlag som JSON:\n"
                            f"{json.dumps(data_context, ensure_ascii=False, separators=(',', ':'))}"
                        ),
                    }],
                },
            ],
        )
    except RateLimitError:
        return {
            "answer": (
                "Statistikkgrunnlaget ble for stort for OpenAI akkurat nå. "
                "Prøv å avgrense spørsmålet med spiller, bane, hull eller tee."
            ),
            "data_context": data_context,
            "used_openai": False,
        }

    return {
        "answer": response.output_text.strip(),
        "data_context": data_context,
        "used_openai": True,
    }


def build_shanklife_stats_context(prompt="", current_user=None):
    round_players = _finished_shanklife_round_players()
    rows = _entry_rows([round_player.id for round_player in round_players])
    completed_rounds = _completed_rounds(round_players)

    by_player = defaultdict(list)
    by_course = defaultdict(list)
    rounds_by_player = defaultdict(list)
    rounds_by_course = defaultdict(list)
    for row in rows:
        by_player[row["player_id"]].append(row)
        by_course[row["course_id"]].append(row)
    for round_row in completed_rounds:
        rounds_by_player[round_row["player_id"]].append(round_row)
        rounds_by_course[round_row["course_id"]].append(round_row)

    player_names = {
        round_player.player_id: round_player.player_name_snapshot
        for round_player in round_players
    }
    players = [
        _player_context(player_id, player_names.get(player_id, "Ukjent spiller"), player_rows, rounds_by_player[player_id])
        for player_id, player_rows in by_player.items()
    ]
    players.sort(key=lambda player: (-player["completed_rounds"], player["name"]))

    course_names = {}
    for round_player in round_players:
        course_names[round_player.round.course_id] = round_player.round.course.name
    requested_course_ids = _requested_course_ids(prompt, course_names)
    courses = []
    for course_id, course_rows in sorted(by_course.items(), key=lambda item: course_names.get(item[0], "")):
        detailed = not requested_course_ids or course_id in requested_course_ids
        courses.append(
            _course_context(
                course_id,
                course_names.get(course_id, "Ukjent bane"),
                course_rows,
                rounds_by_course[course_id],
                detailed=detailed,
            )
        )

    compact_json = json.dumps(courses, ensure_ascii=False, separators=(",", ":"))
    if len(compact_json) > 70000 and not requested_course_ids:
        courses = [_course_summary(course) for course in courses]

    return {
        "current_user": _current_user_context(current_user),
        "dataset": {
            "players": len(players),
            "courses": len(courses),
            "finished_round_players": len(round_players),
            "scored_holes": len(rows),
            "rounds_with_detailed_stats": sum(1 for round_player in round_players if _tracks_stats(round_player)),
            "note": "Alle BalleTour/Ballerud-runder er utelatt.",
        },
        "players": players[:MAX_PLAYERS],
        "courses": courses[:MAX_COURSES],
        "field_summary": _field_summary(players, rows),
    }


def _finished_shanklife_round_players():
    query = (
        RoundPlayer.query.join(Round)
        .filter(Round.status == "finished")
        .filter(~Round.course.has(Course.name.ilike("%Ballerud%")))
        .order_by(Round.started_at.desc(), RoundPlayer.id.asc())
    )
    balletour_course_id = get_balletour_course_id()
    if balletour_course_id:
        query = query.filter(Round.course_id != balletour_course_id)
    return query.all()


def _entry_rows(round_player_ids):
    if not round_player_ids:
        return []
    query_rows = (
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
        .order_by(Round.started_at.desc(), ScoreEntry.hole_number.asc())
        .all()
    )
    return [
        {
            "round_id": round_obj.id,
            "player_id": round_player.player_id,
            "player_name": round_player.player_name_snapshot,
            "course_id": round_obj.course_id,
            "course_name": round_obj.course.name,
            "date": round_obj.started_at.date().isoformat() if round_obj.started_at else "",
            "tee": round_player.selected_tee.name if round_player.selected_tee else "",
            "hole": entry.hole_number,
            "par": hole.par,
            "strokes": entry.strokes,
            "to_par": entry.strokes - hole.par,
            "putts": stat.putts if stat else None,
            "fairway_result": stat.fairway_result if stat else "",
            "club": club.name if club else "",
        }
        for entry, round_player, round_obj, hole, stat, club in query_rows
    ]


def _completed_rounds(round_players):
    completed = []
    for round_player in round_players:
        holes = {hole.hole_number: hole for hole in round_player.round.course.holes}
        entries = [
            entry for entry in round_player.score_entries
            if entry.strokes is not None and entry.hole_number in holes
        ]
        if len(entries) != len(holes):
            continue
        total = sum(entry.strokes for entry in entries)
        par = sum(holes[entry.hole_number].par for entry in entries)
        completed.append({
            "round_id": round_player.round_id,
            "player_id": round_player.player_id,
            "player_name": round_player.player_name_snapshot,
            "course_id": round_player.round.course_id,
            "course_name": round_player.round.course.name,
            "date": round_player.round.started_at.date().isoformat() if round_player.round.started_at else "",
            "tee": round_player.selected_tee.name if round_player.selected_tee else "",
            "score": total,
            "to_par": total - par,
        })
    return completed


def _player_context(player_id, name, rows, rounds):
    by_course = defaultdict(list)
    rounds_by_course = defaultdict(list)
    by_club = defaultdict(list)
    for row in rows:
        by_course[row["course_name"]].append(row)
        if row["club"]:
            by_club[row["club"]].append(row)
    for round_row in rounds:
        rounds_by_course[round_row["course_name"]].append(round_row)
    return {
        "player_id": player_id,
        "name": name,
        "completed_rounds": len(rounds),
        "scored_holes": len(rows),
        "avg_to_par": _rounded_avg([row["to_par"] for row in rounds]),
        "best_to_par": min((row["to_par"] for row in rounds), default=None),
        "score_distribution": _score_distribution([row["to_par"] for row in rows]),
        "putting": _putting_summary(rows),
        "gir": _gir_summary(rows),
        "fairway": _fairway_summary(rows),
        "courses": [
            {
                "course": course_name,
                "holes": len(course_rows),
                "completed_rounds": len(rounds_by_course[course_name]),
                "avg_round_to_par": _rounded_avg([
                    round_row["to_par"] for round_row in rounds_by_course[course_name]
                ]),
                "best_round_to_par": min(
                    (round_row["to_par"] for round_row in rounds_by_course[course_name]),
                    default=None,
                ),
                "avg_to_par_per_hole": _rounded_avg([row["to_par"] for row in course_rows]),
            }
            for course_name, course_rows in sorted(by_course.items())
        ],
        "clubs": [_club_context(club, club_rows) for club, club_rows in _top_items(by_club, MAX_CLUBS)],
        "recent_rounds": rounds[:MAX_RECENT_ROUNDS],
    }


def _course_context(course_id, name, rows, rounds, detailed=True):
    by_hole = defaultdict(list)
    by_player = defaultdict(list)
    rounds_by_player = defaultdict(list)
    by_tee = defaultdict(list)
    for row in rows:
        by_hole[row["hole"]].append(row)
        by_player[row["player_name"]].append(row)
        by_tee[row["tee"] or "ukjent tee"].append(row)
    for round_row in rounds:
        rounds_by_player[round_row["player_name"]].append(round_row)
    context = {
        "course_id": course_id,
        "name": name,
        "completed_rounds": len(rounds),
        "avg_round_to_par": _rounded_avg([round_row["to_par"] for round_row in rounds]),
        "best_round_to_par": min((round_row["to_par"] for round_row in rounds), default=None),
        "scored_holes": len(rows),
        "players": [
            {
                "name": player_name,
                "holes": len(player_rows),
                "completed_rounds": len(rounds_by_player[player_name]),
                "avg_round_to_par": _rounded_avg([
                    round_row["to_par"] for round_row in rounds_by_player[player_name]
                ]),
                "best_round_to_par": min(
                    (round_row["to_par"] for round_row in rounds_by_player[player_name]),
                    default=None,
                ),
                "avg_to_par_per_hole": _rounded_avg([row["to_par"] for row in player_rows]),
                "putting": _putting_summary(player_rows),
                "gir": _gir_summary(player_rows),
                "fairway": _fairway_summary(player_rows),
            }
            for player_name, player_rows in sorted(by_player.items())
        ][:MAX_PLAYERS],
        "tees": [
            {
                "tee": tee_name,
                "holes": len(tee_rows),
                "avg_to_par_per_hole": _rounded_avg([row["to_par"] for row in tee_rows]),
            }
            for tee_name, tee_rows in sorted(by_tee.items())
        ],
        "field_summary": _row_summary(rows),
    }
    if detailed:
        context["holes"] = [
            _hole_context(hole_number, hole_rows)
            for hole_number, hole_rows in sorted(by_hole.items())
        ]
    else:
        context["details_note"] = "Hull-detaljer utelatt fordi spørsmålet peker på en annen bane."
    return context


def _course_summary(course):
    return {
        "course_id": course["course_id"],
        "name": course["name"],
        "completed_rounds": course["completed_rounds"],
        "avg_round_to_par": course["avg_round_to_par"],
        "best_round_to_par": course["best_round_to_par"],
        "scored_holes": course["scored_holes"],
        "players": course["players"],
        "tees": course["tees"],
        "field_summary": course["field_summary"],
        "details_note": "Hull-detaljer utelatt for å holde AI-grunnlaget kompakt. Nevn banen i spørsmålet for full detalj.",
    }


def _hole_context(hole_number, rows):
    par = rows[0]["par"] if rows else None
    grouped_players = defaultdict(list)
    grouped_clubs = defaultdict(list)
    for row in rows:
        grouped_players[row["player_name"]].append(row)
        if row["club"]:
            grouped_clubs[row["club"]].append(row)
    return {
        "hole": hole_number,
        "par": par,
        "played": len(rows),
        "avg_score": _rounded_avg([row["strokes"] for row in rows]),
        "avg_to_par": _rounded_avg([row["to_par"] for row in rows]),
        "score_distribution": _score_distribution([row["to_par"] for row in rows]),
        "putting": _putting_summary(rows),
        "gir": _gir_summary(rows),
        "fairway": _fairway_summary(rows),
        "players": [
            {
                "name": name,
                "played": len(player_rows),
                "avg_to_par": _rounded_avg([row["to_par"] for row in player_rows]),
            }
            for name, player_rows in sorted(
                grouped_players.items(),
                key=lambda item: (
                    _rounded_avg([row["to_par"] for row in item[1]]) is None,
                    _rounded_avg([row["to_par"] for row in item[1]]) or 0,
                    item[0],
                ),
            )[:MAX_HOLE_PLAYERS]
        ],
        "clubs": [_club_context(club, club_rows) for club, club_rows in _top_items(grouped_clubs, MAX_CLUBS)],
    }


def _row_summary(rows):
    return {
        "avg_to_par_per_hole": _rounded_avg([row["to_par"] for row in rows]),
        "score_distribution": _score_distribution([row["to_par"] for row in rows]),
        "putting": _putting_summary(rows),
        "gir": _gir_summary(rows),
        "fairway": _fairway_summary(rows),
    }


def _field_summary(players, rows):
    return {
        "avg_round_to_par": _rounded_avg([player["avg_to_par"] for player in players]),
        "scored_holes": len(rows),
        **_row_summary(rows),
    }


def _putting_summary(rows):
    values = [row["putts"] for row in rows if row["putts"] is not None]
    return {"attempts": len(values), "avg_putts": _rounded_avg(values)}


def _gir_summary(rows):
    attempts = [row for row in rows if row["putts"] is not None]
    hits = sum(1 for row in attempts if row["strokes"] - row["putts"] <= row["par"] - 2)
    return {"attempts": len(attempts), "hits": hits, "percent": _percent(hits, len(attempts))}


def _fairway_summary(rows):
    attempts = [
        row for row in rows
        if row["par"] in (4, 5) and row["fairway_result"] in ("hit", "left", "right")
    ]
    counts = {key: sum(1 for row in attempts if row["fairway_result"] == key) for key in ("hit", "left", "right")}
    return {
        "attempts": len(attempts),
        "hit_percent": _percent(counts["hit"], len(attempts)),
        "left_percent": _percent(counts["left"], len(attempts)),
        "right_percent": _percent(counts["right"], len(attempts)),
    }


def _club_context(club, rows):
    return {
        "club": club,
        "shots": len(rows),
        "avg_to_par": _rounded_avg([row["to_par"] for row in rows]),
        "fairway": _fairway_summary(rows),
    }


def _score_distribution(diffs):
    return {
        "eagle_or_better": sum(1 for diff in diffs if diff <= -2),
        "birdie": sum(1 for diff in diffs if diff == -1),
        "par": sum(1 for diff in diffs if diff == 0),
        "bogey": sum(1 for diff in diffs if diff == 1),
        "double_or_worse": sum(1 for diff in diffs if diff >= 2),
    }


def _requested_course_ids(prompt, course_names):
    lower = (prompt or "").lower()
    ignored_words = {"golf", "golfklubb", "bane", "banen", "club", "course"}
    return {
        course_id for course_id, name in course_names.items()
        if name and (
            name.lower() in lower
            or any(
                word in lower
                for word in name.lower().replace("+", " ").replace("-", " ").split()
                if len(word) >= 3 and word not in ignored_words
            )
        )
    }


def _tracks_stats(round_player):
    return bool(round_player.tracks_stats or round_player.round.stats_user_id)


def _current_user_context(current_user):
    if not current_user:
        return {}
    return {
        "username": current_user.username,
        "player_id": current_user.player_id,
        "player_name": current_user.player.name if current_user.player else "",
    }


def _top_items(grouped, limit):
    return sorted(grouped.items(), key=lambda item: (-len(item[1]), str(item[0])))[:limit]


def _rounded_avg(values):
    values = [value for value in values if value is not None]
    return round(sum(values) / len(values), 2) if values else None


def _percent(numerator, denominator):
    return round((numerator / denominator) * 100, 1) if denominator else None


def _openai_api_key():
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
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
