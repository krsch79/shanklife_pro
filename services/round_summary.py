from collections import Counter

from services.round_length import round_handicap_stroke_index, round_holes


def _percent(value, total):
    if not total:
        return None
    return round((value / total) * 100, 1)


def _average(values, digits=1):
    values = [value for value in values if value is not None]
    if not values:
        return None
    return round(sum(values) / len(values), digits)


def _score_shape_class(score, par):
    if score is None:
        return "plain"
    difference = score - par
    if difference <= -2:
        return "double-circle"
    if difference == -1:
        return "circle"
    if difference == 1:
        return "square"
    if difference >= 2:
        return "double-square"
    return "plain"


def _to_par_display(value):
    if value is None:
        return "-"
    if value == 0:
        return "E"
    return f"+{value}" if value > 0 else str(value)


def _segment_values(values, hole_numbers):
    segment = [values.get(hole_number) for hole_number in hole_numbers]
    present = [value for value in segment if value is not None]
    return sum(present) if present else None


def _player_tracks_stats(round_obj, round_player):
    if round_player.tracks_stats:
        return True
    stats_user = getattr(round_obj, "stats_user", None)
    return bool(stats_user and stats_user.player_id == round_player.player_id)


def _green_result_label(raw_value):
    status, separator, direction_text = (raw_value or "").partition(":")
    status_labels = {
        "hit": "Greentreff",
        "miss": "Miss green",
        "bunker": "Bunker",
    }
    label = status_labels.get(status, "-")
    if not separator:
        return label

    directions = set(direction_text.split(","))
    vertical = "kort" if "short" in directions else "lang" if "long" in directions else "pin high"
    horizontal = "venstre" if "left" in directions else "høyre" if "right" in directions else ""
    direction_label = " ".join(part for part in (vertical, horizontal) if part)
    return f"{label} · {direction_label}" if direction_label else label


def _shot_result_label(stat, hole):
    if not stat:
        return "-"
    if hole.par == 3:
        return _green_result_label(stat.fairway_result)
    return {
        "hit": "Traff fairway",
        "left": "Misset fairway venstre",
        "right": "Misset fairway høyre",
    }.get(stat.fairway_result, "-")


def _player_statistics(round_obj, round_player, holes_by_number, score_by_hole):
    entries = {
        entry.hole_number: entry
        for entry in round_player.score_entries
        if entry.hole_number in holes_by_number and entry.strokes is not None
    }
    stats_rows = [
        (entry, entry.detailed_stat, holes_by_number[hole_number])
        for hole_number, entry in sorted(entries.items())
        if entry.detailed_stat is not None
    ]

    fairway_counts = Counter()
    green_counts = Counter()
    club_counts = Counter()
    putts = []
    drive_distances = []
    last_putt_distances = []
    gir_count = 0
    gir_attempts = 0

    for entry, stat, hole in stats_rows:
        if stat.putts is not None:
            putts.append(stat.putts)
            gir_attempts += 1
            if entry.strokes - stat.putts <= hole.par - 2:
                gir_count += 1
        if hole.par in (4, 5) and stat.drive_distance_m is not None:
            drive_distances.append(stat.drive_distance_m)
        if stat.last_putt_distance_m is not None:
            last_putt_distances.append(stat.last_putt_distance_m)
        if entry.tee_club:
            club_counts[entry.tee_club.name] += 1
        if hole.par in (4, 5) and stat.fairway_result in ("hit", "left", "right"):
            fairway_counts[stat.fairway_result] += 1
        if hole.par == 3:
            green_status = (stat.fairway_result or "").partition(":")[0]
            if green_status in ("hit", "miss", "bunker"):
                green_counts[green_status] += 1

    differences = [
        score - holes_by_number[hole_number].par
        for hole_number, score in score_by_hole.items()
        if score is not None and hole_number in holes_by_number
    ]
    fairway_attempts = sum(fairway_counts.values())
    green_attempts = sum(green_counts.values())
    hole_rows = []
    for hole_number, entry in sorted(entries.items()):
        hole = holes_by_number[hole_number]
        stat = entry.detailed_stat
        difference = entry.strokes - hole.par
        hole_rows.append({
            "hole_number": hole_number,
            "par": hole.par,
            "score": entry.strokes,
            "to_par_display": _to_par_display(difference),
            "club": entry.tee_club.name if entry.tee_club else "-",
            "drive_distance": stat.drive_distance_m if stat and stat.drive_distance_m is not None else None,
            "result": _shot_result_label(stat, hole),
            "putts": stat.putts if stat and stat.putts is not None else None,
            "last_putt_distance": (
                stat.last_putt_distance_m
                if stat and stat.last_putt_distance_m is not None
                else None
            ),
        })

    return {
        "player_name": round_player.player_name_snapshot,
        "tee_name": round_player.selected_tee.name if round_player.selected_tee else "-",
        "scored_holes": len(differences),
        "total_score": sum(score for score in score_by_hole.values() if score is not None),
        "to_par": sum(differences) if differences else None,
        "to_par_display": _to_par_display(sum(differences) if differences else None),
        "gir_count": gir_count,
        "gir_attempts": gir_attempts,
        "gir_percent": _percent(gir_count, gir_attempts),
        "fairway_attempts": fairway_attempts,
        "fairway_hit": fairway_counts["hit"],
        "fairway_hit_percent": _percent(fairway_counts["hit"], fairway_attempts),
        "fairway_left": fairway_counts["left"],
        "fairway_left_percent": _percent(fairway_counts["left"], fairway_attempts),
        "fairway_right": fairway_counts["right"],
        "fairway_right_percent": _percent(fairway_counts["right"], fairway_attempts),
        "green_attempts": green_attempts,
        "green_hit": green_counts["hit"],
        "green_hit_percent": _percent(green_counts["hit"], green_attempts),
        "green_miss": green_counts["miss"],
        "green_bunker": green_counts["bunker"],
        "putts_total": sum(putts) if putts else 0,
        "putts_average": _average(putts, 2),
        "average_drive_distance": _average(drive_distances),
        "average_last_putt": _average(last_putt_distances, 2),
        "total_putt_distance": round(sum(last_putt_distances), 2),
        "eagles_or_better": sum(1 for difference in differences if difference <= -2),
        "birdies": sum(1 for difference in differences if difference == -1),
        "pars": sum(1 for difference in differences if difference == 0),
        "bogeys": sum(1 for difference in differences if difference == 1),
        "double_or_worse": sum(1 for difference in differences if difference >= 2),
        "club_rows": [
            {"name": name, "count": count}
            for name, count in sorted(club_counts.items(), key=lambda row: (-row[1], row[0]))
        ],
        "hole_rows": hole_rows,
    }


