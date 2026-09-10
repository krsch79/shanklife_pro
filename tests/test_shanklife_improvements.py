import re
import unittest
from datetime import timedelta
from unittest.mock import patch

import test_finished_round_edit as fixtures


class ShanklifeImprovementsTests(unittest.TestCase):
    setUp = fixtures.FinishedRoundEditTests.setUp
    tearDown = fixtures.FinishedRoundEditTests.tearDown
    _seed_round = fixtures.FinishedRoundEditTests._seed_round
    _client = fixtures.FinishedRoundEditTests._client

    def _invite(self, email="new@example.com", name="Ny golfer", delivered=True):
        with patch("services.shanklife_invitations.send_mail", return_value=delivered) as mail:
            response = self._client(self.admin_id).post("/admin/shanklife-invitations", data={"name": name, "email": email})
        self.assertEqual(response.status_code, 302)
        if mail.called:
            return re.search(r"/shanklife-invitation/[\w-]+", mail.call_args.args[1]).group()

    def test_invitation_acceptance_grants_only_shanklife_access_and_is_one_use(self):
        from models import ShanklifeInvitation, User, SeriesPlayer
        with self.app.app_context():
            self.db.session.execute(self.db.text("INSERT INTO app_registry (id,slug) VALUES (2,'shanklife-app')"))
            self.db.session.commit()
        link = self._invite()
        client = self.app.test_client()
        self.assertEqual(client.get(link).status_code, 200)
        response = client.post(link, data={"password": "local-test-password", "confirm_password": "local-test-password"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.get('/rounds/finished').status_code, 200)
        self.assertEqual(client.get(link).status_code, 302)
        with self.app.app_context():
            user = User.query.filter_by(email='new@example.com').one()
            self.assertFalse(user.is_admin)
            grants = self.db.session.execute(self.db.text("SELECT has_access,is_app_admin FROM user_app_access WHERE user_id=:id"), {'id': user.id}).all()
            self.assertEqual(grants, [(1, 0), (1, 0)])
            self.assertEqual(SeriesPlayer.query.filter_by(player_id=user.player_id).count(), 0)
            invitation = ShanklifeInvitation.query.one()
            self.assertIsNotNone(invitation.accepted_at)
            self.assertEqual(invitation.accepted_user_id, user.id)
            self.assertNotEqual(invitation.token_hash, link.rsplit('/', 1)[1])

    def test_resend_replaces_token_and_failed_delivery_preserves_previous_link(self):
        first = self._invite()
        second = self._invite()
        client = self.app.test_client()
        self.assertEqual(client.get(first).status_code, 302)
        self.assertEqual(client.get(second).status_code, 200)
        failed = self._invite(delivered=False)
        self.assertEqual(client.get(failed).status_code, 302)
        self.assertEqual(client.get(second).status_code, 200)

    def test_expiry_invalid_password_duplicate_and_nonadmin(self):
        from models import ShanklifeInvitation
        from services.time import server_now
        link = self._invite()
        client = self.app.test_client()
        response = client.post(link, data={'password': 'short', 'confirm_password': 'short'})
        self.assertIn('minst 8 tegn', response.get_data(as_text=True))
        with self.app.app_context():
            invitation = ShanklifeInvitation.query.one()
            self.assertIsNone(invitation.accepted_at)
            invitation.created_at = server_now() - timedelta(days=8)
            self.db.session.commit()
        self.assertEqual(client.get(link).status_code, 302)
        with patch('services.shanklife_invitations.send_mail') as mail:
            self._client(self.regular_user_id).post('/admin/shanklife-invitations', data={'name': 'Forbidden', 'email': 'test@example.com'})
            self._client(self.admin_id).post('/admin/shanklife-invitations', data={'name': 'Invalid', 'email': 'bad\n@example.com'})
            self._client(self.admin_id).post('/admin/shanklife-invitations', data={'name': 'Redigeringsspiller', 'email': 'unique@example.com'})
            mail.assert_not_called()

    def test_combined_round_filters_legacy_length_and_empty_results(self):
        with self.app.app_context():
            original = self.db.session.get(self.Round, self.round_id)
            original.played_hole_count = None
            course_id = original.course_id
            player_id = original.round_players[0].player_id
            self.db.session.add(self.Round(course_id=course_id, status='finished', played_hole_count=9, started_at=original.started_at))
            self.db.session.commit()
        client = self._client(self.admin_id)
        response = client.get(f'/rounds/finished?course={course_id}&holes=18&year=2026&player={player_id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Viser 1 av 2 runder.', response.get_data(as_text=True))
        self.assertIn('Viser 1 av 2 runder.', client.get('/rounds/finished?holes=9').get_data(as_text=True))
        self.assertIn('Viser 0 av 2 runder.', client.get('/rounds/finished?year=2025').get_data(as_text=True))
        self.assertIn('Viser 0 av 2 runder.', client.get('/rounds/finished?holes=invalid').get_data(as_text=True))
        self.assertIn('Viser 2 av 2 runder.', client.get('/rounds/finished').get_data(as_text=True))

    def test_all_outcomes_saved_and_included_in_summary(self):
        from routes.rounds import _save_score_stat
        from services.round_summary import build_round_summary
        from services.shanklife_ai_stats import _fairway_summary
        from models import ScoreStat
        expected = {'bunker': 'Fairwaybunker', 'long': 'Forbi fairway', 'short': 'Kort av fairway', 'green': 'Greentreff'}
        with self.app.app_context():
            round_obj = self.db.session.get(self.Round, self.round_id)
            rp = round_obj.round_players[0]
            rp.tracks_stats = True
            holes = sorted(round_obj.course.holes, key=lambda x: x.hole_number)
            entries = sorted(rp.score_entries, key=lambda x: x.hole_number)
            for hole, entry, result in zip(holes, entries, ['hit', *expected]):
                _save_score_stat(entry, hole, '200', result, '2')
            self.db.session.commit()
            self.assertEqual(ScoreStat.query.count(), 5)
            with self.assertRaises(ValueError):
                _save_score_stat(entries[0], holes[0], '200', 'invalid', '2')
            summary = build_round_summary(round_obj)
            self.assertEqual(summary["statistics"][0]["fairway_attempts"], 5)
            self.assertEqual(summary["statistics"][0]["fairway_hit_percent"], 20)
            # Assert the rendered detail and independent AI denominator too.
        html = self._client(self.admin_id).get(f'/rounds/{self.round_id}/score').get_data(as_text=True)
        for label in expected.values():
            self.assertIn(label, html)
        ai = _fairway_summary([{'par': 4, 'fairway_result': key} for key in ['hit', *expected]])
        self.assertEqual(ai['attempts'], 5)
        self.assertEqual(ai['hit_percent'], 20)
        self.assertEqual(ai['outcomes']['green'], 1)
