import unittest
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import patch

from services.golfbox import (
    _booking_contains_expected_players,
    _booking_response_requires_payment,
    _form_inputs,
    _log_booking_submit_response,
    _parse_member_number_lookup,
    _player_memberships_for_booking_course,
    _resolve_requested_member_memberships,
    _scheduled_pending_booking,
    _verified_booking_in_my_times,
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

    def test_booking_uses_current_users_membership_for_requested_course(self):
        user = SimpleNamespace(
            username="kristian",
            player=SimpleNamespace(name="Kristian Schiander"),
            golfbox_player_name="Kristian Schiander",
            golfbox_member_number="65-110",
            golfbox_home_club_name="Ballerud Golfklubb",
            golfbox_memberships_json=(
                '[{"club_name":"Haga Golfklubb","club_guid":"{haga-guid}",'
                '"member_number":"308-5930","player_name":"Kristian Schiander"},'
                '{"club_name":"Ballerud Golfklubb","club_guid":"{ballerud-guid}",'
                '"member_number":"65-110","player_name":"Kristian Schiander"}]'
            ),
        )
        players = [{"player_name": "Kristian Schiander", "member_number": "65-110", "club_name": "Ballerud Golfklubb"}]

        memberships = _player_memberships_for_booking_course(user, "Haga Golfklubb - Haga Golf Hovedbane", players)

        self.assertEqual(memberships[0]["member_number"], "308-5930")
        self.assertEqual(memberships[0]["club_name"], "Haga Golfklubb")
        self.assertEqual(memberships[0]["club_guid"], "{haga-guid}")

    def test_payment_detection_ignores_zero_price_booking_page(self):
        page_html = """
            <input type="hidden" name="hidden_BookingPrice_0" value="0">
            <input type="hidden" name="hidden_ExtraPrice_0" value="0">
            <script>function payAndConfirm(){}</script>
            <p>Pris pr bestilling 0. Registrer betalingsmåte ved behov.</p>
        """

        self.assertFalse(_booking_response_requires_payment(page_html))

    def test_payment_detection_stops_positive_price_booking_page(self):
        page_html = '<input type="hidden" name="hidden_BookingPrice_0" value="250">'

        self.assertTrue(_booking_response_requires_payment(page_html))

    def test_form_parser_does_not_treat_javascript_checked_property_as_checked_attribute(self):
        page_html = '''
            <input type="checkbox" name="chkSearchOnly" onclick="searchOnly(this.checked);">
            <input type="checkbox" name="chkInviteFriends" onclick="inviteFriendsEvent(this.checked);">
            <input type="checkbox" name="confirmed" value="yes" checked>
        '''

        form_data = _form_inputs(page_html)

        self.assertNotIn("chkSearchOnly", form_data)
        self.assertNotIn("chkInviteFriends", form_data)
        self.assertEqual(form_data["confirmed"], "yes")

    def test_booking_verification_requires_every_expected_player(self):
        booking = {
            "player_rows": [
                {"name": "Kristian Schiander", "member_number": "308-5930"},
                {"name": "Tollef Schiander", "member_number": "308-1556"},
            ]
        }

        self.assertTrue(_booking_contains_expected_players(booking, [
            {"player_name": "Kristian Schiander", "member_number": "308-5930"},
            {"player_name": "Tollef Schiander", "member_number": "308-1556"},
        ]))
        self.assertFalse(_booking_contains_expected_players(booking, [
            {"player_name": "Kristian Schiander", "member_number": "308-5930"},
            {"player_name": "Mangler", "member_number": "308-9999"},
        ]))

    @patch("services.golfbox._parse_my_times")
    def test_my_times_verification_requires_exact_owned_booking(self, parse_my_times):
        parse_my_times.return_value = [{
            "booking_start": "20260720T165000",
            "resource_guid": "{haga-course}",
            "can_cancel": True,
            "player_rows": [{"name": "Kristian Schiander", "member_number": "308-5930"}],
        }]
        response = SimpleNamespace(text="my times", raise_for_status=lambda: None)
        client = SimpleNamespace(get=lambda _url: response)

        booking = _verified_booking_in_my_times(
            client,
            date(2026, 7, 20),
            time(16, 50),
            [{"player_name": "Kristian Schiander", "member_number": "308-5930"}],
            "{HAGA-COURSE}",
        )

        self.assertIsNotNone(booking)

        parse_my_times.return_value[0]["can_cancel"] = False
        self.assertIsNone(_verified_booking_in_my_times(
            client,
            date(2026, 7, 20),
            time(16, 50),
            [{"player_name": "Kristian Schiander", "member_number": "308-5930"}],
            "{HAGA-COURSE}",
        ))

    @patch("services.golfbox.LOGGER")
    def test_booking_response_diagnostics_do_not_log_page_contents(self, logger):
        response = SimpleNamespace(
            text=(
                '<title>GolfBox Player</title>'
                '<input type="hidden" name="command" value="">'
                '<button name="cmdSubmit">Lagre</button>'
                '<div>Personlig medlemsnummer 123-456</div>'
            ),
            status_code=200,
            url=SimpleNamespace(path="/site/my_golfbox/ressources/booking/window.asp"),
        )

        result = _log_booking_submit_response(response, "20260720T165000")

        self.assertEqual(result["http_status"], 200)
        self.assertTrue(result["booking_form_present"])
        self.assertTrue(result["save_button_present"])
        logged_payload = logger.warning.call_args.args[1]
        self.assertNotIn("123-456", logged_payload)
        self.assertNotIn("Personlig", logged_payload)


if __name__ == "__main__":
    unittest.main()
