import unittest

from services.golfbox import _parse_identity


class GolfBoxIdentityTests(unittest.TestCase):
    def test_parse_identity_includes_hcp(self):
        identity = _parse_identity(
            "<div>Kristian Schiander | Ballerud Golfklubb | 65-110 | HCP 3,5</div>"
        )

        self.assertEqual(identity["player_name"], "Kristian Schiander")
        self.assertEqual(identity["club_name"], "Ballerud Golfklubb")
        self.assertEqual(identity["member_number"], "65-110")
        self.assertEqual(identity["hcp"], 3.5)


if __name__ == "__main__":
    unittest.main()
