from datetime import timedelta
from pathlib import Path
import unittest

from app import app


class PwaSessionTests(unittest.TestCase):
    def test_long_lived_session_configuration(self):
        self.assertEqual(app.config["PERMANENT_SESSION_LIFETIME"], timedelta(days=180))
        self.assertTrue(app.config["SESSION_REFRESH_EACH_REQUEST"])
        self.assertTrue(app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(app.config["SESSION_COOKIE_SAMESITE"], "Lax")

    def test_install_files_are_public_and_profile_aware(self):
        client = app.test_client()
        shanklife = client.get("/manifest.webmanifest", base_url="https://pro.shanklife.no")
        balletour = client.get("/manifest.webmanifest?app=balletour", base_url="https://pro.shanklife.no")
        worker = client.get("/sw.js", base_url="https://pro.shanklife.no")
        self.assertEqual(shanklife.status_code, 200)
        self.assertEqual(shanklife.mimetype, "application/manifest+json")
        self.assertEqual(shanklife.get_json()["start_url"], "/")
        self.assertEqual(shanklife.get_json()["display"], "standalone")
        self.assertEqual(balletour.status_code, 200)
        self.assertEqual(balletour.get_json()["start_url"], "/balletour/")
        self.assertEqual(balletour.get_json()["scope"], "/balletour/")
        self.assertEqual(worker.status_code, 200)
        self.assertEqual(worker.headers["Service-Worker-Allowed"], "/")
        shanklife.close()
        balletour.close()
        worker.close()

    def test_base_template_has_ios_install_metadata(self):
        source = (Path(app.root_path) / "templates/base.html").read_text(encoding="utf-8")
        self.assertIn('name="apple-mobile-web-app-capable" content="yes"', source)
        self.assertIn('rel="apple-touch-icon"', source)
        self.assertIn('serviceWorker.register("/sw.js"', source)


if __name__ == "__main__":
    unittest.main()
