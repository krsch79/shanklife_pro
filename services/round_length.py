import math


def round_hole_count(round_obj):
    value = getattr(round_obj, "played_hole_count", None)
    return value if value in (9, 18) else round_obj.course.hole_count


def round_holes(round_obj):
    hole_count = round_hole_count(round_obj)
    return [
        hole
        for hole in sorted(round_obj.course.holes, key=lambda item: item.hole_number)
        if hole.hole_number <= hole_count
    ]


def course_supports_nine_hole_round(course):
    if course.hole_count != 18:
        return False

    holes = {hole.hole_number: hole for hole in course.holes}
    if len(holes) != 18:
        return False

    for front_number in range(1, 10):
        if holes[front_number].par != holes[front_number + 9].par:
            return False

    for tee in course.tees:
        lengths = {length.hole_number: length.length_meters for length in tee.lengths}
        if len(lengths) != 18:
            return False
        for front_number in range(1, 10):
            if lengths[front_number] != lengths[front_number + 9]:
                return False

    return True


def allowed_round_hole_counts(course):
    if course.hole_count == 9:
        return (9,)
    if course_supports_nine_hole_round(course):
        return (9, 18)
    return (18,)


def round_handicap_stroke_index(round_obj, hole):
    if round_hole_count(round_obj) != 9 or round_obj.course.hole_count != 18:
        return hole.stroke_index

    holes = {item.hole_number: item for item in round_obj.course.holes}
    ranked_pairs = []
    for front_number in range(1, 10):
        front = holes.get(front_number)
        back = holes.get(front_number + 9)
        if not front or not back:
            return max(1, min(9, int(math.ceil(hole.stroke_index / 2))))
        ranked_pairs.append((min(front.stroke_index, back.stroke_index), front_number))

    index_by_front_hole = {
        front_number: rank
        for rank, (_lowest_index, front_number) in enumerate(sorted(ranked_pairs), start=1)
    }
    return index_by_front_hole.get(
        hole.hole_number,
        max(1, min(9, int(math.ceil(hole.stroke_index / 2)))),
    )
