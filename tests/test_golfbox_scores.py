import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from services.golfbox import _form_inputs
from services.golfbox_scores import _best_course, _normalize_api_option


class GolfBoxScoreSubmissionTests(unittest.TestCase):
    def test_form_inputs_send_checked_checkbox_without_value_as_on(self):
        page_html = """
            <input type="checkbox" name="chk_IsCounting" checked="checked">
            <input type="checkbox" name="chk_UnknownCourse">
            <input type="checkbox" name="chk_InputHoleScores" checked="checked" value="yes">
        """

        form_data = _form_inputs(page_html)

        self.assertEqual(form_data["chk_IsCounting"], "on")
        self.assertEqual(form_data["chk_InputHoleScores"], "yes")
        self.assertNotIn("chk_UnknownCourse", form_data)

    def test_best_course_matches_local_golfbane_to_golfbox_gk_name(self):
        courses = [
            {"course_name": "Åpen Ballrenne morgen", "course_guid": "ballrenne"},
            {"course_name": "Drøbak GK 18 hull", "course_guid": "drobak-18"},
            {"course_name": "Drøbak GK 9 hull front 2020", "course_guid": "drobak-9"},
        ]

        course = _best_course(courses, "Drøbak golfbane", 18)

        self.assertIsNotNone(course)
        self.assertEqual(course["course_guid"], "drobak-18")

    def test_normalize_api_option_parses_false_hcp_qualifying_text(self):
        option = _normalize_api_option({
            "Course_GUID": "course-id",
            "Course_Name": "Testbane",
            "Course_isHcpQualifying": "False",
        })

        self.assertFalse(option["is_hcp_qualifying"])


class GolfBoxScoreRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.tmpdir.name}/test.db"

        from app import create_app
        from extensions import db
        from models import (
            Course,
            CourseHole,
            CourseTee,
            GolfBoxScoreSubmission,
            Player,
            Round,
            RoundPlayer,
            ScoreEntry,
            User,
        )

        self.app = create_app()
        self.db = db
        self.GolfBoxScoreSubmission = GolfBoxScoreSubmission
        self.database_path = f"{self.tmpdir.name}/test.db"

        with self.app.app_context():
            player = Player(name="GolfBox-rutespiller", default_hcp=9.4)
            self.db.session.add(player)
            self.db.session.flush()
            user = User(username="golfbox-rutebruker", password_hash="test", player_id=player.id)
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
            self.db.session.execute(self.db.text(
                "INSERT OR IGNORE INTO app_registry (id, slug) VALUES (1, 'shanklife-pro')"
            ))
            self.db.session.execute(
                self.db.text(
                    "INSERT OR REPLACE INTO user_app_access "
                    "(user_id, app_id, has_access, is_app_admin) VALUES (:user_id, 1, 1, 0)"
                ),
                {"user_id": user.id},
            )

            course = Course(name="GolfBox-rutebane", hole_count=9)
            self.db.session.add(course)
            self.db.session.flush()
            tee = CourseTee(course_id=course.id, name="50", display_order=1)
            self.db.session.add(tee)
            self.db.session.flush()
            for hole_number in range(1, 10):
                self.db.session.add(CourseHole(
                    course_id=course.id,
                    hole_number=hole_number,
                    par=4,
                    stroke_index=hole_number,
                ))

            round_obj = Round(
                course_id=course.id,
                status="finished",
                started_at=datetime(2026, 8, 10, 10, 0),
                finished_at=datetime(2026, 8, 10, 12, 0),
                played_hole_count=9,
                starting_hole_number=1,
            )
            self.db.session.add(round_obj)
            self.db.session.flush()
            round_player = RoundPlayer(
                round_id=round_obj.id,
                player_id=player.id,
                selected_tee_id=tee.id,
                player_name_snapshot=player.name,
                hcp_for_round=player.default_hcp,
            )
            self.db.session.add(round_player)
            self.db.session.flush()
            for hole_number in range(1, 10):
                self.db.session.add(ScoreEntry(
                    round_id=round_obj.id,
                    round_player_id=round_player.id,
                    hole_number=hole_number,
                    strokes=5,
                ))
            self.db.session.commit()

            self.user_id = user.id
            self.round_id = round_obj.id
            self.round_player_id = round_player.id

    def tearDown(self):
        with self.app.app_context():
            self.db.session.remove()
            self.db.engine.dispose()
        self.tmpdir.cleanup()
        if self.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.previous_database_url

    def _client(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
        return client

    @patch("routes.golfbox_scores.score_course_suggestions", return_value=[])
    def test_repeated_prepare_gets_do_not_create_or_lock_submission(self, _suggestions):
        client = self._client()

        first_response = client.get(f"/rounds/{self.round_id}/golfbox")
        second_response = client.get(f"/rounds/{self.round_id}/golfbox")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        with self.app.app_context():
            self.assertEqual(
                self.GolfBoxScoreSubmission.query.filter_by(round_player_id=self.round_player_id).count(),
                0,
            )

    @patch("routes.golfbox_scores.score_course_suggestions", return_value=[])
    def test_prepare_get_succeeds_while_another_writer_holds_lock(self, _suggestions):
        client = self._client()

        with sqlite3.connect(self.database_path) as writer:
            writer.execute("BEGIN IMMEDIATE")
            response = client.get(f"/rounds/{self.round_id}/golfbox")

        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            self.assertEqual(
                self.GolfBoxScoreSubmission.query.filter_by(round_player_id=self.round_player_id).count(),
                0,
            )

    @patch("routes.golfbox_scores.search_marker", return_value=[])
    @patch("routes.golfbox_scores.score_course_suggestions", return_value=[])
    def test_repeated_marker_posts_reuse_one_submission(self, _suggestions, _search):
        client = self._client()
        form = {"action": "search_marker", "marker_query": "Test"}

        first_response = client.post(f"/rounds/{self.round_id}/golfbox", data=form)
        second_response = client.post(f"/rounds/{self.round_id}/golfbox", data=form)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        with self.app.app_context():
            self.assertEqual(
                self.GolfBoxScoreSubmission.query.filter_by(round_player_id=self.round_player_id).count(),
                1,
            )


if __name__ == "__main__":
    unittest.main()
