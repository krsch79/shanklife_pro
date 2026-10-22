import tempfile
import sqlite3
from werkzeug.security import generate_password_hash
import unittest
from pathlib import Path

from balletour_survey.app import create_app
from balletour_survey.database import list_features


class BalleTourSurveyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        database_path = Path(self.tmpdir.name) / "survey.db"
        self.app = create_app(f"sqlite:///{database_path}")
        auth = Path(self.tmpdir.name) / "auth.db"
        with sqlite3.connect(auth) as conn:
            conn.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,email TEXT,password_hash TEXT); CREATE TABLE app_registry(id INTEGER PRIMARY KEY,slug TEXT,is_active INTEGER); CREATE TABLE user_app_access(user_id INTEGER,app_id INTEGER,has_access INTEGER,is_app_admin INTEGER); INSERT INTO app_registry VALUES(1,'survey',1); INSERT INTO user_app_access VALUES(1,1,1,1);")
            conn.execute("INSERT INTO users VALUES(1,'tester','test@example.invalid',?)", (generate_password_hash("test-password"),))
        self.auth = auth
        self.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False, SHANKLIFE_DB_PATH=str(auth), SECURITY_STATE_DB=str(Path(self.tmpdir.name) / "security.db"))
        self.client = self.app.test_client()
        self.assertEqual(self.client.post("/_security/login", data={"username":"tester","password":"test-password"}).status_code, 302)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_creates_and_exports_point_feature(self):
        response = self.client.post(
            "/api/features",
            json={
                "name": "Hull 1 tee",
                "feature_type": "tee",
                "hole_number": "1",
                "geometry": {"type": "Point", "coordinates": [10.5886, 59.9148]},
                "accuracy_m": "4.4",
            },
        )

        self.assertEqual(response.status_code, 201)
        feature = response.get_json()["feature"]
        self.assertEqual(feature["properties"]["name"], "Hull 1 tee")
        self.assertEqual(feature["properties"]["hole_number"], 1)

        export_response = self.client.get("/api/export.geojson")
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response.get_json()["features"][0]["geometry"]["type"], "Point")

    def test_anonymous_and_revoked_users_cannot_modify_features(self):
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.post("/api/features", json={}).status_code, 401)
        self.assertEqual(anonymous.delete("/api/features/1").status_code, 401)
        with sqlite3.connect(self.auth) as conn:
            conn.execute("UPDATE user_app_access SET has_access=0")
        self.assertEqual(self.client.post("/api/features", json={}).status_code, 401)

    def test_rejects_invalid_coordinates(self):
        response = self.client.post(
            "/api/features",
            json={
                "name": "Feil",
                "feature_type": "tee",
                "geometry": {"type": "Point", "coordinates": [1000, 59.9148]},
            },
        )

        self.assertEqual(response.status_code, 400)
        engine = self.app.config["SURVEY_ENGINE"]
        self.assertEqual(list_features(engine), [])


if __name__ == "__main__":
    unittest.main()
