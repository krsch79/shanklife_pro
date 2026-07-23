import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch


class ProfilePagesTests(unittest.TestCase):
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
            GarminRoundSync,
            Player,
            Round,
            RoundPlayer,
            ScoreEntry,
            User,
        )

        self.app = create_app()
        self.db = db
        self.Course = Course
        self.CourseHole = CourseHole
        self.CourseTee = CourseTee
        self.GarminRoundSync = GarminRoundSync
        self.Player = Player
        self.Round = Round
        self.RoundPlayer = RoundPlayer
        self.ScoreEntry = ScoreEntry
        self.User = User

        with self.app.app_context():
            self.user_id, self.round_ids = self._seed_profile()

    def tearDown(self):
        self.tmpdir.cleanup()
        if self.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.previous_database_url

    def _seed_profile(self):
        player = self.Player(name="Profilspiller", default_hcp=5.4)
        self.db.session.add(player)
        self.db.session.flush()
        user = self.User(
            username="profilbruker",
            password_hash="test",
            player_id=player.id,
            email="profil@example.com",
        )
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

        course = self.Course(name="Profilbanen", hole_count=18)
        self.db.session.add(course)
        self.db.session.flush()
        tee_56 = self.CourseTee(course_id=course.id, name="56", display_order=1)
        tee_51 = self.CourseTee(course_id=course.id, name="51", display_order=2)
        self.db.session.add_all([tee_56, tee_51])
        self.db.session.flush()
        for hole_number in range(1, 19):
            self.db.session.add(self.CourseHole(
                course_id=course.id,
                hole_number=hole_number,
                par=4,
                stroke_index=hole_number,
            ))

        rounds = []
        for index, spec in enumerate((
            ("finished", datetime(2026, 7, 22, 10, 0), 18, tee_56, 4),
            ("finished", datetime(2026, 7, 20, 10, 0), 9, tee_51, 5),
            ("ongoing", datetime(2025, 8, 10, 10, 0), 18, tee_56, 4),
            ("finished", datetime(2025, 7, 1, 10, 0), 18, tee_56, 6),
        )):
            status, started_at, hole_count, tee, strokes = spec
            round_obj = self.Round(
                course_id=course.id,
                status=status,
                started_at=started_at,
                finished_at=started_at if status == "finished" else None,
                played_hole_count=hole_count,
            )
            self.db.session.add(round_obj)
            self.db.session.flush()
            round_player = self.RoundPlayer(
                round_id=round_obj.id,
                player_id=player.id,
                selected_tee_id=tee.id,
                player_name_snapshot=player.name,
                hcp_for_round=player.default_hcp,
                tracks_stats=True,
            )
            self.db.session.add(round_player)
            self.db.session.flush()
            for hole_number in range(1, hole_count + 1):
                self.db.session.add(self.ScoreEntry(
                    round_id=round_obj.id,
                    round_player_id=round_player.id,
                    hole_number=hole_number,
                    strokes=strokes,
                ))
            rounds.append(round_obj)

        self.db.session.flush()
        self.db.session.add(self.GarminRoundSync(
            round_id=rounds[0].id,
            user_id=user.id,
            scorecard_id=987654,
        ))
        self.db.session.commit()
        return user.id, [round_obj.id for round_obj in rounds]

    def _client(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user_id
        return client

    def test_min_side_is_account_page_with_three_recent_rounds(self):
        client = self._client()
        with patch("routes.profile.garmin_connection_available", return_value=True):
            response = client.get("/me")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Spillerprofil", html)
        self.assertIn("Tilkoblede tjenester", html)
        self.assertIn("Konto og varsler", html)
        self.assertIn("Mine siste runder", html)
        self.assertIn("Alle mine runder", html)
        self.assertIn("Min statistikk", html)
        self.assertNotIn("Snittscore", html)
        self.assertNotIn("Utslag par 4/5", html)
        self.assertIn("Se alle 4", html)
        self.assertIn("10.08.2025 10:00", html)
        self.assertNotIn("01.07.2025 10:00", html)

    def test_mine_runder_shows_numeric_tees_and_all_rounds(self):
        response = self._client().get("/me/rounds")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("4</strong> av 4 runder", html)
        self.assertIn("56 tee", html)
        self.assertIn("51 tee", html)
        self.assertIn("Synkronisert med Garmin", html)
        self.assertIn("Ikke synkronisert med Garmin", html)
        self.assertIn("Pågående", html)

    def test_mine_runder_filters_by_tee_holes_year_status_and_garmin(self):
        client = self._client()

        tee_response = client.get("/me/rounds?tee=51&holes=9&status=finished&year=2026")
        tee_html = tee_response.get_data(as_text=True)
        self.assertIn("1</strong> av 4 runder", tee_html)
        self.assertIn("51 tee", tee_html)
        self.assertNotIn("56 tee", tee_html)

        garmin_response = client.get("/me/rounds?garmin=synced")
        garmin_html = garmin_response.get_data(as_text=True)
        self.assertIn("1</strong> av 4 runder", garmin_html)
        self.assertIn(f"Runde {self.round_ids[0]}", garmin_html)
        self.assertNotIn(f"Runde {self.round_ids[1]}", garmin_html)


if __name__ == "__main__":
    unittest.main()
