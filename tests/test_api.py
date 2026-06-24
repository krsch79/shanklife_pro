import os
import tempfile
import unittest

from werkzeug.security import generate_password_hash


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.tmpdir.name}/test.db"

        from app import create_app
        from extensions import db
        from models import Course, CourseHole, CourseTee, Player, Round, RoundPlayer, ScoreEntry, Series, SeriesPlayer, User

        self.app = create_app()
        self.app.config["TESTING"] = True
        self.db = db
        self.Course = Course
        self.CourseHole = CourseHole
        self.CourseTee = CourseTee
        self.Player = Player
        self.Round = Round
        self.RoundPlayer = RoundPlayer
        self.ScoreEntry = ScoreEntry
        self.Series = Series
        self.SeriesPlayer = SeriesPlayer
        self.User = User

        with self.app.app_context():
            player = Player(name="API Testspiller", default_hcp=12.3, gender="male")
            db.session.add(player)
            db.session.flush()
            db.session.add(User(
                username="api@example.com",
                password_hash=generate_password_hash("hemmelig"),
                player_id=player.id,
                email="api@example.com",
            ))
            db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        self.tmpdir.cleanup()
        if self.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.previous_database_url

    def test_health_is_public(self):
        response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_me_requires_login_with_json_error(self):
        response = self.client.get("/api/v1/auth/me")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"]["code"], "unauthorized")

    def test_login_and_bootstrap(self):
        login_response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "api@example.com", "password": "hemmelig"},
        )

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.get_json()["user"]["username"], "api@example.com")

        bootstrap_response = self.client.get("/api/v1/bootstrap")
        payload = bootstrap_response.get_json()

        self.assertEqual(bootstrap_response.status_code, 200)
        self.assertEqual(payload["user"]["player"]["name"], "API Testspiller")
        self.assertEqual([product["id"] for product in payload["products"]], ["shanklife", "balletour"])

    def _login(self):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "api@example.com", "password": "hemmelig"},
        )
        self.assertEqual(response.status_code, 200)

    def _create_balletour_data(self):
        with self.app.app_context():
            player = self.Player.query.filter_by(name="API Testspiller").first()
            course = self.Course(name="Balletour Testbane", hole_count=2)
            self.db.session.add(course)
            self.db.session.flush()
            self.db.session.add_all([
                self.CourseHole(course_id=course.id, hole_number=1, par=3, stroke_index=1),
                self.CourseHole(course_id=course.id, hole_number=2, par=4, stroke_index=2),
            ])
            tee = self.CourseTee(course_id=course.id, name="Gul", display_order=1)
            series = self.Series(name="Balletour", course_id=course.id, min_qualifying_rounds=1)
            self.db.session.add_all([tee, series])
            self.db.session.flush()
            self.db.session.add(self.SeriesPlayer(series_id=series.id, player_id=player.id, display_order=1))
            round_obj = self.Round(course_id=course.id, status="finished")
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
            self.db.session.add_all([
                self.ScoreEntry(round_id=round_obj.id, round_player_id=round_player.id, hole_number=1, strokes=3),
                self.ScoreEntry(round_id=round_obj.id, round_player_id=round_player.id, hole_number=2, strokes=5),
            ])
            self.db.session.commit()
            return round_obj.id, player.id

    def test_balletour_overview_requires_balletour_membership(self):
        self._login()

        response = self.client.get("/api/v1/balletour/overview")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"]["code"], "forbidden")

    def test_balletour_native_endpoints(self):
        round_id, player_id = self._create_balletour_data()
        self._login()

        overview = self.client.get("/api/v1/balletour/overview")
        rounds = self.client.get("/api/v1/balletour/rounds")
        me = self.client.get("/api/v1/balletour/me")
        detail = self.client.get(f"/api/v1/balletour/rounds/{round_id}")
        player_summary = self.client.get(f"/api/v1/balletour/players/{player_id}/summary")

        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.get_json()["leaderboard"][0]["player_name"], "API Testspiller")
        self.assertEqual(rounds.status_code, 200)
        self.assertEqual(rounds.get_json()["rounds"][0]["id"], round_id)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.get_json()["player"]["id"], player_id)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["players"][0]["scores"][1]["strokes"], 5)
        self.assertEqual(player_summary.status_code, 200)
        self.assertEqual(player_summary.get_json()["finished_rounds"], 1)


if __name__ == "__main__":
    unittest.main()
