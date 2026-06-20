import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from services.golfbox import (
    _parse_member_number_lookup,
    _resolve_requested_member_memberships,
    _scheduled_pending_booking,
    confirm_golfbox_booking,
)


class GolfBoxScheduledBookingTests(unittest.TestCase):
    def test_member_number_lookup_response_is_normalized_for_storage(self):
        member = _parse_member_number_lookup(
            "{player-guid}|Øyvind Schiander|Ballerud Golfklubb|1|1||",
            "65-2560",
        )

        self.assertEqual(member["player_name"], "Øyvind Schiander")
        self.assertEqual(member["member_number"], "65-2560")
        self.assertEqual(member["club_name"], "Ballerud Golfklubb")

    @patch("services.golfbox._lookup_golfbox_members_by_number")
    def test_requested_member_number_replaces_generic_name(self, lookup):
        lookup.return_value = {
            "65-2560": {
                "player_name": "Øyvind Schiander",
                "member_number": "65-2560",
                "club_name": "Ballerud Golfklubb",
            }
        }
        memberships = [
            {"player_name": "Kristian Schiander", "member_number": "65-110", "club_name": "Ballerud Golfklubb"},
            {"player_name": "Medlemsnummer 65-2560", "member_number": "65-2560", "club_name": "Ballerud"},
        ]

        resolved, error = _resolve_requested_member_memberships(
            SimpleNamespace(),
            {"member_numbers": ["65-2560"]},
            memberships,
        )

        self.assertIsNone(error)
        self.assertEqual(resolved[1]["player_name"], "Øyvind Schiander")
        self.assertEqual(resolved[1]["club_name"], "Ballerud Golfklubb")

    @patch("services.golfbox._lookup_golfbox_members_by_number", return_value={})
    def test_unknown_member_number_stops_future_booking(self, _lookup):
        memberships = [
            {"player_name": "Medlemsnummer 65-9999", "member_number": "65-9999", "club_name": "Ballerud"},
        ]

        _, error = _resolve_requested_member_memberships(
            SimpleNamespace(),
            {"member_numbers": ["65-9999"]},
            memberships,
        )

        self.assertIn("65-9999", error)
        self.assertIn("Ingen planlagt booking ble lagret", error)

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
