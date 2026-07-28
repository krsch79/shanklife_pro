import re
import unittest
from pathlib import Path


class GpsOptInUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (
            Path(__file__).resolve().parents[1] / "templates" / "round_hole.html"
        ).read_text(encoding="utf-8")

    def test_gps_button_starts_as_explicit_opt_in(self):
        button = re.search(
            r"<button[^>]*data-shot-measure-button[^>]*>(.*?)</button>",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(button)
        self.assertNotIn("disabled", button.group(0).split(">", 1)[0])
        self.assertEqual(button.group(1).strip(), "Aktiver GPS")

    def test_subscribing_does_not_start_geolocation(self):
        subscribe = self.source.split("subscribe(callback) {", 1)[1].split("},", 1)[0]
        self.assertNotIn("start();", subscribe)
        self.assertIn("activate()", self.source)

    def test_first_click_activates_gps_before_measurement(self):
        self.assertIn(
            "if (!gpsActive) {\n                gpsAccuracyTracker.activate();\n                return;",
            self.source,
        )
        self.assertIn('button.textContent = "Mål lengde";', self.source)


if __name__ == "__main__":
    unittest.main()
