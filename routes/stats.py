import math
from collections import defaultdict

from flask import Blueprint, flash, g, render_template, request, session
from sqlalchemy import or_

from extensions import db
from models import Club, CourseHole, Player, Round, RoundPlayer, ScoreEntry, ScoreStat, User
from routes.auth import login_required
from services.balletour import get_balletour_course_id
from services.play_formats import MATCHPLAY
from services.round_length import round_holes
from services.shanklife_ai_stats import ask_shanklife_stats_ai
from services.stats_summary import round_score_summary

stats_bp = Blueprint("stats", __name__, url_prefix="/stats")


def _exclude_balletour_course(query):
    balletour_course_id = get_balletour_course_id()
    if balletour_course_id:
        return query.filter(Round.course_id != balletour_course_id)
    return query


@stats_bp.route("/ai", methods=["GET", "POST"])
@login_required
def ai_stats():
    chat_messages = session.get("shanklife_stats_ai_chat", [])
    if request.method == "GET":
        chat_messages = []
        session.pop("shanklife_stats_ai_chat", None)

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        prompt = request.form.get("prompt", "").strip()
        if action == "clear":
            chat_messages = []
            session.pop("shanklife_stats_ai_chat", None)
        elif prompt:
            chat_messages.append({"role": "user", "text": prompt})
            try:
                result = ask_shanklife_stats_ai(prompt, current_user=g.current_user)
                chat_messages.append({
                    "role": "assistant",
                    "text": result["answer"],
                    "used_openai": result.get("used_openai", False),
                    "context_summary": result.get("data_context", {}).get("dataset", {}),
                })
            except Exception as exc:
                chat_messages.append({
                    "role": "assistant",
                    "error": f"Jeg klarte ikke å analysere statistikken akkurat nå: {exc}",
                })
        else:
            flash("Skriv et statistikkspørsmål først.", "error")
        session["shanklife_stats_ai_chat"] = chat_messages[-10:]

    return render_template(
        "shanklife_ai_stats.html",
        chat_messages=chat_messages,
        example_prompts=[
            "Hva bør jeg trene mest på basert på rundene mine?",
            "På hvilken bane spiller jeg best i forhold til par?",
            "Hvor taper jeg flest slag sammenlignet med de andre spillerne?",
            "Hvordan er fairwaytreffene mine fordelt mellom treff, venstre og høyre?",
            "Hvilke køller gir meg best resultater på par 4 og par 5?",
        ],
    )


def _percent(numerator, denominator):
    if denominator == 0:
        return None
    return round((numerator / denominator) * 100, 1)


