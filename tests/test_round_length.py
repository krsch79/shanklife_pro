import unittest
from types import SimpleNamespace

from services.handicap import (
    calculate_playing_handicap_for_course,
    received_strokes_for_round,
    strokes_received_for_hole,
)
from services.round_length import (
    allowed_round_hole_counts,
    course_supports_nine_hole_round,
    round_handicap_stroke_index,
    round_hole_count,
    round_holes,
)


def _duplicate_loop_course():
    holes = []
    for hole_number in range(1, 19):
        physical_hole = ((hole_number - 1) % 9) + 1
        holes.append(
            SimpleNamespace(
                hole_number=hole_number,
                par=3 + (physical_hole % 3),
                stroke_index=(
                    physical_hole * 2 - 1
                    if hole_number <= 9
                    else physical_hole * 2
                ),
            )
        )
    lengths = [
        SimpleNamespace(
            hole_number=hole_number,
            length_meters=100 + (((hole_number - 1) % 9) + 1) * 10,
        )
        for hole_number in range(1, 19)
    ]
    return SimpleNamespace(
        hole_count=18,
        holes=holes,
        tees=[SimpleNamespace(lengths=lengths)],
    )


class RoundLengthTests(unittest.TestCase):
    def test_identical_loops_allow_nine_or_eighteen_holes(self):
        course = _duplicate_loop_course()

        self.assertTrue(course_supports_nine_hole_round(course))
        self.assertEqual(allowed_round_hole_counts(course), (9, 18))

    def test_length_difference_disables_nine_hole_option(self):
        course = _duplicate_loop_course()
        course.tees[0].lengths[-1].length_meters += 1

        self.assertFalse(course_supports_nine_hole_round(course))
        self.assertEqual(allowed_round_hole_counts(course), (18,))

    def test_nine_hole_round_uses_first_loop_and_normalized_indexes(self):
        course = _duplicate_loop_course()
        round_obj = SimpleNamespace(course=course, played_hole_count=9)

        self.assertEqual(round_hole_count(round_obj), 9)
        self.assertEqual(len(round_holes(round_obj)), 9)
        self.assertEqual(
            [
                round_handicap_stroke_index(round_obj, hole)
                for hole in course.holes[:9]
            ],
            list(range(1, 10)),
        )

    def test_eighteen_hole_rating_is_halved_and_distributed_for_nine_holes(self):
        course = _duplicate_loop_course()
        round_obj = SimpleNamespace(course=course, played_hole_count=9)
        total_par = sum(hole.par for hole in course.holes)
        rating = SimpleNamespace(slope=113, course_rating=total_par)

        playing_handicap = calculate_playing_handicap_for_course(
            10.0,
            rating,
            total_par,
            round_hole_count(round_obj),
        )
        received = received_strokes_for_round(playing_handicap, 9)
        allocation = [
            strokes_received_for_hole(
                playing_handicap,
                round_handicap_stroke_index(round_obj, hole),
                9,
            )
            for hole in course.holes[:9]
        ]

        self.assertEqual(received, 5)
        self.assertEqual(allocation, [1, 1, 1, 1, 1, 0, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
