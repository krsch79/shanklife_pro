import unittest
from types import SimpleNamespace

from services.round_completion import missing_saved_entry_choices, validate_score_putts


class RoundCompletionTests(unittest.TestCase):
    def test_unscored_hole_requires_score_at_completion(self):
        missing = missing_saved_entry_choices(None, SimpleNamespace(par=4), False, False)

        self.assertEqual(missing, ["score"])

    def test_green_or_fairway_and_club_are_required_at_completion(self):
        entry = SimpleNamespace(strokes=5, tee_club_id=None, detailed_stat=None)

        missing = missing_saved_entry_choices(entry, SimpleNamespace(par=4), True, True)

        self.assertEqual(missing, ["kølle", "fairway"])

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
        validate_score_putts(2, None)

    def test_zero_putts_are_allowed_for_chip_in(self):
        validate_score_putts(0, 3)

    def test_zero_putts_pass_round_completion_without_last_putt(self):
        stat = SimpleNamespace(fairway_result="hit", putts=0, last_putt_distance_m=None)
        entry = SimpleNamespace(strokes=3, tee_club_id=1, detailed_stat=stat)

        missing = missing_saved_entry_choices(entry, SimpleNamespace(par=3), True, True)

        self.assertEqual(missing, [])

    def test_missing_putts_pass_round_completion(self):
        stat = SimpleNamespace(fairway_result="hit", putts=None, last_putt_distance_m=None)
        entry = SimpleNamespace(strokes=4, tee_club_id=1, detailed_stat=stat)

        missing = missing_saved_entry_choices(entry, SimpleNamespace(par=4), True, True)

        self.assertEqual(missing, [])

    def test_putts_are_validated_when_score_is_added(self):
        with self.assertRaisesRegex(ValueError, "minst én mer"):
            validate_score_putts(4, 4)

    def test_score_one_higher_than_putts_is_allowed(self):
        validate_score_putts(2, 3)


if __name__ == "__main__":
    unittest.main()
