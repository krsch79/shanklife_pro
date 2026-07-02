import unittest

from services.golfbox import _fallback_prompt_interpretation, _normalize_interpretation


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


if __name__ == "__main__":
    unittest.main()
