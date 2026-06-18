import unittest

from services.stats_summary import round_score_summary


class StatsSummaryTests(unittest.TestCase):
    def test_round_average_uses_score_against_par(self):
        completed = [
            {"holes": 18, "total": 73, "par": 72},
            {"holes": 18, "total": 70, "par": 70},
            {"holes": 9, "total": 34, "par": 36},
        ]

        summary = round_score_summary(completed)

        self.assertEqual(summary["avg_round_vs_par"], -0.3)
        self.assertEqual(summary["best_round_vs_par"], -2)

    def test_best_rounds_are_split_by_hole_count(self):
        completed = [
            {"holes": 18, "total": 73, "par": 72},
            {"holes": 18, "total": 71, "par": 70},
            {"holes": 9, "total": 34, "par": 36},
            {"holes": 9, "total": 36, "par": 36},
        ]

        summary = round_score_summary(completed)

        self.assertEqual(summary["best_round_18"], 71)
        self.assertEqual(summary["best_round_9"], 34)

    def test_missing_round_length_has_no_best_score(self):
        summary = round_score_summary([
            {"holes": 9, "total": 35, "par": 36},
        ])

        self.assertIsNone(summary["best_round_18"])
        self.assertEqual(summary["best_round_9"], 35)


if __name__ == "__main__":
    unittest.main()
