from collections import defaultdict

from models import CourseTeeLength, Round, RoundPlayer, ScoreEntry
from services.handicap import calculate_playing_handicap_for_course, strokes_received_for_hole


def _to_par_display(value):
    if value is None:
        return "—"
    if value == 0:
        return "E"
    if value > 0:
        return f"+{value}"
    return str(value)


def _through_display(completed_holes, hole_count):
    if completed_holes == 0:
        return "—"
    if completed_holes >= hole_count:
        return "F"
    return str(completed_holes)


def _sort_key(entry, view_mode):
    score_value = entry["net_to_par"] if view_mode == "net" else entry["gross_to_par"]

    if score_value is None:
        return (1, 999, 999, 999, entry["player_name"].lower())

    return (
        0,
        score_value,
        -entry["completed_holes"],
        entry["gross_total_strokes"],
        entry["player_name"].lower(),
    )


def _assign_positions(entries, view_mode):
    current_position = 0
    previous_key = None

    for index, entry in enumerate(entries, start=1):
        score_value = entry["net_to_par"] if view_mode == "net" else entry["gross_to_par"]
        ranking_key = (
            score_value,
            entry["completed_holes"],
            entry["gross_total_strokes"],
        )

        if ranking_key != previous_key:
            current_position = index
            previous_key = ranking_key

        entry["position"] = current_position


def _score_shape_class(score, par):
    if score is None:
        return ""

    diff = score - par
    if diff <= -2:
        return "score-shape double-circle"
    if diff == -1:
        return "score-shape circle"
    if diff == 1:
        return "score-shape square"
    if diff >= 2:
        return "score-shape double-square"
    return "score-shape plain"


def build_live_leaderboards(view_mode="gross"):
    ongoing_rounds = (
        Round.query.filter_by(status="ongoing")
        .order_by(Round.started_at.asc())
        .all()
    )

    grouped = defaultdict(list)

    for round_obj in ongoing_rounds:
        grouped[round_obj.course_id].append(round_obj)

    boards = []

    for _, rounds in grouped.items():
        if not rounds:
            continue

        course = rounds[0].course
        hole_count = course.hole_count
        par_map = {hole.hole_number: hole.par for hole in course.holes}
        total_par_for_course = sum(par_map.values())
        index_map = {hole.hole_number: hole.stroke_index for hole in course.holes}

        entries = []

        for round_obj in rounds:
            for round_player in round_obj.round_players:
                score_entries = (
                    ScoreEntry.query.filter_by(
                        round_id=round_obj.id,
                        round_player_id=round_player.id,
                    )
                    .order_by(ScoreEntry.hole_number.asc())
                    .all()
                )

                completed_holes = 0
                gross_total_strokes = 0
                total_par_completed = 0

                gender = (round_player.player.gender if round_player.player and round_player.player.gender else "male")
                rating = None
                if round_player.selected_tee:
                    for candidate in round_player.selected_tee.ratings:
                        if candidate.gender == gender:
                            rating = candidate
                            break

                playing_handicap = None
                if rating:
                    playing_handicap = calculate_playing_handicap_for_course(
                        round_player.hcp_for_round,
                        rating,
                        total_par_for_course,
                        hole_count,
                    )

                net_total_strokes = 0
                net_available = rating is not None

                for score_entry in score_entries:
                    if score_entry.strokes is None:
                        continue

                    completed_holes += 1
                    gross_total_strokes += score_entry.strokes
                    hole_par = par_map.get(score_entry.hole_number, 0)
                    total_par_completed += hole_par

                    if net_available:
                        hole_index = index_map.get(score_entry.hole_number, hole_count)
                        shots_received = strokes_received_for_hole(playing_handicap, hole_index, hole_count)
                        net_total_strokes += score_entry.strokes - shots_received

                gross_to_par = None
                if completed_holes > 0:
                    gross_to_par = gross_total_strokes - total_par_completed

                net_to_par = None
                if completed_holes > 0 and net_available:
                    net_to_par = net_total_strokes - total_par_completed

                entries.append(
                    {
                        "round_player_id": round_player.id,
                        "round_id": round_obj.id,
                        "round_started_at": round_obj.started_at,
                        "player_name": round_player.player_name_snapshot,
                        "gender": gender,
                        "hcp_for_round": round_player.hcp_for_round,
                        "tee_name": round_player.selected_tee.name if round_player.selected_tee else "—",
                        "completed_holes": completed_holes,
                        "through_display": _through_display(completed_holes, hole_count),
                        "gross_total_strokes": gross_total_strokes,
                        "gross_to_par": gross_to_par,
                        "gross_to_par_display": _to_par_display(gross_to_par),
                        "net_total_strokes": net_total_strokes if net_available else None,
                        "net_to_par": net_to_par,
                        "net_to_par_display": _to_par_display(net_to_par),
                        "playing_handicap": playing_handicap,
                    }
                )

        entries.sort(key=lambda entry: _sort_key(entry, view_mode))
        _assign_positions(entries, view_mode)

        boards.append(
            {
                "course_id": course.id,
                "course_name": course.name,
                "hole_count": hole_count,
                "round_count": len(rounds),
                "entries": entries,
            }
        )

    boards.sort(key=lambda board: board["course_name"].lower())
    return boards


def build_round_player_modal_data(round_player_id):
    round_player = RoundPlayer.query.get_or_404(round_player_id)
    round_obj = round_player.round
    course = round_obj.course

    holes = sorted(course.holes, key=lambda h: h.hole_number)

    entries = (
        ScoreEntry.query.filter_by(
            round_id=round_obj.id,
            round_player_id=round_player.id,
        )
        .order_by(ScoreEntry.hole_number.asc())
        .all()
    )

    score_map = {entry.hole_number: entry.strokes for entry in entries}

    length_map = {}
    if round_player.selected_tee_id:
        tee_lengths = (
            CourseTeeLength.query.filter_by(tee_id=round_player.selected_tee_id)
            .order_by(CourseTeeLength.hole_number.asc())
            .all()
        )
        for item in tee_lengths:
            length_map[item.hole_number] = item.length_meters

    hole_rows = []
    out_score = 0
    in_score = 0
    total_score = 0

    out_par = 0
    in_par = 0
    total_par = 0

    for hole in holes:
        score = score_map.get(hole.hole_number)
        par = hole.par
        length = length_map.get(hole.hole_number)

        if hole.hole_number <= 9:
            out_par += par
        else:
            in_par += par
        total_par += par

        if score is not None:
            total_score += score
            if hole.hole_number <= 9:
                out_score += score
            else:
                in_score += score

        hole_rows.append(
            {
                "hole_number": hole.hole_number,
                "par": par,
                "index": hole.stroke_index,
                "length": length,
                "score": score,
                "shape_class": _score_shape_class(score, par),
            }
        )

    to_par = None
    if total_score > 0:
        to_par = total_score - total_par

    return {
        "round_player_id": round_player.id,
        "round_id": round_obj.id,
        "round_started_at": round_obj.started_at,
        "round_status": round_obj.status,
        "course_name": course.name,
        "player_name": round_player.player_name_snapshot,
        "hcp_for_round": round_player.hcp_for_round,
        "tee_name": round_player.selected_tee.name if round_player.selected_tee else "—",
        "hole_count": course.hole_count,
        "hole_rows": hole_rows,
        "out_score": out_score,
        "in_score": in_score if course.hole_count > 9 else None,
        "total_score": total_score,
        "out_par": out_par,
        "in_par": in_par if course.hole_count > 9 else None,
        "total_par": total_par,
        "to_par_display": _to_par_display(to_par),
    }
