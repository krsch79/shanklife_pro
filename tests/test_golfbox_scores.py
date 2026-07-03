import unittest

from services.golfbox_scores import _best_course, _normalize_api_option


class GolfBoxScoreSubmissionTests(unittest.TestCase):
    def test_best_course_matches_local_golfbane_to_golfbox_gk_name(self):
        courses = [
            {"course_name": "Åpen Ballrenne morgen", "course_guid": "ballrenne"},
            {"course_name": "Drøbak GK 18 hull", "course_guid": "drobak-18"},
            {"course_name": "Drøbak GK 9 hull front 2020", "course_guid": "drobak-9"},
        ]

        course = _best_course(courses, "Drøbak golfbane", 18)

        self.assertIsNotNone(course)
        self.assertEqual(course["course_guid"], "drobak-18")

    def test_normalize_api_option_parses_false_hcp_qualifying_text(self):
        option = _normalize_api_option({
            "Course_GUID": "course-id",
            "Course_Name": "Testbane",
            "Course_isHcpQualifying": "False",
        })

        self.assertFalse(option["is_hcp_qualifying"])


if __name__ == "__main__":
    unittest.main()