def _avg(values):
    values = [value for value in values if value is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _normal_drive_distances(values):
    distances = []
    for value in values:
        if value is None:
            continue
        try:
            distance = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(distance) and 30 <= distance <= 360:
            distances.append(distance)

    distances.sort()
    total = len(distances)
    if total >= 10:
        short_trim = max(1, int(total * 0.2))
        long_trim = max(1, int(total * 0.1))
        if short_trim + long_trim < total:
            return distances[short_trim:total - long_trim]
    if total >= 5:
        return distances[1:-1]
    return distances


def _avg_normal_drive_distance(values):
    distances = _normal_drive_distances(values)
    if not distances:
        return None
    return int(round(sum(distances) / len(distances)))


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


def _green_point(status, directions, index):
    vertical = "long" if "long" in directions else "short" if "short" in directions else ""
    horizontal = "left" if "left" in directions else "right" if "right" in directions else ""
    key = "_".join(part for part in (vertical, horizontal) if part) or "center"
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
            "center": (50, 19),
            "long": (50, 19),
            "short": (50, 81),
            "left": (20, 50),
            "right": (80, 50),
            "long_left": (30, 20),
            "long_right": (70, 20),
            "short_left": (30, 80),
            "short_right": (70, 80),
        },
        "miss": {
            "center": (50, 91),
            "long": (50, 10),
            "short": (50, 91),
            "left": (10, 50),
            "right": (90, 50),
            "long_left": (22, 10),
            "long_right": (78, 10),
            "short_left": (22, 90),
            "short_right": (78, 90),
        },
    }
    if key == "center" and status in ("bunker", "miss"):
        key = ("long", "right", "short", "left")[index % 4]
    x, y = anchors.get(status, anchors["hit"]).get(key, anchors["hit"]["center"])
    jitter_range = 5 if status == "hit" else 3
    return {
        "status": status,
        "x": max(8, min(92, x + ((index * 17) % jitter_range) - (jitter_range // 2))),
        "y": max(8, min(92, y + ((index * 29) % jitter_range) - (jitter_range // 2))),
    }


def _stats_players():
    user_query = (
        db.session.query(User.player_id)
        .join(Round, Round.stats_user_id == User.id)
        .filter(Round.status == "finished")
        .filter(Round.play_format != MATCHPLAY)
    )
    round_player_query = (
        db.session.query(RoundPlayer.player_id)
        .join(Round)
        .filter(Round.status == "finished")
        .filter(Round.play_format != MATCHPLAY)
        .filter(RoundPlayer.tracks_stats.is_(True))
    )
    tracked_player_ids = {
        player_id
        for (player_id,) in _exclude_balletour_course(user_query).distinct().all()
        if player_id
    }
    tracked_player_ids.update({
        player_id
        for (player_id,) in _exclude_balletour_course(round_player_query).distinct().all()
        if player_id
    })
    if g.current_user and g.current_user.player_id:
        tracked_player_ids.add(g.current_user.player_id)
    if not tracked_player_ids:
        return []
    return Player.query.filter(Player.id.in_(tracked_player_ids)).order_by(Player.name.asc()).all()


def _tracked_round_players(player):
    if not player:
        return []
    query = (
        RoundPlayer.query.join(Round)
        .outerjoin(User, Round.stats_user_id == User.id)
        .filter(Round.status == "finished")
        .filter(Round.play_format != MATCHPLAY)
        .filter(RoundPlayer.player_id == player.id)
        .filter(or_(
            RoundPlayer.tracks_stats.is_(True),
            User.player_id == player.id,
        ))
        .order_by(Round.started_at.desc())
    )
    return _exclude_balletour_course(query).all()


def _completed_rounds(round_players):
    completed = []
    for round_player in round_players:
        holes = round_holes(round_player.round)
        entries = [entry for entry in round_player.score_entries if entry.strokes is not None]
        if len(entries) != len(holes):
            continue
        completed.append({
            "round_player": round_player,
            "holes": len(holes),
            "total": sum(entry.strokes for entry in entries),
            "par": sum(hole.par for hole in holes),
        })
    return completed


def _par_by_entry_id(round_player_ids):
    rows = (
        db.session.query(ScoreEntry.id, CourseHole.par)
        .join(Round, Round.id == ScoreEntry.round_id)
        .join(
            CourseHole,
            (CourseHole.course_id == Round.course_id)
            & (CourseHole.hole_number == ScoreEntry.hole_number),
        )
        .filter(ScoreEntry.round_player_id.in_(round_player_ids))
        .all()
        if round_player_ids else []
    )
    return {entry_id: par for entry_id, par in rows}


def _score_distribution(diffs):
    return {
        "eagles_or_better": sum(1 for diff in diffs if diff <= -2),
        "birdies": sum(1 for diff in diffs if diff == -1),
        "pars": sum(1 for diff in diffs if diff == 0),
        "bogeys": sum(1 for diff in diffs if diff == 1),
        "double_bogeys_or_worse": sum(1 for diff in diffs if diff >= 2),
    }


def _gir_count(stats_rows, par_by_entry_id):
    return sum(
        1
        for stat, entry in stats_rows
        if entry.strokes is not None
        and stat.putts is not None
        and entry.strokes - stat.putts <= par_by_entry_id.get(entry.id, 3) - 2
    )


def _round_stat_summary(round_player):
    entries = sorted(
        [entry for entry in round_player.score_entries if entry.strokes is not None],
        key=lambda entry: entry.hole_number,
    )
    holes = {hole.hole_number: hole for hole in round_holes(round_player.round)}
    par_by_entry_id = {
        entry.id: holes[entry.hole_number].par
        for entry in entries
        if entry.hole_number in holes
    }
    stats_by_entry_id = {
        stat.score_entry_id: stat
        for stat in ScoreStat.query.filter(
            ScoreStat.score_entry_id.in_([entry.id for entry in entries])
        ).all()
    } if entries else {}
    stats_rows = [
        (stats_by_entry_id[entry.id], entry)
        for entry in entries
        if entry.id in stats_by_entry_id
    ]
    diffs = [entry.strokes - par_by_entry_id.get(entry.id, 3) for entry in entries]
    score_counts = _score_distribution(diffs)
    fairway_counts = {"hit": 0, "left": 0, "right": 0}
    fairway_attempts = 0
    for stat, entry in stats_rows:
        if par_by_entry_id.get(entry.id) not in (4, 5):
            continue
        if stat.fairway_result in fairway_counts:
            fairway_attempts += 1
            fairway_counts[stat.fairway_result] += 1

    gir_attempts = len([entry for entry in entries if entry.id in stats_by_entry_id])
    gir_count = _gir_count(stats_rows, par_by_entry_id)
    total = sum(entry.strokes for entry in entries) if entries else None
    par = sum(par_by_entry_id.get(entry.id, 0) for entry in entries)
    return {
        "round_id": round_player.round_id,
        "started_at": round_player.round.started_at,
        "course_name": round_player.round.course.name,
        "tee_name": round_player.selected_tee.name if round_player.selected_tee else "—",
        "holes": len(entries),
        "total": total,
        "to_par": total - par if total is not None else None,
        "gir_percent": _percent(gir_count, gir_attempts),
        "avg_putts": _avg([stat.putts for stat, _entry in stats_rows]),
        "fairway_attempts": fairway_attempts,
        "fairway_hit_percent": _percent(fairway_counts["hit"], fairway_attempts),
        "fairway_left_percent": _percent(fairway_counts["left"], fairway_attempts),
        "fairway_right_percent": _percent(fairway_counts["right"], fairway_attempts),
        **score_counts,
    }


def _player_stats(player):
    round_players = _tracked_round_players(player)
    round_player_ids = [round_player.id for round_player in round_players]
    completed = _completed_rounds(round_players)
    entries = (
        ScoreEntry.query.filter(ScoreEntry.round_player_id.in_(round_player_ids))
        .filter(ScoreEntry.strokes.isnot(None))
        .all()
        if round_player_ids else []
    )
    par_by_entry_id = _par_by_entry_id(round_player_ids)
    diffs = [entry.strokes - par_by_entry_id.get(entry.id, 3) for entry in entries]
    score_counts = _score_distribution(diffs)

    stats_rows = (
        db.session.query(ScoreStat, ScoreEntry)
        .join(ScoreEntry, ScoreStat.score_entry_id == ScoreEntry.id)
        .filter(ScoreEntry.round_player_id.in_(round_player_ids))
        .all()
        if round_player_ids else []
    )
    green_rows = [(stat, entry) for stat, entry in stats_rows if par_by_entry_id.get(entry.id) == 3]
    tee_rows = [(stat, entry) for stat, entry in stats_rows if par_by_entry_id.get(entry.id) in (4, 5)]

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
    for index, (stat, entry) in enumerate(green_rows):
        status, directions = _green_parts(stat.fairway_result)
        bucket = _green_bucket(status, directions)
        green_bucket_counts[bucket] = green_bucket_counts.get(bucket, 0) + 1
        green_points.append(_green_point(status, directions, index))
        if status == "bunker":
            sand_save_attempts += 1
            if entry.strokes is not None and entry.strokes <= par_by_entry_id.get(entry.id, 3):
                sand_saves += 1

    fairway_counts = {"hit": 0, "left": 0, "right": 0}
    for stat, _entry in tee_rows:
        if stat.fairway_result in fairway_counts:
            fairway_counts[stat.fairway_result] += 1
    fairway_attempts = sum(fairway_counts.values())

    club_rows = []
    by_club = defaultdict(lambda: {
        "count": 0,
        "strokes": [],
        "drive_distances": [],
        "hit": 0,
        "left": 0,
        "right": 0,
    })
    club_names = {}
    for stat, entry in tee_rows:
        if not entry.tee_club_id:
            continue
        bucket = by_club[entry.tee_club_id]
        bucket["count"] += 1
        bucket["strokes"].append(entry.strokes)
        bucket["drive_distances"].append(stat.drive_distance_m)
        if stat.fairway_result in ("hit", "left", "right"):
            bucket[stat.fairway_result] += 1
    clubs = Club.query.filter(Club.id.in_(by_club.keys())).all() if by_club else []
    club_names = {club.id: club.name for club in clubs}
    for club_id, row in by_club.items():
        club_rows.append({
            "name": club_names.get(club_id, "Ukjent"),
            "count": row["count"],
            "avg": _avg(row["strokes"]),
            "avg_drive_distance": _avg_normal_drive_distance(row["drive_distances"]),
            "fairway_percent": _percent(row["hit"], row["count"]),
            "left_percent": _percent(row["left"], row["count"]),
            "right_percent": _percent(row["right"], row["count"]),
        })
    club_rows.sort(key=lambda row: (-(row["count"] or 0), row["name"]))

    putt_distance_by_round = {row["round_player"].round_id: 0 for row in completed}
    for stat, entry in stats_rows:
        if entry.round_id in putt_distance_by_round and stat.last_putt_distance_m is not None:
            putt_distance_by_round[entry.round_id] += stat.last_putt_distance_m

    round_summary = round_score_summary(completed)
    gir_attempts = len([entry for entry in entries if entry.id in {stat.score_entry_id for stat, _entry in stats_rows}])
    gir_count = _gir_count(stats_rows, par_by_entry_id)
    return {
        "round_count": len(round_players),
        "completed_round_count": len(completed),
        **round_summary,
        "scored_holes": len(entries),
        "gir_percent": _percent(gir_count, gir_attempts),
        **score_counts,
        "green_hit_percent": _percent(green_bucket_counts["hit"], len(green_rows)),
        "bunker_percent": _percent(green_bucket_counts["bunker"], len(green_rows)),
        "sand_save_attempts": sand_save_attempts,
        "sand_saves": sand_saves,
        "sand_save_percent": _percent(sand_saves, sand_save_attempts),
        "avg_putts": _avg([stat.putts for stat, _entry in stats_rows]),
        "avg_last_putt_distance": _avg([stat.last_putt_distance_m for stat, _entry in stats_rows]),
        "avg_putt_meters_per_round": _avg(list(putt_distance_by_round.values())),
        "green_points": green_points[-160:],
        "green_distribution": [
            {
                "key": key,
                "label": label,
                "count": green_bucket_counts.get(key, 0),
                "percent": _percent(green_bucket_counts.get(key, 0), len(green_rows)),
            }
            for key, label in green_bucket_labels
            if green_bucket_counts.get(key, 0) or key in ("hit", "bunker")
        ],
        "fairway_attempts": fairway_attempts,
        "fairway_hit_percent": _percent(fairway_counts["hit"], fairway_attempts),
        "fairway_left_percent": _percent(fairway_counts["left"], fairway_attempts),
        "fairway_right_percent": _percent(fairway_counts["right"], fairway_attempts),
        "club_rows": club_rows,
        "round_rows": [_round_stat_summary(round_player) for round_player in round_players],
    }


@stats_bp.route("/")
@login_required
def index():
    players = _stats_players()
    selected_player_id = request.args.get("player_id", "").strip()
    selected_player = None
    if selected_player_id:
        try:
            selected_player = next((player for player in players if player.id == int(selected_player_id)), None)
        except ValueError:
            selected_player = None
    if not selected_player and g.current_user:
        selected_player = next((player for player in players if player.id == g.current_user.player_id), None)
    if not selected_player and players:
        selected_player = players[0]
    if not selected_player:
        return render_template("stats.html", players=players, selected_player=None, stats={})
    return render_template(
        "stats.html",
        players=players,
        selected_player=selected_player,
        stats=_player_stats(selected_player),
    )
