import unittest
from types import SimpleNamespace

from services.round_completion import missing_saved_entry_choices, validate_score_stat_combination


class RoundCompletionTests(unittest.TestCase):
    def test_unscored_hole_requires_score_at_completion(self):
        missing = missing_saved_entry_choices(None, SimpleNamespace(par=4), False, False)

        self.assertEqual(missing, ["score"])

    def test_statistics_and_club_are_required_at_completion(self):
        entry = SimpleNamespace(strokes=5, tee_club_id=None, detailed_stat=None)

        missing = missing_saved_entry_choices(entry, SimpleNamespace(par=4), True, True)

        self.assertEqual(missing, ["kølle", "fairway", "putter"])

    def test_par_three_requires_tee_club_at_completion(self):
        stat = SimpleNamespace(fairway_result="hit:pin", putts=1, last_putt_distance_m=0.5)
        entry = SimpleNamespace(strokes=3, tee_club_id=None, detailed_stat=stat)

        missing = missing_saved_entry_choices(entry, SimpleNamespace(par=3), True, True)

        self.assertEqual(missing, ["kølle"])

    def test_complete_stat_entry_passes_completion(self):
        stat = SimpleNamespace(fairway_result="hit", putts=2, last_putt_distance_m=0.8)
        entry = SimpleNamespace(strokes=4, tee_club_id=1, detailed_stat=stat)

        missing = missing_saved_entry_choices(entry, SimpleNamespace(par=4), True, True)

        self.assertEqual(missing, [])

    def test_putts_and_green_miss_can_be_entered_before_score(self):
        validate_score_stat_combination(3, "miss:short,right", 2, None)

    def test_putts_are_validated_when_score_is_added(self):
        with self.assertRaisesRegex(ValueError, "score minus 1"):
            validate_score_stat_combination(4, "hit", 4, 4)

    def test_green_miss_is_validated_when_score_is_added(self):
        with self.assertRaisesRegex(ValueError, "minst 2 slag"):
            validate_score_stat_combination(3, "miss:short,right", 2, 3)


if __name__ == "__main__":
    unittest.main()
