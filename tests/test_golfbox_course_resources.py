"""Multi-course selection and membership refresh; every upstream request is mocked."""
import unittest
from datetime import date, time
from unittest.mock import MagicMock, patch
from services import golfbox as gb

HAGA='{11111111-1111-1111-1111-111111111111}'
BALLERUD='{22222222-2222-2222-2222-222222222222}'
MAIN='{33333333-3333-3333-3333-333333333333}'
SHARE='{44444444-4444-4444-4444-444444444444}'
CLUBS=f'<select name="ddlClub"><option value="{HAGA}">Haga Golfklubb</option></select>'
RESOURCES=f'<select name="ddlRessoruce"><option value="{MAIN}">Haga Golfklubb - Haga Golf Hovedbane</option><option value="{SHARE}">Haga Golfklubb - Aksjonærsløyfen</option></select>'
SWITCH=f'''<table><tr><td><div class="flex-grow-1"><div>Haga Golfklubb</div></div><button onclick="_postBack('switchClub','{HAGA}')" title=" Velg "></button></td></tr><tr><td><div class="flex-grow-1">Ballerud Golfklubb</div><button onclick="_postBack('switchClub','{BALLERUD}')" title=" Valgt "></button></td></tr></table>'''

def response(text='',url='https://www.golfbox.no/site/security/switchClub.asp'):
    r=MagicMock();r.text=text;r.url=url;return r

def identity(club,number):
    return f'<p>QA Spiller | {club} | {number} | HCP: 5.4</p>'

class GolfBoxCourseResourceTests(unittest.TestCase):
    def resolve(self,name):
        client=MagicMock();client.get.return_value=response(CLUBS);client.post.return_value=response(RESOURCES)
        with patch('services.golfbox.httpx.Client') as factory,patch('services.golfbox._login'):
            factory.return_value.__enter__.return_value=client
            return gb._resolve_course({'username':'qa','password':'qa'},name)

    def test_explicit_shareholder_course_never_uses_first_resource(self):
        result=self.resolve('Haga Golfklubb - Aksjonærsløyfen')
        self.assertEqual(result['resource_guid'],SHARE)
        self.assertIn('Aksjonærsløyfen',result['course'])

    def test_removed_explicit_resource_is_not_replaced_by_main_course(self):
        self.assertIsNone(self.resolve('Haga Golfklubb - Removed course'))

    def test_existing_legacy_job_club_name_preserves_original_resolution(self):
        self.assertEqual(self.resolve('Haga')['resource_guid'],MAIN)

    def test_membership_refresh_reads_fresh_identity_and_restores_original_club(self):
        client=MagicMock();client.get.side_effect=[response(SWITCH),response(identity('Haga Golfklubb','308-2')),response(identity('Ballerud Golfklubb','65-1'))]
        client.post.return_value=response('command acknowledged')
        found=gb._fetch_memberships(client,identity('Ballerud Golfklubb','65-1'))
        self.assertEqual({m['member_number'] for m in found},{'308-2','65-1'})
        self.assertEqual(client.post.call_args.kwargs['data']['commandValue'],BALLERUD)
        self.assertEqual(client.post.call_count,3)

    def test_failed_membership_refresh_restores_original_club(self):
        client=MagicMock();client.get.side_effect=[response(SWITCH),response('No identity')];client.post.return_value=response('ack')
        with self.assertRaises(ValueError):gb._fetch_memberships(client,identity('Ballerud Golfklubb','65-1'))
        self.assertEqual(client.post.call_args.kwargs['data']['commandValue'],BALLERUD)

    def test_switch_club_reads_identity_when_acknowledgement_has_none(self):
        client=MagicMock();client.get.side_effect=[response(SWITCH),response(identity('Haga Golfklubb','308-2'))];client.post.return_value=response('ack')
        result=gb._switch_club(client,HAGA)
        self.assertEqual(result['member_number'],'308-2')

    def test_availability_switches_to_own_membership_before_reading_exact_resource(self):
        client=MagicMock();client.get.return_value=response('grid')
        with patch('services.golfbox.httpx.Client') as factory,patch('services.golfbox._login'),patch('services.golfbox._switch_club') as switch,patch('services.golfbox._parse_grid_slots',return_value=[]):
            factory.return_value.__enter__.return_value=client
            gb._fetch_slots({},HAGA,SHARE,'Haga Golfklubb - Aksjonærsløyfen',date(2026,10,20),time(10),time(12),1,member_club_guid=HAGA)
        switch.assert_called_once_with(client,HAGA)
        self.assertEqual(client.get.call_args.kwargs['params']['Ressource_GUID'],SHARE)
        self.assertTrue(client.get.call_args.args[0].endswith('/grid.asp'));client.post.assert_not_called()
