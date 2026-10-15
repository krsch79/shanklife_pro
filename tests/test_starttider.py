"""Functional workspace tests. All external reads, submits and email are mocked."""
import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from tests import test_sportsmode
from services.time import server_now


class StarttiderTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_sportsmode.SportsModeTests()
        self.fixture.setUp()
        self.app, self.db, self.client = self.fixture.app, self.fixture.db, self.fixture.client
        self.uid = self.fixture.user_id
        from models import User, GolfBoxFavorite
        with self.app.app_context():
            u = self.db.session.get(User, self.uid)
            u.golfbox_username = 'qa'; u.golfbox_password_token = 'qa-not-a-real-secret'
            u.golfbox_member_number = '65-1'; u.golfbox_home_club_name = 'Ballerud'
            u.golfbox_memberships_json = json.dumps([{'member_number':'65-1','club_name':'Ballerud','player_name':'Profilspiller','is_current_user':True}])
            f = GolfBoxFavorite(user_id=u.id,name='Erik Test',member_number='65-2',club_name='Ballerud')
            self.db.session.add(f); self.db.session.commit(); self.favorite_id = f.id
        self.assertEqual(self.client.get('/starttider').status_code,200)
        with self.client.session_transaction() as s: self.csrf = s['starttider_csrf']
        self.tomorrow = (server_now().date()+timedelta(days=1)).isoformat()

    def tearDown(self):
        self.fixture.tearDown()

    def state(self):
        return self.client.get('/starttider/data?kind=state').json

    def post(self, operation, **data):
        return self.client.post('/starttider/action',json={'action':operation,'revision':self.state()['revision'],**data},headers={'X-CSRF-Token':self.csrf})

    def draft(self, **data):
        return {**self.state()['draft'],'date':self.tomorrow,**data}

    def availability(self, **extra):
        return {'status':'ok','available_slots':[{'date':self.tomorrow,'time':'16:20','course':'Ballerud',
            'club_guid':'club','resource_guid':'resource','available_spots':4}], 'booking_enabled':True, **extra}

    def search(self, **draft):
        with patch('services.starttider.gb.find_golfbox_availability_for_courses',return_value=self.availability()):
            response = self.post('search',draft=self.draft(**draft))
            self.assertEqual(response.status_code,200,response.json)
        return response

    def review(self):
        self.search(time_from='16:00',time_to='18:00')
        response=self.post('review_slot',index=0,draft=self.state()['draft'])
        self.assertEqual(response.status_code,200,response.json)
        return response.json['review']['id']

    def test_shell_and_legacy_get_do_not_call_upstream(self):
        with patch('services.golfbox.upcoming_golfbox_bookings') as bookings, patch('services.golfbox.sync_golfbox_favorites') as sync:
            self.assertEqual(self.client.get('/starttider').status_code,200)
            self.assertEqual(self.client.get('/balletour/ai').location,'/starttider')
            bookings.assert_not_called();sync.assert_not_called()

    def test_legacy_post_cannot_replay_old_confirmation(self):
        with patch('services.golfbox.confirm_golfbox_booking') as send:
            r=self.client.post('/balletour/ai',data={'action':'confirm_booking'})
            self.assertEqual(r.status_code,303);send.assert_not_called()

    def test_access_revocation_and_tour_only_access(self):
        with self.app.app_context():
            self.db.session.execute(self.db.text('UPDATE user_app_access SET has_access=0 WHERE user_id=:id AND app_id=1'),{'id':self.uid});self.db.session.commit()
        self.assertEqual(self.client.get('/starttider').status_code,200)
        with self.app.app_context():
            self.db.session.execute(self.db.text('UPDATE user_app_access SET has_access=0 WHERE user_id=:id AND app_id=2'),{'id':self.uid});self.db.session.commit()
        self.assertEqual(self.client.get('/starttider').status_code,403)
        self.assertEqual(self.client.get('/starttider/data?kind=favorites').status_code,403)

    def test_csrf_and_stale_revision_reject_actions(self):
        self.assertEqual(self.client.post('/starttider/action',json={'action':'reset'}).status_code,403)
        old=self.state()['revision'];self.post('draft',draft=self.draft())
        r=self.client.post('/starttider/action',json={'action':'reset','revision':old},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(r.status_code,409)

    def test_draft_survives_get_without_cookie_results(self):
        self.search(time_from='16:00',time_to='18:00',players=2,player_refs=['self','f:65-2'])
        self.client.get('/starttider')
        s=self.state();self.assertEqual(s['draft']['players'],2);self.assertEqual(len(s['result']['available_slots']),1)
        with self.client.session_transaction() as cookie:
            self.assertNotIn('golfbox_ai_chat',cookie);self.assertNotIn('golfbox_pending_booking',cookie)
        self.assertLess(sum(len(h) for h in self.client.get('/starttider').headers.getlist('Set-Cookie')),3000)

    def test_only_count_can_search_but_cannot_book_unnamed_players(self):
        self.search(players=2,player_refs=[])
        r=self.post('review_slot',index=0)
        self.assertEqual(r.status_code,400);self.assertIn('alle spillerne',r.json['message'])

    def test_favorite_is_owner_scoped(self):
        from models import GolfBoxFavorite, User, Player
        with self.app.app_context():
            p=Player(name='Annen spiller',default_hcp=0);self.db.session.add(p);self.db.session.flush()
            u=User(username='other',password_hash='x',player_id=p.id);self.db.session.add(u);self.db.session.flush()
            f=GolfBoxFavorite(user_id=u.id,name='Hemmelig',member_number='65-99',club_name='Ballerud');self.db.session.add(f);self.db.session.commit();other=f.id
        self.assertNotIn('Hemmelig',self.client.get('/starttider/data?kind=favorites').text)
        self.search(players=2)
        self.assertEqual(self.post('review_slot',index=0,draft=self.draft(players=2,player_refs=['self','f:65-99'])).status_code,400)

    def test_ai_time_followup_preserves_course_date_and_people(self):
        self.post('draft',draft=self.draft(courses=['Haga'],players=2,player_refs=['self','f:65-2'],time_from='16:00',time_to='20:00'))
        with patch.dict('os.environ',{'OPENAI_API_KEY':''}):
            r=self.post('interpret',prompt='heller etter 17')
        self.assertEqual(r.status_code,200,r.json)
        d=r.json['draft'];self.assertEqual(d['courses'],['Haga']);self.assertEqual(d['date'],self.tomorrow)
        self.assertEqual(d['players'],2);self.assertEqual(d['time_from'],'17:00');self.assertEqual(d['time_to'],'20:00')

    def test_ai_unavailable_keeps_local_followup_working(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':'qa'}),patch('services.starttider.OpenAI',side_effect=RuntimeError('unavailable')):
            r=self.post('interpret',prompt='heller etter 17',draft=self.draft(time_to='20:00'))
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['draft']['time_from'],'17:00')

    def test_ai_names_only_set_count_before_player_choice(self):
        from models import GolfBoxFavorite
        with self.app.app_context():
            self.db.session.add(GolfBoxFavorite(user_id=self.uid,name='Erik Test',member_number='99-2',club_name='Haga'));self.db.session.commit()
        with patch.dict('os.environ',{'OPENAI_API_KEY':''}):
            r=self.post('interpret',prompt='meg og Erik Test',draft=self.draft())
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['draft']['unresolved_names'],[]);self.assertEqual(r.json['draft']['player_refs'],['self']);self.assertEqual(r.json['draft']['players'],2)

    def test_selected_slot_is_server_owned_and_capacity_checked(self):
        self.search()
        self.assertEqual(self.post('review_slot',index=99,slot={'time':'06:00'}).status_code,400)
        with self.app.app_context():
            from models import GolfBoxWorkspace
            w=self.db.session.get(GolfBoxWorkspace,self.uid);s=json.loads(w.state_json);s['result']['available_slots'][0]['available_spots']=0;w.state_json=json.dumps(s);self.db.session.commit()
        self.assertEqual(self.post('review_slot',index=0).status_code,400)

    def test_changed_search_requires_new_results(self):
        self.search()
        self.assertEqual(self.post('review_slot',index=0,draft=self.draft(courses=['Haga'])).status_code,400)

    def test_single_confirmation_has_one_external_submit_even_when_repeated(self):
        action=self.review()
        with patch('services.starttider.gb.find_golfbox_availability_for_courses',return_value=self.availability()),patch('services.starttider.gb.confirm_golfbox_booking',return_value={'status':'booking_created','message':'Bekreftet'}) as send:
            first=self.post('confirm',id=action);second=self.post('confirm',id=action)
        self.assertEqual(first.status_code,200);self.assertEqual(second.status_code,200);send.assert_called_once()

    def test_external_timeout_is_not_replayed(self):
        action=self.review()
        with patch('services.starttider.gb.find_golfbox_availability_for_courses',return_value=self.availability()),patch('services.starttider.gb.confirm_golfbox_booking',side_effect=TimeoutError()) as send:
            first=self.post('confirm',id=action);second=self.post('confirm',id=action)
        self.assertEqual(first.json['outcome']['status'],'booking_unverified');self.assertEqual(second.json['outcome']['status'],'booking_unverified');send.assert_called_once()

    def test_lost_slot_does_not_submit(self):
        action=self.review()
        with patch('services.starttider.gb.find_golfbox_availability_for_courses',return_value=self.availability(available_slots=[])),patch('services.starttider.gb.confirm_golfbox_booking') as send:
            r=self.post('confirm',id=action)
        self.assertEqual(r.json['outcome']['status'],'booking_failed');send.assert_not_called()

    def test_payment_required_keeps_its_actual_outcome(self):
        action=self.review()
        with patch('services.starttider.gb.find_golfbox_availability_for_courses',return_value=self.availability()),patch('services.starttider.gb.confirm_golfbox_booking',return_value={'status':'payment_required','message':'GolfBox ber om betaling.'}):
            r=self.post('confirm',id=action)
        self.assertEqual(r.json['outcome']['status'],'payment_required')

    def test_review_expires_and_is_owner_bound(self):
        from models import GolfBoxAction
        action=self.review()
        with self.app.app_context():
            row=self.db.session.get(GolfBoxAction,action);row.expires_at=server_now()-timedelta(seconds=1);self.db.session.commit()
        self.assertEqual(self.post('confirm',id=action).status_code,400)
        self.assertEqual(self.post('confirm',id='someone-elses-action').status_code,400)

    def test_every_job_requires_review_then_single_activation(self):
        from models import GolfBoxWatchBooking, GolfBoxRecurringBooking, GolfBoxScheduledBooking
        tomorrow=server_now()+timedelta(days=1)
        for kind,target in [('watch','_watch_booking_result'),('scheduled','_scheduled_booking_result'),('recurring','_recurring_booking_result')]:
            with self.subTest(kind=kind),patch('services.starttider.gb.'+target,return_value={'status':kind+'_booking_created','message':'Opprettet'}) as send:
                r=self.post('review_job',draft=self.draft(),job={'kind':kind,'execute_at':tomorrow.replace(hour=1,minute=0).isoformat(),'weekday':0,'weeks_ahead':1,'execute_time':'07:00'})
                self.assertEqual(r.status_code,200,r.json);send.assert_not_called()
                action=r.json['review']['id'];self.post('confirm',id=action);self.post('confirm',id=action);send.assert_called_once()
        with self.app.app_context():
            self.assertEqual(sum(c.query.count() for c in [GolfBoxWatchBooking,GolfBoxRecurringBooking,GolfBoxScheduledBooking]),0)

    def test_job_review_rejects_multiple_courses(self):
        self.assertEqual(self.post('review_job',draft=self.draft(courses=['Haga','Ballerud']),job={'kind':'watch'}).status_code,400)

    def test_multiple_course_slot_can_be_reviewed(self):
        with patch('services.starttider.gb.find_golfbox_availability_for_courses',return_value=self.availability(booking_enabled=False)):
            r=self.post('search',draft=self.draft(courses=['Haga','Ballerud']))
        self.assertTrue(r.json['result']['booking_enabled'])
        self.assertEqual(self.post('review_slot',index=0).status_code,200)

    def test_bookings_cached_and_error_never_claims_empty(self):
        with patch('services.starttider.gb.upcoming_golfbox_bookings',return_value={'status':'ok','bookings':[{'course':'Ballerud','time':'16:20'}]}) as fetch:
            self.client.get('/starttider/data?kind=bookings');self.client.get('/starttider/data?kind=bookings');fetch.assert_called_once()
        with patch('services.starttider.gb.upcoming_golfbox_bookings',return_value={'status':'error','message':'Logg inn på nytt','bookings':[]}):
            r=self.client.get('/starttider/data?kind=bookings&refresh=1')
        self.assertTrue(r.json['stale']);self.assertEqual(len(r.json['bookings']),1);self.assertEqual(r.json['status'],'error')

    def test_missing_personal_credentials_never_uses_global_credentials(self):
        from models import User
        with self.app.app_context():
            u=self.db.session.get(User,self.uid);u.golfbox_password_token=None;self.db.session.commit()
        with patch('services.starttider.gb.find_golfbox_availability_for_courses') as fetch:
            r=self.post('search',draft=self.draft())
        self.assertEqual(r.json['result']['status'],'configuration_required');fetch.assert_not_called()

    def test_manual_member_number_looked_up_before_review(self):
        self.search(players=2)
        with patch('services.starttider.gb._lookup_golfbox_members_by_number',return_value={'99-123':{'player_name':'Manuell','member_number':'99-123','club_name':'Haga'}}) as lookup:
            r=self.post('review_slot',index=0,draft=self.draft(players=2,player_refs=['self','m:99-123']))
        self.assertEqual(r.status_code,200,r.json);lookup.assert_called_once();self.assertEqual(r.json['review']['players'],['Profilspiller','Manuell'])

    def test_history_is_paginated_and_private(self):
        with patch('services.starttider.gb.golfbox_booking_history',return_value=[]) as history:
            r=self.client.get('/starttider/data?kind=history&page=2')
        self.assertEqual(r.status_code,200);history.assert_called_once();self.assertEqual(history.call_args.kwargs['limit'],21)
        self.assertEqual(r.headers['Cache-Control'],'no-store')

    def test_favorite_sync_cannot_reassign_selection_to_another_person(self):
        from services import golfbox as gb
        self.search(players=2,player_refs=['self','f:65-2'])
        with self.app.app_context():
            from models import User
            user=self.db.session.get(User,self.uid)
            gb._replace_golfbox_favorites(user,[{'name':'Ny spiller','member_number':'99-3','club_name':'Haga'},{'name':'Erik Test','member_number':'65-2','club_name':'Ballerud'}])
            self.db.session.commit()
        r=self.post('review_slot',index=0,draft=self.draft(players=2,player_refs=['self','f:65-2']))
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['review']['players'][-1],'Erik Test')

    def test_cancel_review_is_own_place_and_repeat_is_single_use(self):
        from models import GolfBoxWorkspace
        with self.app.app_context():
            w=self.db.session.get(GolfBoxWorkspace,self.uid)
            w.cache_json=json.dumps({'fetched_at':server_now().isoformat(),'bookings':[{'booking_guid':'mine','booking_start':'start','resource_guid':'r','can_cancel':True,'players':['Profilspiller','Erik'],'course':'Ballerud','date':self.tomorrow,'time':'16:20'}]})
            self.db.session.commit()
        review=self.post('review_cancel',index=0)
        self.assertEqual(review.status_code,200,review.json);self.assertEqual(review.json['review']['players'],['Profilspiller'])
        with patch('services.starttider.gb.cancel_golfbox_booking',return_value={'status':'booking_cancelled','message':'Avbestilt'}) as cancel,patch('services.starttider.gb.upcoming_golfbox_bookings',return_value={'status':'ok','bookings':[]}):
            action=review.json['review']['id'];self.post('confirm',id=action);self.post('confirm',id=action)
        cancel.assert_called_once()

    def test_cancellation_not_verified_is_uncertain_and_not_replayed(self):
        from services import starttider as st
        with self.app.app_context():
            from models import User
            review=st.new_review(self.db.session.get(User,self.uid),'cancel',{'booking_guid':'mine','booking_start':'s','resource_guid':'r'},{'players':['Profilspiller']})
        with patch('services.starttider.gb.cancel_golfbox_booking',return_value={'status':'booking_cancelled'}),patch('services.starttider.gb.upcoming_golfbox_bookings',return_value={'status':'error','bookings':[]}):
            r=self.post('confirm',id=review['id'])
        self.assertEqual(r.json['outcome']['status'],'booking_unverified')

    def test_watch_finds_time_requires_separate_booking_confirmation(self):
        r=self.post('review_job',draft=self.draft(),job={'kind':'watch'})
        payload={'course':'Ballerud','date':self.tomorrow,'time':'16:20','players':1,'player_memberships':[{'player_name':'Profilspiller','member_number':'65-1'}],'club_guid':'club','resource_guid':'resource'}
        with patch('services.starttider.gb._watch_booking_result',return_value={'status':'confirmation_required','pending_booking':payload}),patch('services.starttider.gb.confirm_golfbox_booking') as send:
            r=self.post('confirm',id=r.json['review']['id'])
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['review']['kind'],'booking');send.assert_not_called()

    def test_ai_explicit_member_number_only_sets_count(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':''}):
            r=self.post('interpret',prompt='meg og 99-123',draft=self.draft())
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['draft']['player_refs'],['self']);self.assertEqual(r.json['draft']['players'],2)

    def test_recurring_review_shows_first_actual_play_date(self):
        from services import golfbox as gb
        from models import GolfBoxAction
        from types import SimpleNamespace
        r=self.post('review_job',draft=self.draft(),job={'kind':'recurring','weekday':0,'weeks_ahead':2,'execute_time':'07:00'})
        self.assertEqual(r.status_code,200,r.json)
        with self.app.app_context():
            action=self.db.session.get(GolfBoxAction,r.json['review']['id']);i=json.loads(action.payload_json)['interpretation']
            expected=gb._next_play_date_for_recurring(SimpleNamespace(next_run_at=__import__('datetime').datetime.fromisoformat(i['execute_at']),play_weekday=i['recurrence']['play_weekday'],play_weeks_ahead=2))
        self.assertEqual(r.json['review']['date'],expected.isoformat())

    def lookup(self, query):
        return self.client.post('/starttider/players',json={'query':query},headers={'X-CSRF-Token':self.csrf})

    def test_search_discards_participant_identity_and_keeps_count(self):
        r=self.search(players=3,player_refs=['m:99-123'])
        self.assertEqual(r.json['draft']['player_refs'],['self'])
        self.assertEqual(r.json['draft']['players'],3)

    def test_self_is_first_even_if_client_omits_or_reorders_self(self):
        from models import GolfBoxAction
        self.search(players=2)
        for refs in [['f:65-2'],['f:65-2','self']]:
            r=self.post('review_slot',index=0,draft=self.draft(players=2,player_refs=refs))
            self.assertEqual(r.status_code,200,r.json)
            with self.app.app_context():
                payload=json.loads(self.db.session.get(GolfBoxAction,r.json['review']['id']).payload_json)
            self.assertEqual([m['member_number'] for m in payload['player_memberships']],['65-1','65-2'])

    def test_duplicate_self_or_extra_player_is_not_booked(self):
        self.search(players=2)
        with patch('services.starttider.gb._lookup_golfbox_members_by_number',return_value={'65-1':{'player_name':'Profilspiller','member_number':'65-1','club_name':'Ballerud'}}):
            r=self.post('review_slot',index=0,draft=self.draft(players=2,player_refs=['self','m:65-1']))
        self.assertEqual(r.status_code,400);self.assertIn('allerede spiller 1',r.json['message'])
        self.assertEqual(self.post('review_slot',index=0,draft=self.draft(players=2,player_refs=['self','f:65-2','m:99-123'])).status_code,400)

    def test_old_review_without_self_cannot_be_confirmed(self):
        from models import GolfBoxAction
        action=self.review()
        with self.app.app_context():
            a=self.db.session.get(GolfBoxAction,action);p=json.loads(a.payload_json)
            p['player_memberships']=[{'player_name':'Someone else','member_number':'99-123'}]
            a.payload_json=json.dumps(p);self.db.session.commit()
        with patch('services.starttider.gb.confirm_golfbox_booking') as send:
            r=self.post('confirm',id=action)
        self.assertEqual(r.status_code,400);send.assert_not_called()

    def test_directory_name_lookup_preserves_ambiguous_club_choices(self):
        from services.golfbox_scores import _parse_marker_search_results
        # GolfBox's real response contract: membership in label, GUID/name/club in value.
        markup="""<select id="slc_MarkerSearch4result"><option value="{'g':'a','n':'Anne Test','c':'Haga'}">99-123, Anne Test, Haga</option><option value="{'g':'b','n':'Anne Test','c':'Oslo'}">10-456, Anne Test, Oslo</option><option value="{'g':'c','n':'Unusable','c':'Unknown'}">No membership</option></select>"""
        before=self.state()['revision']
        with patch('services.golfbox_scores.search_marker',return_value=_parse_marker_search_results(markup)) as search:
            r=self.lookup('Anne Test')
        self.assertEqual(r.status_code,200,r.json);search.assert_called_once()
        self.assertEqual([p['member_number'] for p in r.json['players']],['99-123','10-456'])
        self.assertEqual(self.state()['revision'],before)
        self.assertEqual(r.headers['Cache-Control'],'no-store')
        self.assertNotIn('Anne Test',self.client.get('/starttider/data?kind=favorites').text)

    def test_directory_number_lookup_deduplicates_favorite_and_excludes_self(self):
        with patch('services.starttider.gb._lookup_golfbox_members_by_number',return_value={'65-2':{'player_name':'Erik Test','member_number':'65-2','club_name':'Ballerud'}}) as lookup:
            r=self.lookup('65-2')
        lookup.assert_called_once();self.assertEqual(r.json['players'][0]['ref'],'f:65-2')
        with patch('services.starttider.gb._lookup_golfbox_members_by_number',return_value={'65-1':{'player_name':'Profilspiller','member_number':'65-1','club_name':'Ballerud'}}):
            self.assertEqual(self.lookup('65-1').json['players'],[])

    def test_directory_empty_error_csrf_and_access(self):
        self.assertEqual(self.client.post('/starttider/players',json={'query':'Erik'}).status_code,403)
        self.assertEqual(self.lookup('x').status_code,400)
        with patch('services.golfbox_scores.search_marker',return_value=[]):
            self.assertEqual(self.lookup('Absent').json['players'],[])
        with patch('services.golfbox_scores.search_marker',side_effect=TimeoutError()):
            self.assertEqual(self.lookup('Erik').status_code,502)
        with self.app.app_context():
            self.db.session.execute(self.db.text('UPDATE user_app_access SET has_access=0 WHERE user_id=:id AND app_id=2'),{'id':self.uid});self.db.session.commit()
        self.assertEqual(self.lookup('Erik').status_code,403)
