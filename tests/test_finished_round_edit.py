import os
import tempfile
import unittest
from datetime import datetime


class FinishedRoundEditTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.tmpdir.name}/test.db"

        from app import create_app
        from extensions import db
        from models import Course, CourseHole, CourseTee, CourseTeeLength, Player, Round, RoundPlayer, ScoreEntry, User

        self.app = create_app()
        self.db = db
        self.Course = Course
        self.CourseHole = CourseHole
        self.CourseTee = CourseTee
        self.CourseTeeLength = CourseTeeLength
        self.Player = Player
        self.Round = Round
        self.RoundPlayer = RoundPlayer
        self.ScoreEntry = ScoreEntry
        self.User = User

        with self.app.app_context():
            self._seed_round()

    def tearDown(self):
        self.tmpdir.cleanup()
        if self.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.previous_database_url

    def _seed_round(self):
        player = self.Player(name="Redigeringsspiller", default_hcp=8.2)
        other_player = self.Player(name="Vanlig bruker", default_hcp=12.4)
        self.db.session.add_all([player, other_player])
        self.db.session.flush()

        admin = self.User(
            username="rundeadmin",
            password_hash="test",
            player_id=player.id,
            is_admin=True,
        )
        regular_user = self.User(
            username="rundebruker",
            password_hash="test",
            player_id=other_player.id,
            is_admin=False,
        )
        self.db.session.add_all([admin, regular_user])
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
        for user in (admin, regular_user):
            self.db.session.execute(
                self.db.text(
                    "INSERT OR REPLACE INTO user_app_access "
                    "(user_id, app_id, has_access, is_app_admin) VALUES (:user_id, 1, 1, :is_admin)"
                ),
                {"user_id": user.id, "is_admin": int(user.is_admin)},
            )

        course = self.Course(name="Redigeringsbanen", hole_count=18)
        other_course = self.Course(name="Annen bane", hole_count=18)
        self.db.session.add_all([course, other_course])
        self.db.session.flush()
        tee_58 = self.CourseTee(course_id=course.id, name="58", display_order=1)
        tee_54 = self.CourseTee(course_id=course.id, name="54", display_order=2)
        foreign_tee = self.CourseTee(course_id=other_course.id, name="Ugyldig tee", display_order=1)
        self.db.session.add_all([tee_58, tee_54, foreign_tee])
        self.db.session.flush()

        holes = []
        for hole_number in range(1, 19):
            hole = self.CourseHole(
                course_id=course.id,
                hole_number=hole_number,
                par=4,
                stroke_index=hole_number,
            )
            self.db.session.add(hole)
            holes.append(hole)
        self.db.session.flush()
        self.db.session.add_all([
            self.CourseTeeLength(tee_id=tee_58.id, hole_id=holes[0].id, hole_number=1, length_meters=385),
            self.CourseTeeLength(tee_id=tee_54.id, hole_id=holes[0].id, hole_number=1, length_meters=350),
        ])

        finished_at = datetime(2026, 8, 5, 14, 30)
        round_obj = self.Round(
            course_id=course.id,
            status="finished",
            started_at=datetime(2026, 8, 5, 10, 0),
            finished_at=finished_at,
            played_hole_count=18,
            starting_hole_number=1,
        )
        self.db.session.add(round_obj)
        self.db.session.flush()
        round_player = self.RoundPlayer(
            round_id=round_obj.id,
            player_id=player.id,
            selected_tee_id=tee_58.id,
            player_name_snapshot=player.name,
            hcp_for_round=player.default_hcp,
            tracks_stats=False,
        )
        self.db.session.add(round_player)
        self.db.session.flush()
        for hole_number in range(1, 19):
            self.db.session.add(self.ScoreEntry(
                round_id=round_obj.id,
                round_player_id=round_player.id,
                hole_number=hole_number,
                strokes=5,
            ))
        self.db.session.commit()

        self.admin_id = admin.id
        self.regular_user_id = regular_user.id
        self.round_id = round_obj.id
        self.round_player_id = round_player.id
        self.original_tee_id = tee_58.id
        self.new_tee_id = tee_54.id
        self.foreign_tee_id = foreign_tee.id
        self.finished_at = finished_at

    def _client(self, user_id):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
        return client

    def test_admin_edit_page_shows_real_course_tees_and_current_selection(self):
        response = self._client(self.admin_id).get(f"/rounds/{self.round_id}/hole/1?edit=1")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(f'name="selected_tee_{self.round_player_id}"', html)
        self.assertIn(f'value="{self.original_tee_id}" selected', html)
        self.assertIn(">58</option>", html)
        self.assertIn(">54</option>", html)
        self.assertIn("385 m på hull 1", html)
        self.assertIn("Lagre og lukk", html)

    def test_admin_can_change_tee_and_save_without_reopening_round(self):
        response = self._client(self.admin_id).post(
            f"/rounds/{self.round_id}/hole/1?edit=1",
            data={
                "action": "save_exit",
                f"selected_tee_{self.round_player_id}": str(self.new_tee_id),
                f"score_{self.round_player_id}": "5",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith(f"/rounds/{self.round_id}/score"))
        with self.app.app_context():
            round_obj = self.db.session.get(self.Round, self.round_id)
            round_player = self.db.session.get(self.RoundPlayer, self.round_player_id)
            self.assertEqual(round_player.selected_tee_id, self.new_tee_id)
            self.assertEqual(round_obj.status, "finished")
            self.assertEqual(round_obj.finished_at, self.finished_at)

    def test_tee_from_another_course_is_rejected_without_partial_changes(self):
        response = self._client(self.admin_id).post(
            f"/rounds/{self.round_id}/hole/1?edit=1",
            data={
                "action": "save_exit",
                f"selected_tee_{self.round_player_id}": str(self.foreign_tee_id),
                f"score_{self.round_player_id}": "6",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("finnes ikke på banen", response.get_data(as_text=True))
        with self.app.app_context():
            round_player = self.db.session.get(self.RoundPlayer, self.round_player_id)
            score = self.ScoreEntry.query.filter_by(
                round_id=self.round_id,
                round_player_id=self.round_player_id,
                hole_number=1,
            ).one()
            self.assertEqual(round_player.selected_tee_id, self.original_tee_id)
            self.assertEqual(score.strokes, 5)

    def test_non_admin_cannot_change_tee_on_finished_round(self):
        client = self._client(self.regular_user_id)
        page = client.get(f"/rounds/{self.round_id}/hole/1?edit=1")
        self.assertNotIn(f'name="selected_tee_{self.round_player_id}"', page.get_data(as_text=True))

        response = client.post(
            f"/rounds/{self.round_id}/hole/1?edit=1",
            data={
                "action": "save_exit",
                f"selected_tee_{self.round_player_id}": str(self.new_tee_id),
                f"score_{self.round_player_id}": "5",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            round_player = self.db.session.get(self.RoundPlayer, self.round_player_id)
            self.assertEqual(round_player.selected_tee_id, self.original_tee_id)


if __name__ == "__main__":
    unittest.main()
