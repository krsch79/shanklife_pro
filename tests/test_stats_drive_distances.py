import unittest

from routes.stats import _avg_normal_drive_distance, _normal_drive_distances


class StatsDriveDistanceTests(unittest.TestCase):
    def test_normal_drive_distances_drop_extremes_when_sample_is_large(self):
        distances = [20, 60, 80, 190, 200, 205, 210, 215, 220, 225, 230, 370]

        self.assertEqual(_normal_drive_distances(distances), [190, 200, 205, 210, 215, 220, 225])
        self.assertEqual(_avg_normal_drive_distance(distances), 209)

    def test_normal_drive_distances_keep_small_samples_after_sanity_filter(self):
        distances = [None, 24, 155, 165, 180, 361]

        self.assertEqual(_normal_drive_distances(distances), [155, 165, 180])
        self.assertEqual(_avg_normal_drive_distance(distances), 167)


if __name__ == "__main__":
    unittest.main()
