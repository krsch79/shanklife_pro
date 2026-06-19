import unittest
from types import SimpleNamespace

from services.round_summary import build_round_summary


def _stat(putts, fairway_result, drive_distance=200):
    return SimpleNamespace(
        putts=putts,
        fairway_result=fairway_result,
        drive_distance_m=drive_distance,
        last_putt_distance_m=0.5 if putts else None,
    )


class RoundSummaryTests(unittest.TestCase):
    def test_builds_scorecard_totals_and_round_statistics(self):
        holes = [
            SimpleNamespace(hole_number=1, par=3, stroke_index=3),
            SimpleNamespace(hole_number=2, par=4, stroke_index=1),
            SimpleNamespace(hole_number=3, par=5, stroke_index=2),
        ]
        tee = SimpleNamespace(
            id=1,
            name="Gul",
            lengths=[
                SimpleNamespace(hole_number=1, length_meters=140),
                SimpleNamespace(hole_number=2, length_meters=350),
                SimpleNamespace(hole_number=3, length_meters=480),
            ],
        )
        entries = [
            SimpleNamespace(
                hole_number=1,
                strokes=2,
                detailed_stat=_stat(1, "hit", 140),
                tee_club=SimpleNamespace(name="7-jern"),
            ),
            SimpleNamespace(
                hole_number=2,
                strokes=4,
                detailed_stat=_stat(2, "hit"),
                tee_club=SimpleNamespace(name="Driver"),
            ),
            SimpleNamespace(
                hole_number=3,
                strokes=6,
                detailed_stat=_stat(0, "right", 220),
                tee_club=SimpleNamespace(name="Driver"),
            ),
        ]
        round_player = SimpleNamespace(
            id=1,
            player_id=4,
            player_name_snapshot="Kristian",
            hcp_for_round=3.5,
            tracks_stats=True,
            selected_tee=tee,
            score_entries=entries,
        )
        round_obj = SimpleNamespace(
            played_hole_count=None,
            course=SimpleNamespace(hole_count=3, holes=holes),
            round_players=[round_player],
            stats_user=None,
        )

        summary = build_round_summary(round_obj)

        self.assertEqual(summary["front_par"], 12)
        self.assertEqual(summary["tee_rows"][0]["front_total"], 970)
        self.assertEqual(summary["player_rows"][0]["total"], 12)
        self.assertEqual(summary["player_rows"][0]["to_par_display"], "E")
        self.assertEqual(
            [summary["player_rows"][0]["cells"][number]["shape_class"] for number in (1, 2, 3)],
            ["circle", "plain", "square"],
        )

        stats = summary["statistics"][0]
        self.assertEqual(stats["gir_count"], 2)
        self.assertEqual(stats["gir_attempts"], 3)
        self.assertEqual(stats["fairway_attempts"], 2)
        self.assertEqual(stats["fairway_hit"], 1)
        self.assertEqual(stats["fairway_right"], 1)
        self.assertEqual(stats["putts_total"], 3)
        self.assertEqual(stats["putts_average"], 1.0)
        self.assertEqual(stats["green_attempts"], 1)
        self.assertEqual(stats["green_hit"], 1)
        self.assertEqual(stats["club_rows"][0], {"name": "Driver", "count": 2})


if __name__ == "__main__":
    unittest.main()
