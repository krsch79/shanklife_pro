import os
import tempfile
import unittest
from datetime import datetime


class FakeGarminClient:
    def __init__(self, summary, shots_by_hole):
        self.summary = summary
        self.shots_by_hole = shots_by_hole
        self.requested_holes = []

    def get_golf_summary(self, start, limit):
        return self.summary

    def get_golf_shot_data(self, scorecard_id, hole_number):
        self.requested_holes.append(hole_number)
        return self.shots_by_hole[int(hole_number)]


class GarminGolfTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.tmpdir.name}/test.db"

        from app import create_app
        from extensions import db
        from models import Course, CourseHole, GarminRoundSync, Player, Round, RoundPlayer, ScoreEntry, User

        self.app = create_app()
        self.db = db
        self.Course = Course
        self.CourseHole = CourseHole
        self.GarminRoundSync = GarminRoundSync
        self.Player = Player
        self.Round = Round
        self.RoundPlayer = RoundPlayer
        self.ScoreEntry = ScoreEntry
        self.User = User

    def tearDown(self):
        self.tmpdir.cleanup()
        if self.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.previous_database_url

    def _round(self):
        course = self.Course(name="Haga BLÅ+RØD", hole_count=3)
        player = self.Player(name="Garmin Testspiller", default_hcp=3.0)
        self.db.session.add_all([course, player])
        self.db.session.flush()
        user = self.User(username="garmin_test", password_hash="test", player_id=player.id)
        self.db.session.add(user)
        self.db.session.add_all([
            self.CourseHole(course_id=course.id, hole_number=1, par=3, stroke_index=3),
            self.CourseHole(course_id=course.id, hole_number=2, par=4, stroke_index=1),
            self.CourseHole(course_id=course.id, hole_number=3, par=5, stroke_index=2),
        ])
        round_obj = self.Round(
            course_id=course.id,
            status="finished",
            started_at=datetime(2026, 7, 10, 12, 55),
            finished_at=datetime(2026, 7, 10, 17, 10),
            played_hole_count=3,
        )
        self.db.session.add(round_obj)
        self.db.session.flush()
        round_player = self.RoundPlayer(
            round_id=round_obj.id,
            player_id=player.id,
            player_name_snapshot=player.name,
            hcp_for_round=3.0,
            tracks_stats=False,
        )
        self.db.session.add(round_player)
        self.db.session.flush()
        for hole, strokes in ((1, 3), (2, 4), (3, 5)):
            self.db.session.add(self.ScoreEntry(
                round_id=round_obj.id,
                round_player_id=round_player.id,
                hole_number=hole,
                strokes=strokes,
            ))
        self.db.session.commit()
        return user, round_obj, round_player

    @staticmethod
    def _shot_payload(hole, distance, club_id, club_type_id):
        return {
            "holeShots": [{
                "holeNumber": hole,
                "shots": [{
                    "shotOrder": 1,
                    "shotType": "TEE",
                    "meters": distance,
                    "clubId": club_id,
                    "excludeFromStats": False,
                }],
            }],
            "clubDetails": [{"id": club_id, "clubTypeId": club_type_id}],
        }

    def test_matches_and_imports_par_four_and_five_tee_data(self):
        from services.garmin_golf import sync_round_from_garmin

        with self.app.app_context():
            user, round_obj, round_player = self._round()
            summary = {"scorecardSummaries": [{
                "id": 371718841,
                "courseName": "Haga Golfklubb ~ Blue/Red",
                "startTime": "2026-07-10T10:53:30.000Z",
                "holesCompleted": 3,
                "holePars": "345",
                "strokes": 12,
                "roundInProgress": False,
            }]}
            client = FakeGarminClient(summary, {
                2: self._shot_payload(2, 211.4, 1001, 1),
                3: self._shot_payload(3, 187.6, 1002, 5),
            })

            result = sync_round_from_garmin(round_obj, round_player, user, client=client)
            self.db.session.commit()

            entries = {entry.hole_number: entry for entry in round_player.score_entries}
            self.assertIsNone(entries[1].detailed_stat)
            self.assertEqual(entries[2].detailed_stat.drive_distance_m, 211)
            self.assertEqual(entries[2].tee_club.name, "Driver")
            self.assertEqual(entries[3].detailed_stat.drive_distance_m, 188)
            self.assertEqual(entries[3].tee_club.name, "2 hybrid")
            self.assertEqual(client.requested_holes, ["2", "3"])
            self.assertTrue(round_player.tracks_stats)
            self.assertEqual(result["distances_updated"], 2)
            self.assertEqual(result["clubs_updated"], 2)
            sync_row = self.GarminRoundSync.query.filter_by(round_id=round_obj.id).one()
            self.assertEqual(sync_row.scorecard_id, 371718841)

    def test_rejects_a_round_with_a_different_score(self):
        from services.garmin_golf import GarminGolfSyncError, match_garmin_scorecard

        with self.app.app_context():
            _user, round_obj, round_player = self._round()
            payload = {"scorecardSummaries": [{
                "id": 123,
                "courseName": "Haga Golfklubb ~ Blue/Red",
                "startTime": "2026-07-10T10:53:30.000Z",
                "holesCompleted": 3,
                "holePars": "345",
                "strokes": 13,
                "roundInProgress": False,
            }]}
            with self.assertRaisesRegex(GarminGolfSyncError, "matcher dato, bane, hull og score"):
                match_garmin_scorecard(round_obj, round_player, payload)


if __name__ == "__main__":
    unittest.main()
