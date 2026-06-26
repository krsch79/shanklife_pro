import os
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.tmpdir.name}/test.db"

        from app import create_app
        from extensions import db
        from models import Club, Course, CourseHole, CourseTee, CourseTeeLength, Player, PlayerHoleDefaultClub, Round, RoundPlayer, ScoreEntry, Series, SeriesPlayer, User

        self.app = create_app()
        self.app.config["TESTING"] = True
        self.db = db
        self.Club = Club
        self.Course = Course
        self.CourseHole = CourseHole
        self.CourseTee = CourseTee
        self.CourseTeeLength = CourseTeeLength
        self.Player = Player
        self.PlayerHoleDefaultClub = PlayerHoleDefaultClub
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
                email=None,
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
            self.db.session.flush()
            tee = self.CourseTee(course_id=course.id, name="Gul", display_order=1)
            series = self.Series(name="Balletour", course_id=course.id, min_qualifying_rounds=1)
            self.db.session.add_all([tee, series])
            self.db.session.flush()
            holes = self.CourseHole.query.filter_by(course_id=course.id).order_by(self.CourseHole.hole_number).all()
            self.db.session.add_all([
                self.CourseTeeLength(tee_id=tee.id, hole_id=holes[0].id, hole_number=1, length_meters=125),
                self.CourseTeeLength(tee_id=tee.id, hole_id=holes[1].id, hole_number=2, length_meters=240),
            ])
            if not self.Club.query.filter_by(name="J7").first():
                self.db.session.add(self.Club(name="J7", sort_order=7))
            if not self.Club.query.filter_by(name="Driver").first():
                self.db.session.add(self.Club(name="Driver", sort_order=1))
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
            return round_obj.id, player.id, tee.id

    def _create_shanklife_course_data(self):
        with self.app.app_context():
            player = self.Player.query.filter_by(name="API Testspiller").first()
            course = self.Course(name="Native Shanklife Testbane", hole_count=9)
            self.db.session.add(course)
            self.db.session.flush()
            holes = [
                self.CourseHole(
                    course_id=course.id,
                    hole_number=number,
                    par=3 if number % 3 == 0 else 4,
                    stroke_index=number,
                )
                for number in range(1, 10)
            ]
            self.db.session.add_all(holes)
            self.db.session.flush()
            tee = self.CourseTee(course_id=course.id, name="Gul", display_order=1)
            self.db.session.add(tee)
            self.db.session.flush()
            self.db.session.add_all([
                self.CourseTeeLength(
                    tee_id=tee.id,
                    hole_id=hole.id,
                    hole_number=hole.hole_number,
                    length_meters=145 if hole.par == 3 else 330,
                )
                for hole in holes
            ])
            self.db.session.commit()
            return course.id, player.id, tee.id

    def test_shanklife_round_started_mail_is_sent_without_local_simulator_header(self):
        course_id, player_id, tee_id = self._create_shanklife_course_data()
        self._login()

        with patch("routes.api._send_shanklife_round_started_mail") as send_started_mail:
            response = self.client.post(
                "/api/v1/shanklife/rounds",
                json={
                    "course_id": course_id,
                    "played_hole_count": 9,
                    "players": [{
                        "player_id": player_id,
                        "hcp": 12.3,
                        "tee_id": tee_id,
                        "tracks_stats": True,
                    }],
                },
            )

        self.assertEqual(response.status_code, 201)
        send_started_mail.assert_called_once()

    def test_shanklife_round_started_mail_is_suppressed_for_local_simulator_header(self):
        course_id, player_id, tee_id = self._create_shanklife_course_data()
        self._login()

        with patch("routes.api._send_shanklife_round_started_mail") as send_started_mail:
            response = self.client.post(
                "/api/v1/shanklife/rounds",
                headers={"X-Shanklife-Local-Client": "ios-debug-simulator"},
                json={
                    "course_id": course_id,
                    "played_hole_count": 9,
                    "players": [{
                        "player_id": player_id,
                        "hcp": 12.3,
                        "tee_id": tee_id,
                        "tracks_stats": True,
                    }],
                },
            )

        self.assertEqual(response.status_code, 201)
        send_started_mail.assert_not_called()

    def test_balletour_round_started_mail_is_sent_without_local_simulator_header(self):
        _, player_id, tee_id = self._create_balletour_data()
        self._login()

        with (
            patch("routes.api.fetch_bekkestua_weather", return_value={}),
            patch("routes.api._send_balletour_round_started_mail") as send_started_mail,
        ):
            response = self.client.post(
                "/api/v1/balletour/rounds",
                json={"players": [{"player_id": player_id, "hcp": 12.3, "tee_id": tee_id}]},
            )

        self.assertEqual(response.status_code, 201)
        send_started_mail.assert_called_once()

    def test_balletour_round_started_mail_is_suppressed_for_local_simulator_header(self):
        _, player_id, tee_id = self._create_balletour_data()
        self._login()

        with (
            patch("routes.api.fetch_bekkestua_weather", return_value={}),
            patch("routes.api._send_balletour_round_started_mail") as send_started_mail,
        ):
            response = self.client.post(
                "/api/v1/balletour/rounds",
                headers={"X-Shanklife-Local-Client": "ios-debug-simulator"},
                json={"players": [{"player_id": player_id, "hcp": 12.3, "tee_id": tee_id}]},
            )

        self.assertEqual(response.status_code, 201)
        send_started_mail.assert_not_called()

    def test_balletour_overview_requires_balletour_membership(self):
        self._login()

        response = self.client.get("/api/v1/balletour/overview")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"]["code"], "forbidden")

    def test_balletour_native_endpoints(self):
        round_id, player_id, tee_id = self._create_balletour_data()
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

    def test_balletour_round_detail_includes_default_tee_club(self):
        _, player_id, tee_id = self._create_balletour_data()
        self._login()

        with self.app.app_context():
            course = self.Course.query.filter_by(name="Balletour Testbane").first()
            club = self.Club.query.filter_by(name="J7").first()
            club_id = club.id
            self.db.session.add(self.PlayerHoleDefaultClub(
                player_id=player_id,
                course_id=course.id,
                hole_number=1,
                club_id=club_id,
            ))
            self.db.session.commit()

        with patch("routes.api.fetch_bekkestua_weather", return_value={}):
            create_response = self.client.post(
                "/api/v1/balletour/rounds",
                json={"players": [{"player_id": player_id, "hcp": 12.3, "tee_id": tee_id}]},
            )

        self.assertEqual(create_response.status_code, 201)
        round_id = create_response.get_json()["id"]

        detail = self.client.get(f"/api/v1/balletour/rounds/{round_id}")

        self.assertEqual(detail.status_code, 200)
        first_score = detail.get_json()["players"][0]["scores"][0]
        self.assertIsNone(first_score["tee_club_id"])
        self.assertEqual(first_score["default_tee_club_id"], club_id)

    def test_balletour_round_can_be_created_scored_and_finished_from_api(self):
        _, player_id, tee_id = self._create_balletour_data()
        self._login()

        setup = self.client.get("/api/v1/balletour/round-setup")
        self.assertEqual(setup.status_code, 200)
        clubs = setup.get_json()["clubs"]
        self.assertGreaterEqual(len(clubs), 1)
        first_club_id = clubs[0]["id"]
        second_club_id = clubs[1]["id"] if len(clubs) > 1 else first_club_id

        create_response = self.client.post(
            "/api/v1/balletour/rounds",
            json={"players": [{"player_id": player_id, "hcp": 12.3, "tee_id": tee_id}]},
        )
        self.assertEqual(create_response.status_code, 201)
        round_id = create_response.get_json()["id"]
        round_player_id = create_response.get_json()["players"][0]["round_player_id"]

        hole_1 = self.client.put(
            f"/api/v1/balletour/rounds/{round_id}/holes/1",
            json={
                "players": [{
                    "round_player_id": round_player_id,
                    "strokes": 3,
                    "tee_club_id": first_club_id,
                    "drive_distance_m": 125,
                    "green": {"status": "hit", "directions": ["pin"]},
                    "putts": 2,
                    "last_putt_distance_m": 0.5,
                }]
            },
        )
        self.assertEqual(hole_1.status_code, 200)

        hole_2 = self.client.put(
            f"/api/v1/balletour/rounds/{round_id}/holes/2",
            json={
                "players": [{
                    "round_player_id": round_player_id,
                    "strokes": 5,
                    "tee_club_id": second_club_id,
                    "drive_distance_m": 220,
                    "fairway_result": "right",
                    "putts": 2,
                    "last_putt_distance_m": 1.2,
                }]
            },
        )
        self.assertEqual(hole_2.status_code, 200)

        finish = self.client.post(f"/api/v1/balletour/rounds/{round_id}/finish")
        self.assertEqual(finish.status_code, 200)
        self.assertEqual(finish.get_json()["status"], "finished")

        stats = self.client.get("/api/v1/balletour/stats")
        all_stats = self.client.get("/api/v1/balletour/stats/all")
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.get_json()["stats"]["completed_round_count"], 2)
        self.assertEqual(all_stats.status_code, 200)
        self.assertGreaterEqual(len(all_stats.get_json()["rows"]), 1)

    def test_shanklife_course_and_round_can_be_created_scored_and_finished_from_api(self):
        self._login()
        with self.app.app_context():
            player = self.Player.query.filter_by(name="API Testspiller").first()
            if not self.Club.query.filter_by(name="Driver").first():
                self.db.session.add(self.Club(name="Driver", sort_order=1))
            self.db.session.commit()
            player_id = player.id

        holes = [
            {"hole_number": number, "par": 3 if number % 3 == 0 else 4, "stroke_index": number}
            for number in range(1, 10)
        ]
        lengths = {str(number): 145 if number % 3 == 0 else 330 for number in range(1, 10)}
        course_response = self.client.post(
            "/api/v1/shanklife/courses",
            json={
                "name": "Native Shanklife Testbane",
                "hole_count": 9,
                "holes": holes,
                "tees": [{"name": "Gul", "lengths": lengths}],
            },
        )
        self.assertEqual(course_response.status_code, 201)
        course_payload = course_response.get_json()
        tee_id = course_payload["tees"][0]["id"]

        setup = self.client.get("/api/v1/shanklife/setup")
        self.assertEqual(setup.status_code, 200)
        club_id = setup.get_json()["clubs"][0]["id"]

        create_response = self.client.post(
            "/api/v1/shanklife/rounds",
            json={
                "course_id": course_payload["id"],
                "played_hole_count": 9,
                "players": [{
                    "player_id": player_id,
                    "hcp": 12.3,
                    "tee_id": tee_id,
                    "tracks_stats": True,
                }],
            },
        )
        self.assertEqual(create_response.status_code, 201)
        round_payload = create_response.get_json()
        round_id = round_payload["id"]
        round_player_id = round_payload["players"][0]["round_player_id"]

        for hole in holes:
            hole_number = hole["hole_number"]
            score_response = self.client.put(
                f"/api/v1/shanklife/rounds/{round_id}/holes/{hole_number}",
                json={
                    "players": [{
                        "round_player_id": round_player_id,
                        "strokes": hole["par"],
                        "tee_club_id": club_id,
                        "drive_distance_m": lengths[str(hole_number)],
                        "green": {"status": "hit", "directions": ["pin"]},
                        "fairway_result": "hit",
                        "putts": 2,
                        "last_putt_distance_m": 1.0,
                    }]
                },
            )
            self.assertEqual(score_response.status_code, 200)

        finish = self.client.post(f"/api/v1/shanklife/rounds/{round_id}/finish")
        self.assertEqual(finish.status_code, 200)
        self.assertEqual(finish.get_json()["status"], "finished")

        rounds = self.client.get("/api/v1/shanklife/rounds?status=finished")
        self.assertEqual(rounds.status_code, 200)
        self.assertEqual(rounds.get_json()["rounds"][0]["id"], round_id)


if __name__ == "__main__":
    unittest.main()
