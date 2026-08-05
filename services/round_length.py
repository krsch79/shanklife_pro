def round_hole_count(round_obj):
    value = getattr(round_obj, "played_hole_count", None)
    return value if value in (9, 18) else round_obj.course.hole_count


def round_starting_hole_number(round_obj):
    hole_count = round_hole_count(round_obj)
    value = getattr(round_obj, "starting_hole_number", None)
    if hole_count == 9 and round_obj.course.hole_count == 18 and value == 10:
        return 10
    return 1


def round_holes(round_obj):
    hole_count = round_hole_count(round_obj)
    starting_hole = round_starting_hole_number(round_obj)
    ending_hole = starting_hole + hole_count - 1
    return [
        hole
        for hole in sorted(round_obj.course.holes, key=lambda item: item.hole_number)
        if starting_hole <= hole.hole_number <= ending_hole
    ]


def round_length_label(round_obj):
    hole_count = round_hole_count(round_obj)
    if hole_count == 9 and round_obj.course.hole_count == 18:
        return "Siste 9" if round_starting_hole_number(round_obj) == 10 else "Første 9"
    return f"{hole_count} hull"


def course_supports_nine_hole_round(course):
    return course.hole_count == 18


def allowed_round_hole_counts(course):
    if course.hole_count == 9:
        return (9,)
    if course_supports_nine_hole_round(course):
        return (9, 18)
    return (course.hole_count,)


def allowed_round_starting_holes(course, hole_count):
    if course.hole_count == 18 and hole_count == 9:
        return (1, 10)
    return (1,)


def round_handicap_stroke_index(round_obj, hole):
    if round_hole_count(round_obj) != 9 or round_obj.course.hole_count != 18:
        return hole.stroke_index

    ranked_holes = sorted(
        round_holes(round_obj),
        key=lambda item: (item.stroke_index, item.hole_number),
    )
    index_by_hole = {
        ranked_hole.hole_number: rank
        for rank, ranked_hole in enumerate(ranked_holes, start=1)
    }
    return index_by_hole.get(hole.hole_number, hole.stroke_index)
