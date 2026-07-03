import os
import tempfile
import unittest
from types import SimpleNamespace


class GpsDriveMappingTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.tmpdir.name}/test.db"

        from app import create_app
        from extensions import db
        from models import Course, CourseHole, Player, Round, RoundPlayer, ScoreEntry, ScoreStat

        self.app = create_app()
        self.db = db
        self.Course = Course
        self.CourseHole = CourseHole
        self.Player = Player
        self.Round = Round
        self.RoundPlayer = RoundPlayer
        self.ScoreEntry = ScoreEntry
        self.ScoreStat = ScoreStat

    def tearDown(self):
        self.tmpdir.cleanup()
        if self.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.previous_database_url

    def test_first_gps_shot_reuses_pending_score_stat_row(self):
        from routes.rounds import _map_first_shot_to_drive_distance, _save_score_stat

        with self.app.app_context():
            course = self.Course(name="GPS Testbane", hole_count=1)
            player = self.Player(name="GPS Testspiller", default_hcp=10)
            self.db.session.add_all([course, player])
            self.db.session.flush()
            self.db.session.add(self.CourseHole(course_id=course.id, hole_number=1, par=4, stroke_index=1))
            self.db.session.flush()
            round_obj = self.Round(course_id=course.id, status="ongoing")
            self.db.session.add(round_obj)
            self.db.session.flush()
            round_player = self.RoundPlayer(
                round_id=round_obj.id,
                player_id=player.id,
                player_name_snapshot=player.name,
                hcp_for_round=10,
                tracks_stats=True,
            )
            self.db.session.add(round_player)
            self.db.session.flush()
            entry = self.ScoreEntry(
                round_id=round_obj.id,
                round_player_id=round_player.id,
                hole_number=1,
                strokes=5,
            )
            self.db.session.add(entry)
            self.db.session.flush()

            _save_score_stat(entry, SimpleNamespace(par=4), "", "hit", "2", "1.0")
            _map_first_shot_to_drive_distance(entry, [{"distance_m": 213.0}])
            self.db.session.commit()

            stats = self.ScoreStat.query.filter_by(score_entry_id=entry.id).all()
            self.assertEqual(len(stats), 1)
            self.assertEqual(stats[0].drive_distance_m, 213)
            self.assertEqual(stats[0].fairway_result, "hit")


if __name__ == "__main__":
    unittest.main()
