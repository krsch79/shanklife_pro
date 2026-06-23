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
        from models import Player, User

        self.app = create_app()
        self.app.config["TESTING"] = True
        self.db = db
        self.Player = Player
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


if __name__ == "__main__":
    unittest.main()