def build_round_summary(round_obj):
    holes = round_holes(round_obj)
    holes_by_number = {hole.hole_number: hole for hole in holes}
    front_numbers = [hole.hole_number for hole in holes if hole.hole_number <= 9]
    back_numbers = [hole.hole_number for hole in holes if hole.hole_number > 9]
    all_numbers = front_numbers + back_numbers

    par_by_hole = {hole.hole_number: hole.par for hole in holes}
    index_by_hole = {
        hole.hole_number: round_handicap_stroke_index(round_obj, hole)
        for hole in holes
    }

    visible_tees = []
    visible_tee_ids = set()
    for round_player in sorted(round_obj.round_players, key=lambda item: item.id):
        tee = round_player.selected_tee
        if tee and tee.id not in visible_tee_ids:
            visible_tee_ids.add(tee.id)
            visible_tees.append(tee)

    tee_rows = []
    for tee in visible_tees:
        lengths = {
            length.hole_number: length.length_meters
            for length in tee.lengths
            if length.hole_number in holes_by_number
        }
        tee_rows.append({
            "label": f"Lengde {tee.name}",
            "lengths": lengths,
            "front_total": _segment_values(lengths, front_numbers),
            "back_total": _segment_values(lengths, back_numbers),
            "total": _segment_values(lengths, all_numbers),
        })

    player_rows = []
    statistics = []
    for round_player in sorted(round_obj.round_players, key=lambda item: item.id):
        entries = {entry.hole_number: entry for entry in round_player.score_entries}
        scores = {
            hole_number: entries[hole_number].strokes if hole_number in entries else None
            for hole_number in all_numbers
        }
        cells = {
            hole_number: {
                "score": score,
                "shape_class": _score_shape_class(score, par_by_hole[hole_number]),
            }
            for hole_number, score in scores.items()
        }
        player_row = {
            "player_name": round_player.player_name_snapshot,
            "hcp": round_player.hcp_for_round,
            "tee_name": round_player.selected_tee.name if round_player.selected_tee else "-",
            "cells": cells,
            "front_total": _segment_values(scores, front_numbers),
            "back_total": _segment_values(scores, back_numbers),
            "total": _segment_values(scores, all_numbers),
            "to_par": (
                sum(score for score in scores.values() if score is not None)
                - sum(par_by_hole[hole_number] for hole_number, score in scores.items() if score is not None)
            ),
        }
        player_row["to_par_display"] = _to_par_display(player_row["to_par"])
        player_rows.append(player_row)

        if _player_tracks_stats(round_obj, round_player):
            statistics.append(
                _player_statistics(round_obj, round_player, holes_by_number, scores)
            )

    return {
        "hole_numbers": all_numbers,
        "front_holes": [holes_by_number[number] for number in front_numbers],
        "back_holes": [holes_by_number[number] for number in back_numbers],
        "par_by_hole": par_by_hole,
        "index_by_hole": index_by_hole,
        "front_par": _segment_values(par_by_hole, front_numbers),
        "back_par": _segment_values(par_by_hole, back_numbers),
        "total_par": _segment_values(par_by_hole, all_numbers),
        "tee_rows": tee_rows,
        "player_rows": player_rows,
        "statistics": statistics,
    }
