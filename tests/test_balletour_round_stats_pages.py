import os
import tempfile
import unittest
from datetime import datetime

from werkzeug.security import generate_password_hash


class BalleTourRoundStatsPagesTests(unittest.TestCase):
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
            Player,
            Round,
            RoundPlayer,
            ScoreEntry,
            ScoreStat,
            Series,
            SeriesPlayer,
            User,
        )

        self.app = create_app()
        self.app.config["TESTING"] = True
        self.db = db

        with self.app.app_context():
            player = Player(name="Rundestatistikkspiller", default_hcp=8.2)
            db.session.add(player)
            db.session.flush()
            user = User(
                username="rundestatistikk@example.com",
                password_hash=generate_password_hash("hemmelig"),
                player_id=player.id,
                email="rundestatistikk@example.com",
            )
            db.session.add(user)
            db.session.flush()

            db.session.execute(db.text(
                "CREATE TABLE IF NOT EXISTS app_registry ("
                "id INTEGER PRIMARY KEY, slug VARCHAR(80) NOT NULL UNIQUE)"
            ))
            db.session.execute(db.text(
                "CREATE TABLE IF NOT EXISTS user_app_access ("
                "user_id INTEGER NOT NULL, app_id INTEGER NOT NULL, "
                "has_access BOOLEAN NOT NULL DEFAULT 0, is_app_admin BOOLEAN NOT NULL DEFAULT 0, "
                "PRIMARY KEY (user_id, app_id))"
            ))
            db.session.execute(db.text(
                "INSERT OR IGNORE INTO app_registry (id, slug) VALUES (2, 'balletour')"
            ))
            db.session.execute(
                db.text(
                    "INSERT OR REPLACE INTO user_app_access "
                    "(user_id, app_id, has_access, is_app_admin) VALUES (:user_id, 2, 1, 0)"
                ),
                {"user_id": user.id},
            )

            course = Course(name="BalleTour rundestatistikkbane", hole_count=2)
            db.session.add(course)
            db.session.flush()
            holes = [
                CourseHole(course_id=course.id, hole_number=1, par=3, stroke_index=1),
                CourseHole(course_id=course.id, hole_number=2, par=4, stroke_index=2),
            ]
            db.session.add_all(holes)
            tee = CourseTee(course_id=course.id, name="Gul", display_order=1)
            series = Series(name="Balletour", course_id=course.id, min_qualifying_rounds=1)
            db.session.add_all([tee, series])
            db.session.flush()
            db.session.add(SeriesPlayer(series_id=series.id, player_id=player.id, display_order=1))

            round_obj = Round(
                course_id=course.id,
                status="finished",
                started_at=datetime(2026, 8, 29, 10, 0),
                finished_at=datetime(2026, 8, 29, 11, 0),
                played_hole_count=2,
            )
            db.session.add(round_obj)
            db.session.flush()
            round_player = RoundPlayer(
                round_id=round_obj.id,
                player_id=player.id,
                selected_tee_id=tee.id,
                player_name_snapshot=player.name,
                hcp_for_round=player.default_hcp,
                tracks_stats=True,
            )
            db.session.add(round_player)
            db.session.flush()
            entries = [
                ScoreEntry(
                    round_id=round_obj.id,
                    round_player_id=round_player.id,
                    hole_number=1,
                    strokes=4,
                ),
                ScoreEntry(
                    round_id=round_obj.id,
                    round_player_id=round_player.id,
                    hole_number=2,
                    strokes=4,
                ),
            ]
            db.session.add_all(entries)
            db.session.flush()
            db.session.add_all([
                ScoreStat(
                    score_entry_id=entries[0].id,
                    fairway_result="hit",
                    putts=2,
                    last_putt_distance_m=0.7,
                ),
                ScoreStat(
                    score_entry_id=entries[1].id,
                    fairway_result="hit",
                    putts=2,
                    drive_distance_m=210,
                    last_putt_distance_m=0.5,
                ),
            ])
            db.session.commit()
            self.user_id = user.id
            self.round_id = round_obj.id

        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def tearDown(self):
        self.tmpdir.cleanup()
        if self.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.previous_database_url

    def test_finished_round_cards_show_compact_stats_and_detail_link(self):
        response = self.client.get("/balletour/rounds/finished?tee=yellow")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("GIR 1/2", html)
        self.assertIn("· 50.0%", html)
        self.assertIn("FW 1/1", html)
        self.assertIn("4 putter", html)
        self.assertIn("Se rundestatistikk", html)
        self.assertIn(f'/balletour/rounds/{self.round_id}', html)

    def test_round_detail_shows_balletour_scorecard_and_per_round_stats(self):
        response = self.client.get(f"/balletour/rounds/{self.round_id}?tee=yellow")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Fullført BalleTour-runde", html)
        self.assertIn("Rundestatistikk", html)
        self.assertIn("GIR · 50.0%", html)
        self.assertIn("Fairwaytreff · 100.0%", html)
        self.assertIn("Hull for hull", html)
        self.assertIn("Tilbake til fullførte runder", html)

    def test_round_detail_rejects_non_balletour_round(self):
        from models import Course, Round

        with self.app.app_context():
            other_course = Course(name="Annen bane", hole_count=1)
            self.db.session.add(other_course)
            self.db.session.flush()
            other_round = Round(course_id=other_course.id, status="finished")
            self.db.session.add(other_round)
            self.db.session.commit()
            other_round_id = other_round.id

        response = self.client.get(f"/balletour/rounds/{other_round_id}")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
