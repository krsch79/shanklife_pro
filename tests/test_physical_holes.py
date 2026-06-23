import unittest

from services.physical_holes import infer_physical_hole_identity


class PhysicalHoleTests(unittest.TestCase):
    def test_haga_combo_courses_share_same_physical_loop_hole(self):
        blue_yellow = infer_physical_hole_identity("Haga Blå+Gul", 12, 18)
        yellow_red = infer_physical_hole_identity("Haga Gul+Rød", 3, 18)

        self.assertEqual(blue_yellow["physical_course_group"], "Haga")
        self.assertEqual(blue_yellow["physical_loop"], "GUL")
        self.assertEqual(blue_yellow["physical_hole_number"], 3)
        self.assertEqual(blue_yellow, yellow_red)

    def test_plain_course_has_no_inferred_identity(self):
        self.assertIsNone(infer_physical_hole_identity("Asker golfklubb", 4, 18))


if __name__ == "__main__":
    unittest.main()
