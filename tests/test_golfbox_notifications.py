import unittest
from unittest.mock import patch

from services.golfbox_notifications import _booking_body, _booking_datetime


class GolfBoxNotificationTests(unittest.TestCase):
    def test_booking_datetime_uses_start_of_time_window(self):
        value = _booking_datetime({"date": "2026-06-22", "time": "16:30", "time_to": "17:30"})

        self.assertEqual(value.isoformat(), "2026-06-22T16:30:00")

    @patch("services.golfbox_notifications._weather_text", return_value="Vær ikke tilgjengelig")
    def test_failed_booking_email_includes_reason_and_players(self, _weather):
        body = _booking_body("scheduled_failed", {
            "course": "Haga",
            "date": "2026-06-22",
            "time": "16:30",
            "time_to": "17:30",
            "player_memberships": [
                {"player_name": "Kristian Schiander", "member_number": "65-110"},
            ],
            "message": "GolfBox avviste bookingen.",
        })

        self.assertIn("kunne ikke gjennomføres", body)
        self.assertIn("Tid: 16:30-17:30", body)
        self.assertIn("Kristian Schiander", body)
        self.assertIn("Resultat: GolfBox avviste bookingen.", body)

    @patch("services.golfbox_notifications._weather_text", return_value="Vær ikke tilgjengelig")
    def test_expired_watch_email_explains_no_booking(self, _weather):
        body = _booking_body("watch_expired", {
            "course": "Ballerud",
            "date": "2026-06-22",
            "time": "17:00",
            "time_to": "19:00",
            "players": ["Kristian"],
            "message": "Ledighetssøket utløp uten booking.",
        })

        self.assertIn("utløp uten", body)
        self.assertIn("Ledighetssøket utløp uten booking", body)


if __name__ == "__main__":
    unittest.main()
