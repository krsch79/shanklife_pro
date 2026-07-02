import tempfile
import unittest
from pathlib import Path

from balletour_survey.app import create_app
from balletour_survey.database import list_features


class BalleTourSurveyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        database_path = Path(self.tmpdir.name) / "survey.db"
        self.app = create_app(f"sqlite:///{database_path}")
        self.client = self.app.test_client()

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
