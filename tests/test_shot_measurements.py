import json
import unittest

from services.shot_measurements import haversine_distance_m, parse_shot_measurements


class ShotMeasurementTests(unittest.TestCase):
    def test_haversine_distance_is_in_meters(self):
        distance = haversine_distance_m(59.944, 10.714, 59.944, 10.716)

        self.assertGreater(distance, 100)
        self.assertLess(distance, 120)

    def test_parse_payload_uses_client_distance_when_valid(self):
        payload = [{
            "start": {"lat": 59.944, "lng": 10.714, "accuracy_m": 6},
            "end": {"lat": 59.944, "lng": 10.716, "accuracy_m": 8},
            "distance_m": 111.4,
        }]

        rows = parse_shot_measurements(json.dumps(payload))

        self.assertEqual(rows[0]["shot_number"], 1)
        self.assertEqual(rows[0]["distance_m"], 111.4)
        self.assertEqual(rows[0]["start_accuracy_m"], 6.0)

    def test_parse_payload_computes_distance_from_coordinates(self):
        payload = [{
            "start": {"lat": 59.944, "lng": 10.714},
            "end": {"lat": 59.944, "lng": 10.716},
        }]

        rows = parse_shot_measurements(json.dumps(payload))

        self.assertGreater(rows[0]["distance_m"], 100)
        self.assertLess(rows[0]["distance_m"], 120)

    def test_invalid_coordinate_is_rejected(self):
        payload = [{
            "start": {"lat": 99, "lng": 10.714},
            "end": {"lat": 59.944, "lng": 10.716},
        }]

        with self.assertRaisesRegex(ValueError, "start-breddegrad"):
            parse_shot_measurements(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
