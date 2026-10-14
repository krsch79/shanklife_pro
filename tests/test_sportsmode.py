import json
import unittest
from datetime import datetime

from tests import test_profile_pages


class SportsModeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_profile_pages.ProfilePagesTests()
        self.fixture.setUp()
        self.app = self.fixture.app
        self.app.config['TESTING'] = True
        self.db = self.fixture.db
        self.user_id = self.fixture.user_id
        from models import Course, CourseHole, CourseTee, Round, RoundPlayer, ScoreEntry, Series, SeriesPlayer, User
        with self.app.app_context():
            user = self.db.session.get(User, self.user_id)
            course = Course(name='Ballerud test', hole_count=9)
            self.db.session.add(course); self.db.session.flush()
            tee = CourseTee(course_id=course.id, name='Gul', display_order=1)
            series = Series(name='Balletour', course_id=course.id, min_qualifying_rounds=20)
            self.db.session.add_all([tee, series]); self.db.session.flush()
            for h in range(1, 10): self.db.session.add(CourseHole(course_id=course.id, hole_number=h, par=3, stroke_index=h))
            self.db.session.add(SeriesPlayer(series_id=series.id, player_id=user.player_id))
            self.db.session.execute(self.db.text("INSERT OR IGNORE INTO app_registry(id,slug) VALUES(2,'balletour')"))
            self.db.session.execute(self.db.text("INSERT INTO user_app_access(user_id,app_id,has_access,is_app_admin) VALUES(:id,2,1,0)"), {'id': self.user_id})
            ids = []
            for kind in ('legacy', 'tour', 'private'):
                r = Round(course_id=course.id, status='finished', started_at=datetime(2026,10,10), played_hole_count=9,
                          series_id=series.id if kind == 'tour' else None, tour_context_set=kind != 'legacy')
                self.db.session.add(r); self.db.session.flush()
                rp = RoundPlayer(round_id=r.id, player_id=user.player_id, selected_tee_id=tee.id,
                                 player_name_snapshot=user.player.name, hcp_for_round=5.4)
                self.db.session.add(rp); self.db.session.flush()
                for h in range(1,10):self.db.session.add(ScoreEntry(round_id=r.id,round_player_id=rp.id,hole_number=h,strokes=3))
                ids.append(r.id)
            self.db.session.commit()
            self.tour_id, self.course_id = series.id, course.id
            self.legacy_id, self.tour_round_id, self.private_id = ids
        self.client = self.app.test_client()
        with self.client.session_transaction() as s: s['user_id'] = self.user_id

    def tearDown(self):
        self.fixture.tearDown()

    def test_shared_history_contains_own_private_and_tour_rounds(self):
        r = self.client.get('/api/v1/sports/rounds')
        self.assertEqual(r.status_code,200)
        rows = {r['round_id']:r for r in r.json['rounds']}
        self.assertEqual(len(rows),7)
        self.assertEqual(rows[self.private_id]['source'],'shanklife')
        self.assertEqual(rows[self.tour_round_id]['source'],'balletour')
        self.assertEqual(rows[self.legacy_id]['source'],'balletour')

    def test_private_round_does_not_enter_tour_ranking_or_api(self):
        r=self.client.get('/api/v1/balletour/rounds?status=finished&tee=gul')
        self.assertEqual(r.status_code,200)
        ids={row['id'] for row in r.json['rounds']}
        self.assertIn(self.legacy_id,ids);self.assertIn(self.tour_round_id,ids);self.assertNotIn(self.private_id,ids)
        self.assertEqual(self.client.get(f'/api/v1/balletour/rounds/{self.private_id}').status_code,404)
        self.assertEqual(self.client.get(f'/balletour/rounds/{self.private_id}').status_code,404)

    def test_migration_preserves_legacy_and_never_reclassifies_marked_private(self):
        from services.tour_context import migrate_legacy_tour_context
        from models import Round
        with self.app.app_context():
            before = [(r.id,r.course_id,r.status) for r in Round.query.order_by(Round.id)]
            migrate_legacy_tour_context();migrate_legacy_tour_context()
            self.db.session.expire_all()
            self.assertEqual(self.db.session.get(Round,self.legacy_id).series_id,self.tour_id)
            self.assertIsNone(self.db.session.get(Round,self.private_id).series_id)
            self.assertTrue(self.db.session.get(Round,self.private_id).tour_context_set)
            self.assertEqual(before,[(r.id,r.course_id,r.status) for r in Round.query.order_by(Round.id)])

    def test_revoked_tour_permission_hides_tour_history_but_retains_private(self):
        with self.app.app_context():
            self.db.session.execute(self.db.text('UPDATE user_app_access SET has_access=0 WHERE user_id=:id AND app_id=2'),{'id':self.user_id});self.db.session.commit()
        rows=self.client.get('/api/v1/sports/rounds').json['rounds']
        self.assertIn(self.private_id,{r['round_id'] for r in rows})
        self.assertFalse(any(r['is_tour'] for r in rows))
        self.assertEqual(self.client.get('/balletour/').status_code,403)
        self.assertEqual(self.client.get('/api/v1/balletour/overview').status_code,403)
        self.assertFalse(self.client.get('/api/v1/auth/me').json['user']['products']['balletour'])

    def test_tour_only_member_can_use_shared_home_without_private_rounds(self):
        with self.app.app_context():
            self.db.session.execute(self.db.text('UPDATE user_app_access SET has_access=0 WHERE user_id=:id AND app_id=1'),{'id':self.user_id});self.db.session.commit()
        self.assertEqual(self.client.get('/').status_code,200)
        rows=self.client.get('/api/v1/sports/rounds').json['rounds']
        self.assertTrue(rows);self.assertTrue(all(r['is_tour'] for r in rows))
        self.assertEqual(self.client.get('/rounds/new').status_code,403)
        self.assertEqual(self.client.get(f'/rounds/{self.tour_round_id}/score').status_code,200)
        self.assertEqual(self.client.get(f'/rounds/{self.private_id}/score').status_code,403)
        me = self.client.get('/api/v1/auth/me')
        self.assertEqual(me.status_code,200)
        self.assertFalse(me.json['user']['products']['shanklife'])
        self.assertTrue(me.json['user']['products']['balletour'])
        self.assertEqual(self.client.get('/api/v1/balletour/overview').status_code,200)

    def test_old_schema_upgrade_preserves_rounds_and_score_entries(self):
        from app import ensure_schema_updates
        from sqlalchemy import inspect
        from models import Round, ScoreEntry
        from services.tour_context import migrate_legacy_tour_context
        with self.app.app_context():
            score_before = [(e.id,e.strokes,e.hole_result) for e in ScoreEntry.query.order_by(ScoreEntry.id)]
            count_before = Round.query.count()
            self.db.session.remove()
            columns = [c['name'] for c in inspect(self.db.engine).get_columns('rounds') if c['name'] not in ('series_id','tour_context_set')]
            with self.db.engine.begin() as conn:
                conn.execute(self.db.text('CREATE TABLE rounds_legacy AS SELECT '+','.join(columns)+' FROM rounds'))
                conn.execute(self.db.text('DROP TABLE rounds'))
                conn.execute(self.db.text('ALTER TABLE rounds_legacy RENAME TO rounds'))
            ensure_schema_updates(self.app)
            migrate_legacy_tour_context()
            ensure_schema_updates(self.app)
            self.assertEqual(Round.query.count(),count_before)
            self.assertEqual(score_before,[(e.id,e.strokes,e.hole_result) for e in ScoreEntry.query.order_by(ScoreEntry.id)])
            self.assertEqual(self.db.session.get(Round,self.legacy_id).series_id,self.tour_id)
            self.assertIsNone(self.db.session.get(Round,self.fixture.round_ids[0]).series_id)

    def test_tour_admin_clear_preserves_private_round_on_same_course(self):
        from services.admin_tools import clear_balletour_rounds
        from models import Round, ScoreEntry
        from unittest.mock import patch
        with self.app.app_context(), patch('services.admin_tools._delete_round_image_files'):
            before = ScoreEntry.query.filter_by(round_id=self.private_id).count()
            self.assertEqual(clear_balletour_rounds(reset_connection=False),2)
            self.assertIsNotNone(self.db.session.get(Round,self.private_id))
            self.assertEqual(ScoreEntry.query.filter_by(round_id=self.private_id).count(),before)

    def test_other_legacy_series_keep_their_course_based_history(self):
        from models import Round, Series
        from services.tour_context import migrate_legacy_tour_context, series_round_condition
        with self.app.app_context():
            r = self.db.session.get(Round,self.fixture.round_ids[0])
            series = Series(name='Klubbserie',course_id=r.course_id,min_qualifying_rounds=2)
            self.db.session.add(series);self.db.session.commit()
            before = {r.id for r in Round.query.filter_by(course_id=series.course_id)}
            migrate_legacy_tour_context()
            self.assertEqual(before,{r.id for r in Round.query.filter(series_round_condition(series))})

    def test_finishing_shows_result_before_optional_golfbox_submission(self):
        from models import Round, RoundPlayer, Club, ScoreStat
        from unittest.mock import patch
        for round_id,expected in ((self.private_id,f'/rounds/{self.private_id}/score'),(self.tour_round_id,f'/balletour/rounds/{self.tour_round_id}')):
            with self.app.app_context():
                r=self.db.session.get(Round,round_id);r.status='ongoing'
                rp=RoundPlayer.query.filter_by(round_id=round_id).first();rp.tracks_stats=False;rp_id=rp.id
                form={'action':'finish',f'score_{rp_id}':'3'}
                if round_id == self.tour_round_id:
                    club=Club(name='J7 test',sort_order=7);self.db.session.add(club);self.db.session.flush()
                    for entry in rp.score_entries:
                        entry.tee_club_id=club.id
                        self.db.session.add(ScoreStat(score_entry_id=entry.id,drive_distance_m=125,fairway_result='hit:pin',putts=2,last_putt_distance_m=1))
                    form.update({f'tee_club_{rp_id}':str(club.id),f'stat_drive_{rp_id}':'125',f'stat_green_status_{rp_id}':'hit',f'stat_green_horizontal_{rp_id}':'pin',f'stat_green_vertical_{rp_id}':'',f'stat_putts_{rp_id}':'2',f'stat_last_putt_distance_{rp_id}':'1'})
                self.db.session.commit()
            with patch('routes.rounds._try_automatic_garmin_sync'), patch('routes.rounds._send_shanklife_round_finished_mail'), patch('routes.rounds._send_balletour_round_finished_mail'):
                response=self.client.post(f'/rounds/{round_id}/hole/9',data=form)
            self.assertEqual(response.status_code,302)
            self.assertEqual(response.headers['Location'],expected)

    def test_personal_read_model_never_includes_other_players_private_trackman(self):
        from models import User
        from services.trackman_models import TrackManRound
        # A real projection fixture keeps TrackMan missing/automatic/gimme semantics intact.
        with self.app.app_context():
            other = User.query.filter(User.id != self.user_id).first()
            summary={'total':12,'par':12,'holes':[{'number':1,'par':3,'strokes':3,'putts':2,'gir':True,'gimme':False,'tee_shot':None}],
                     'stat':{},'automatic_putting':False,'team':False}
            self.db.session.add(TrackManRound(user_id=other.id,remote_id='private-other',environment='simulator',course_name='Private course',completed=False,holes_to_play=9,summary=json.dumps(summary)))
            self.db.session.commit()
            other_id = TrackManRound.query.filter_by(remote_id='private-other').first().id
        response=self.client.get('/api/v1/sports/rounds?environment=simulator')
        self.assertEqual(response.status_code,200);self.assertEqual(response.json['rounds'],[])
        self.assertEqual(self.client.get(f'/me/trackman/round/{other_id}').status_code,404)

    def test_trackman_scorecard_uses_owned_projection_and_conceded_putts_once(self):
        from services.trackman_models import TrackManRound
        summary={'total':3,'par':3,'holes':[{'number':1,'par':3,'strokes':3,'putts':2,'gir':True,'gimme':True,'tee_shot':None}],
                 'stat':{},'automatic_putting':False,'team':False}
        with self.app.app_context():
            row=TrackManRound(user_id=self.user_id,remote_id='owned-gimme',environment='simulator',course_name='Owned course',completed=False,holes_to_play=9,summary=json.dumps(summary))
            self.db.session.add(row);self.db.session.commit();row_id=row.id
        response=self.client.get(f'/me/trackman/round/{row_id}')
        self.assertEqual(response.status_code,200)
        self.assertIn('2.0',response.text)
        self.assertIn('DELVIS SPILT',response.text)
        row=self.client.get('/api/v1/sports/rounds?environment=simulator').json['rounds'][0]
        self.assertEqual(row['score'],'3');self.assertEqual(row['to_par'],'E')

    def test_matchplay_summary_uses_result_instead_of_incomplete_strokes(self):
        from models import Round, RoundPlayer
        with self.app.app_context():
            r=self.db.session.get(Round,self.fixture.round_ids[0]);r.play_format='matchplay'
            rp=RoundPlayer.query.filter_by(round_id=r.id).first()
            for e in rp.score_entries:e.hole_result='halved'
            rp.score_entries[0].hole_result='lost'
            self.db.session.commit()
        row=next(r for r in self.client.get('/api/v1/sports/rounds').json['rounds'] if r['round_id']==self.fixture.round_ids[0])
        self.assertEqual(row['score'],'1 ned');self.assertEqual(row['to_par'],'')
