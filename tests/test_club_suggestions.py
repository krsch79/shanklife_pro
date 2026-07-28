import unittest
from types import SimpleNamespace


class ClubSuggestionTests(unittest.TestCase):
    @staticmethod
    def _row(score, club_id=None, club_name=None, result=None, sort_order=0):
        club = None
        if club_id is not None:
            club = SimpleNamespace(id=club_id, name=club_name, sort_order=sort_order)
        return (
            SimpleNamespace(strokes=score),
            SimpleNamespace(),
            SimpleNamespace(fairway_result=result) if result else None,
            club,
        )

    def test_recommends_club_with_best_average_score(self):
        from routes.rounds import _club_suggestion_from_history_rows

        rows = [
            self._row(5, 1, "Driver", "hit", 1),
            self._row(4, 2, "3-wood", "left", 2),
            self._row(6, 1, "Driver", "right", 1),
            self._row(4, 2, "3-wood", "hit", 2),
        ]

        suggestion = _club_suggestion_from_history_rows(rows)

        self.assertEqual(suggestion, {
            "club_id": 2,
            "club_name": "3-wood",
            "uses": 2,
            "average_score": 4.0,
        })

    def test_tie_prefers_more_historical_uses(self):
        from routes.rounds import _club_suggestion_from_history_rows

        rows = [
            self._row(4, 1, "Driver", "right", 1),
            self._row(5, 2, "3-wood", "hit", 2),
            self._row(3, 1, "Driver", "hit", 1),
            self._row(3, 2, "3-wood", "hit", 2),
            self._row(5, 1, "Driver", "right", 1),
        ]

        suggestion = _club_suggestion_from_history_rows(rows)

        self.assertEqual(suggestion["club_name"], "Driver")
        self.assertEqual(suggestion["uses"], 3)

    def test_ignores_history_without_registered_club(self):
        from routes.rounds import _club_suggestion_from_history_rows

        self.assertIsNone(_club_suggestion_from_history_rows([
            self._row(4),
            self._row(5),
        ]))


if __name__ == "__main__":
    unittest.main()
