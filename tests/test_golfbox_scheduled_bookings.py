import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from services.golfbox import _scheduled_pending_booking, confirm_golfbox_booking


class GolfBoxScheduledBookingTests(unittest.TestCase):
    def test_scheduled_booking_does_not_reuse_ballerud_identifiers(self):
        booking = SimpleNamespace(course="Haga", play_date=date(2026, 6, 27), play_time="10:00")
        players = [{"player_name": "Kristian", "member_number": "308-5930", "club_name": "Haga Golfklubb"}]

        pending = _scheduled_pending_booking(booking, players)

        self.assertEqual(pending["course"], "Haga")
        self.assertNotIn("club_guid", pending)
        self.assertNotIn("resource_guid", pending)

    @patch("services.golfbox._book_slot")
    @patch("services.golfbox._resolve_course")
    @patch("services.golfbox._credentials_for_user")
    def test_confirmation_resolves_identifiers_for_non_ballerud_course(self, credentials, resolve_course, book_slot):
        credentials.return_value = {"username": "user", "password": "secret"}
        resolve_course.return_value = {
            "club_guid": "haga-club",
            "resource_guid": "haga-course",
            "course": "Haga Golf Hovedbane",
        }
        book_slot.return_value = {"status": "wrong_membership", "message": "stopped"}
        pending = {
            "course": "Haga",
            "date": "2026-06-27",
            "time": "10:00",
            "player_memberships": [],
        }

        confirm_golfbox_booking(pending, user=SimpleNamespace())

        resolve_course.assert_called_once_with(credentials.return_value, "Haga")
        self.assertEqual(book_slot.call_args.args[5:7], ("haga-club", "haga-course"))


if __name__ == "__main__":
    unittest.main()
