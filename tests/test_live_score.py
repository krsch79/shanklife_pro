import unittest
from types import SimpleNamespace

from services.live_score import score_to_par_for_entries


class LiveScoreTests(unittest.TestCase):
    def test_shotgun_scores_count_regardless_of_hole_number(self):
        entries = [
            SimpleNamespace(hole_number=4, strokes=5),
            SimpleNamespace(hole_number=5, strokes=3),
            SimpleNamespace(hole_number=6, strokes=4),
            SimpleNamespace(hole_number=1, strokes=None),
        ]
        par_by_hole = {1: 4, 4: 4, 5: 3, 6: 4}

        self.assertEqual(
            score_to_par_for_entries(entries, par_by_hole, excluded_hole_number=1),
            1,
        )

    def test_current_hole_is_excluded_before_live_selection_is_added(self):
        entries = [
            SimpleNamespace(hole_number=4, strokes=5),
            SimpleNamespace(hole_number=5, strokes=4),
        ]
        par_by_hole = {4: 4, 5: 3}

        self.assertEqual(
            score_to_par_for_entries(entries, par_by_hole, excluded_hole_number=5),
            1,
        )

    def test_unscored_and_unknown_holes_are_ignored(self):
        entries = [
            SimpleNamespace(hole_number=4, strokes=None),
            SimpleNamespace(hole_number=19, strokes=4),
        ]

        self.assertEqual(score_to_par_for_entries(entries, {4: 4}), 0)


if __name__ == "__main__":
    unittest.main()
