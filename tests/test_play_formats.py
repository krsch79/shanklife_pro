import unittest

from services.play_formats import matchplay_status_label, matchplay_status_value


class MatchplayStatusTests(unittest.TestCase):
    def test_calculates_matchplay_status_from_hole_results(self):
        self.assertEqual(matchplay_status_value(["won", "halved", "won", "lost"]), 1)

    def test_formats_up_down_and_all_square(self):
        self.assertEqual(matchplay_status_label(2), "2 opp")
        self.assertEqual(matchplay_status_label(-1), "1 ned")
        self.assertEqual(matchplay_status_label(0), "All square")


if __name__ == "__main__":
    unittest.main()
