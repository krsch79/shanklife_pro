import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.golfbox import (
    _fallback_prompt_interpretation,
    _normalize_interpretation,
    continue_golfbox_slot_booking,
    start_golfbox_slot_booking,
)


class GolfBoxPromptInterpretationTests(unittest.TestCase):
    def test_open_availability_question_defaults_to_one_player(self):
        interpretation = _fallback_prompt_interpretation("Er det noe ledig på Ballerud i dag?")

        self.assertEqual(interpretation["intent"], "find_availability")
        self.assertEqual(interpretation["players"], 1)

    def test_explicit_player_count_is_preserved_for_availability(self):
        interpretation = _fallback_prompt_interpretation("Er det noe ledig for 2 personer på Ballerud i dag?")

        self.assertEqual(interpretation["intent"], "find_availability")
        self.assertEqual(interpretation["players"], 2)

    def test_openai_default_two_is_overridden_for_open_availability_question(self):
        interpretation = _normalize_interpretation(
            {
                "intent": "find_availability",
                "courses": ["Ballerud"],
                "players": 2,
                "date": "today",
                "time_from": "06:00",
                "time_to": "22:00",
            },
            "Er det noe ledig på Ballerud i dag?",
        )

        self.assertEqual(interpretation["players"], 1)

    def test_slot_booking_button_asks_for_players_without_player_details(self):
        result = start_golfbox_slot_booking(_slot_payload(), user=None)

        self.assertEqual(result["status"], "slot_booking_players_required")
        self.assertIn("Hvem skal bookes inn", result["message"])
        self.assertEqual(result["pending_slot_booking"]["time"], "17:00")

    @patch("services.golfbox._interpret_prompt_with_openai")
    def test_slot_booking_can_continue_with_only_current_user(self, interpret_prompt):
        interpret_prompt.return_value = {
            "intent": "create_booking",
            "courses": ["Ballerud"],
            "players": 1,
            "player_names": [],
            "member_numbers": [],
            "member_number_names": {},
            "include_current_user": True,
            "date": "2026-07-02",
            "time_from": "17:00",
            "time_to": "17:30",
            "_interpretation_source": "local_rules",
        }
        user = SimpleNamespace(
            username="Kristian",
            player=SimpleNamespace(name="Kristian Schiander"),
            golfbox_player_name="Kristian Schiander",
            golfbox_home_club_name="Ballerud Golfklubb",
            golfbox_member_number="65-110",
            golfbox_username="",
            golfbox_password_token="",
        )

        result = continue_golfbox_slot_booking(_slot_payload(), "bare meg", user=user)

        self.assertEqual(result["status"], "confirmation_required")
        self.assertEqual(result["pending_booking"]["players"], 1)
        self.assertEqual(result["pending_booking"]["player_memberships"][0]["player_name"], "Kristian Schiander")


def _slot_payload():
    return {
        "course": "Ballerud",
        "date": "2026-07-02",
        "time": "17:00",
        "available_spots": 4,
        "club_guid": "{club}",
        "resource_guid": "{resource}",
        "interpretation": {
            "intent": "find_availability",
            "courses": ["Ballerud"],
            "players": 1,
            "date": "2026-07-02",
            "time_from": "06:00",
            "time_to": "22:00",
        },
    }


if __name__ == "__main__":
    unittest.main()
