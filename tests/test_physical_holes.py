import unittest
from types import SimpleNamespace

from services.physical_holes import (
    assign_physical_identities_from_loop_signatures,
    infer_physical_hole_identity,
)


def _course(name, loop_names=None):
    holes = []
    for hole_number in range(1, 19):
        loop_hole = ((hole_number - 1) % 9) + 1
        loop_index = 0 if hole_number <= 9 else 1
        loop_name = loop_names[loop_index] if loop_names else None
        holes.append(
            SimpleNamespace(
                hole_number=hole_number,
                par=3 + (loop_hole % 3),
                physical_course_group="Haga" if loop_name else None,
                physical_loop=loop_name,
                physical_hole_number=loop_hole if loop_name else None,
            )
        )
    lengths = [
        SimpleNamespace(
            hole_number=hole_number,
            length_meters=100 + (((hole_number - 1) % 9) + 1) * 10,
        )
        for hole_number in range(1, 19)
    ]
    return SimpleNamespace(
        name=name,
        hole_count=18,
        holes=holes,
        tees=[SimpleNamespace(display_order=1, lengths=lengths)],
    )


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

    def test_loop_signature_reuses_known_physical_identity(self):
        known = _course("Haga Blå+Blå", ("BLÅ", "BLÅ"))
        unknown = _course("Haga ny kombinasjon")

        changed = assign_physical_identities_from_loop_signatures([known, unknown])

        self.assertTrue(changed)
        self.assertEqual(unknown.holes[0].physical_course_group, "Haga")
        self.assertEqual(unknown.holes[0].physical_loop, "BLÅ")
        self.assertEqual(unknown.holes[0].physical_hole_number, 1)
        self.assertEqual(unknown.holes[11].physical_loop, "BLÅ")
        self.assertEqual(unknown.holes[11].physical_hole_number, 3)

    def test_identical_unknown_loops_get_stable_auto_identity(self):
        course = _course("Ukjent kombinasjon")

        changed = assign_physical_identities_from_loop_signatures([course])

        self.assertTrue(changed)
        self.assertEqual(course.holes[0].physical_course_group, "Auto")
        self.assertTrue(course.holes[0].physical_loop.startswith("Sløyfe "))
        self.assertEqual(course.holes[0].physical_loop, course.holes[9].physical_loop)
        self.assertEqual(course.holes[0].physical_hole_number, 1)
        self.assertEqual(course.holes[9].physical_hole_number, 1)


if __name__ == "__main__":
    unittest.main()
