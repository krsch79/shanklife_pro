import math


def round_half_up(value):
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def calculate_playing_handicap(handicap_index, rating, total_par):
    if rating is None:
        return None

    return round_half_up(
        handicap_index * (rating.slope / 113.0) + (rating.course_rating - total_par)
    )


def strokes_received_for_hole(playing_handicap, hole_index, hole_count):
    if playing_handicap == 0:
        return 0

    if playing_handicap > 0:
        base = playing_handicap // hole_count
        remainder = playing_handicap % hole_count
        extra = 1 if hole_index <= remainder else 0
        return base + extra

    abs_hcp = abs(playing_handicap)
    base = abs_hcp // hole_count
    remainder = abs_hcp % hole_count
    extra = 1 if hole_index <= remainder else 0
    return -(base + extra)
