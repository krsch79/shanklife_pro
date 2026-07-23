import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch


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
        self.db.session.flush()
        self.db.session.execute(self.db.text(
            "CREATE TABLE IF NOT EXISTS app_registry ("
            "id INTEGER PRIMARY KEY, slug VARCHAR(80) NOT NULL UNIQUE)"
        ))
        self.db.session.execute(self.db.text(
            "CREATE TABLE IF NOT EXISTS user_app_access ("
            "user_id INTEGER NOT NULL, app_id INTEGER NOT NULL, "
            "has_access BOOLEAN NOT NULL DEFAULT 0, is_app_admin BOOLEAN NOT NULL DEFAULT 0, "
            "PRIMARY KEY (user_id, app_id))"
        ))
        self.db.session.execute(
            self.db.text("INSERT OR IGNORE INTO app_registry (id, slug) VALUES (1, 'shanklife-pro')")
        )
        self.db.session.execute(
            self.db.text(
                "INSERT OR REPLACE INTO user_app_access "
                "(user_id, app_id, has_access, is_app_admin) VALUES (:user_id, 1, 1, 0)"
            ),
            {"user_id": user.id},
        )
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

    def test_accepts_unique_round_with_a_different_score(self):
        from services.garmin_golf import match_garmin_scorecard

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
            matched = match_garmin_scorecard(round_obj, round_player, payload)
            self.assertEqual(matched["id"], 123)

    def test_explains_when_only_hole_count_differs(self):
        from services.garmin_golf import GarminGolfSyncError, match_garmin_scorecard

        with self.app.app_context():
            _user, round_obj, round_player = self._round()
            payload = {"scorecardSummaries": [{
                "id": 124,
                "courseName": "Haga Golfklubb ~ Blue/Red",
                "startTime": "2026-07-10T10:53:30.000Z",
                "holesCompleted": 9,
                "holePars": "345345345",
                "strokes": 40,
                "roundInProgress": False,
            }]}
            with self.assertRaisesRegex(
                GarminGolfSyncError,
                "har 9 hull, mens Shanklife-runden har 3",
            ):
                match_garmin_scorecard(round_obj, round_player, payload)

    def test_prevents_second_sync(self):
        from services.garmin_golf import GarminGolfSyncError, sync_round_from_garmin

        with self.app.app_context():
            user, round_obj, round_player = self._round()
            self.db.session.add(self.GarminRoundSync(
                round_id=round_obj.id,
                user_id=user.id,
                scorecard_id=123,
            ))
            self.db.session.commit()
            with self.assertRaisesRegex(GarminGolfSyncError, "allerede synkronisert"):
                sync_round_from_garmin(round_obj, round_player, user, client=FakeGarminClient({}, {}))

    def test_finished_rounds_shows_status_and_bulk_selection(self):
        with self.app.app_context():
            user, round_obj, _round_player = self._round()
            user_id = user.id
            round_id = round_obj.id

        client = self.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
        with patch("routes.rounds.garmin_connection_available", return_value=True):
            response = client.get("/rounds/finished")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Ikke synkronisert med Garmin", html)
        self.assertIn(f'value="{round_id}"', html)
        self.assertIn("Synkroniser valgte med Garmin", html)

        with self.app.app_context():
            self.db.session.add(self.GarminRoundSync(
                round_id=round_id,
                user_id=user_id,
                scorecard_id=123,
            ))
            self.db.session.commit()
        with patch("routes.rounds.garmin_connection_available", return_value=True):
            response = client.get("/rounds/finished")
        html = response.get_data(as_text=True)
        self.assertIn("Synkronisert med Garmin", html)
        self.assertNotIn(f'value="{round_id}"', html)

    def test_bulk_sync_reports_specific_round_failure(self):
        from services.garmin_golf import GarminGolfSyncError

        with self.app.app_context():
            user, round_obj, _round_player = self._round()
            user_id = user.id
            round_id = round_obj.id

        client = self.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
        with (
            patch("routes.rounds.garmin_client_for_user", return_value=object()),
            patch(
                "routes.rounds.sync_round_from_garmin",
                side_effect=GarminGolfSyncError("Garmin har ingen fullført golfrunde på datoen."),
            ),
        ):
            response = client.post(
                "/rounds/garmin-sync",
                data={"round_ids": str(round_id)},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f"#{round_id}: Garmin har ingen fullført golfrunde",
            response.get_data(as_text=True),
        )

    def test_automatic_sync_runs_when_round_is_finished(self):
        from flask import g
        from routes.rounds import _try_automatic_garmin_sync

        with self.app.test_request_context("/"):
            user, round_obj, _round_player = self._round()
            g.current_user = user
            result = {
                "scorecard_id": 123,
                "distances_updated": 2,
                "clubs_updated": 2,
                "unmapped_clubs": 0,
                "local_total": 12,
                "garmin_total": 12,
                "score_difference": 0,
            }
            with (
                patch("routes.rounds.garmin_connection_available", return_value=True),
                patch("routes.rounds.sync_round_from_garmin", return_value=result) as sync_mock,
            ):
                _try_automatic_garmin_sync(round_obj)
            sync_mock.assert_called_once_with(round_obj, _round_player, user)


if __name__ == "__main__":
    unittest.main()
