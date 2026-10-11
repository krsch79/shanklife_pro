import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import httpx

from services.trackman_api import TrackManClient, TrackManError, has_next, items_of, unalias
from services.trackman_rounds import project_scorecard


def scorecard(**overrides):
    data = {"id": "own-card", "kind": "CoursePlay", "bayKind": "SIMULATOR_BAY", "course": {"displayName": "Test course"}, "startedAt": "2026-01-01T10:00:00Z", "numberOfHolesToPlay": 9, "grossScore": 36, "isCompleted": True, "isTeamScorecard": False, "holes": [{"holeNumber": n, "par": 4, "grossScore": 4, "isPlayed": True, "putts": 2, "greenInRegulation": True, "gimmeWasGiven": False} for n in range(1, 10)], "gameSettings": {"gameScore": "StrokeGross", "puttingSettings": {"isAuto": False, "puttingMode": "MANUAL_AIMED"}}, "stat": {"fairwayHitFairway": 4, "fairwayHitLeft": 2, "fairwayHitRight": 2}}
    data.update(overrides)
    return data


class TrackManProjectionTests(unittest.TestCase):
    def test_completed_requires_actual_holes_and_matching_total(self):
        self.assertTrue(project_scorecard(scorecard())["completed"])
        self.assertFalse(project_scorecard(scorecard(grossScore=35))["completed"])
        self.assertFalse(project_scorecard(scorecard(numberOfHolesToPlay=18))["completed"])

    def test_unplayed_zero_and_missing_scores_are_not_scored_holes(self):
        data = scorecard()
        data["holes"][0].update(isPlayed=False, grossScore=0)
        data["holes"][1]["grossScore"] = None
        result = project_scorecard(data)
        self.assertEqual(len(result["summary"]["holes"]), 7)
        self.assertEqual(result["summary"]["total"], 28)
        self.assertFalse(result["completed"])

    def test_missing_and_zero_putts_are_distinct(self):
        data = scorecard()
        data["holes"][0]["putts"] = None
        data["holes"][1]["putts"] = 0
        projected = project_scorecard(data)["summary"]["holes"]
        self.assertIsNone(projected[0]["putts"])
        self.assertEqual(projected[1]["putts"], 0)

    def test_unknown_environment_is_never_assumed_outdoor(self):
        self.assertEqual(project_scorecard(scorecard(bayKind="FUTURE_BAY"))["environment"], "unknown")

    def test_games_are_not_rounds_and_team_rounds_are_preserved(self):
        self.assertIsNone(project_scorecard(scorecard(kind="ClosestToPin")))
        self.assertTrue(project_scorecard(scorecard(isTeamScorecard=True))["summary"]["team"])

    def test_auto_putting_not_physical_manual_aimed_is(self):
        self.assertFalse(project_scorecard(scorecard())["summary"]["automatic_putting"])
        automatic = scorecard(gameSettings={"puttingSettings": {"isAuto": True, "puttingMode": "AUTO"}})
        self.assertTrue(project_scorecard(automatic)["summary"]["automatic_putting"])
        self.assertTrue(project_scorecard(scorecard(gameSettings={}))["summary"]["automatic_putting"])


class TrackManTransportTests(unittest.TestCase):
    def test_graphql_partial_data_requires_explicit_mode_and_manifest(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": {"node": {"measurement": None}}, "errors": [{"message": "private body", "path": ["node", "measurement"]}]}))
        client = TrackManClient(transport=transport)
        with self.assertRaises(TrackManError):
            client.query("{node{id}}")
        self.assertEqual(client.query("{node{id}}", allow_partial=True)["node"]["measurement"], None)
        self.assertIn("upstream error: node.measurement", client.gaps)
        client.close()

    def test_validation_errors_are_not_retried_as_empty_data(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(400, json={"errors": [{"message": "invalid query"}]})
        client = TrackManClient(transport=httpx.MockTransport(handler))
        with self.assertRaises(TrackManError):
            client.query("{invalid}", allow_partial=True)
        self.assertEqual(len(calls), 1)
        client.close()

    def test_rate_limit_retry_and_no_secret_in_exception(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(429, json={}) if len(calls) < 2 else httpx.Response(200, json={"data": {"ok": True}})
        client = TrackManClient("secret-access", transport=httpx.MockTransport(handler))
        with patch("services.trackman_api.time.sleep"):
            self.assertTrue(client.query("{ok}")["ok"])
        self.assertEqual(len(calls), 2)
        client.close()

    def test_query_size_rejected_before_network(self):
        client = TrackManClient(transport=httpx.MockTransport(lambda request: self.fail("HTTP must not run")))
        with self.assertRaises(TrackManError):
            client.query("x" * 250001)
        client.close()

    def test_alias_restore_and_page_helpers(self):
        self.assertEqual(unalias({"__typename": "Bay", "Bay__isLocked": False}), {"__typename": "Bay", "isLocked": False})
        self.assertTrue(has_next({"pageInfo": {"hasNextPage": True}}, 4))
        self.assertFalse(has_next({"pageInfo": {"hasNextPage": False}}, 50))
        self.assertEqual(items_of({"items": None}), [])


class TrackManIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "sqlite:///" + self.tmp.name + "/test.db"
        from app import create_app
        from extensions import db
        from models import Player, User
        from services.trackman_models import TrackManAccount
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.db = db
        with self.app.app_context():
            for name in ("owner", "other"):
                player = Player(name="TM " + name, default_hcp=0)
                db.session.add(player); db.session.flush()
                user = User(username="tm-" + name, password_hash="unused", player_id=player.id)
                db.session.add(user); db.session.flush()
                setattr(self, name, user.id)
            db.session.execute(db.text("CREATE TABLE IF NOT EXISTS app_registry(id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL)"))
            db.session.execute(db.text("CREATE TABLE IF NOT EXISTS user_app_access(user_id INTEGER, app_id INTEGER, has_access BOOLEAN, is_app_admin BOOLEAN, PRIMARY KEY(user_id, app_id))"))
            db.session.execute(db.text("INSERT OR IGNORE INTO app_registry VALUES(1,'shanklife-pro')"))
            for user_id in (self.owner, self.other):
                db.session.execute(db.text("INSERT INTO user_app_access VALUES(:id,1,1,0)"), {"id": user_id})
            db.session.add(TrackManAccount(user_id=self.owner))
            db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.owner
            session["trackman_csrf"] = "csrf-test"

    def tearDown(self):
        with self.app.app_context():
            self.db.session.remove(); self.db.engine.dispose()
        if self.old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.old_url
        self.tmp.cleanup()

    def seed_card(self, owner=None, **overrides):
        from services.trackman_sync import archive
        from services.trackman_rounds import save_scorecard
        owner = owner or self.owner
        data = scorecard(**overrides)
        with self.app.app_context():
            row = archive(owner, "scorecards", data["id"], data)
            save_scorecard(owner, data)
            self.db.session.commit()
            return row.id

    def test_upsert_rerun_no_duplicate_and_updated_score(self):
        from services.trackman_models import TrackManArchive, TrackManRound
        self.seed_card(); self.seed_card(grossScore=35)
        with self.app.app_context():
            self.assertEqual(TrackManRound.query.filter_by(user_id=self.owner).count(), 1)
            self.assertEqual(TrackManArchive.query.filter_by(user_id=self.owner).count(), 1)
            self.assertFalse(TrackManRound.query.filter_by(user_id=self.owner).one().completed)

    def test_details_and_export_are_owner_private(self):
        own = self.seed_card()
        other = self.seed_card(owner=self.other, id="other-card")
        self.assertEqual(self.client.get("/me/trackman/archive/" + str(own)).status_code, 200)
        self.assertEqual(self.client.get("/me/trackman/archive/" + str(other)).status_code, 404)
        export = self.client.get("/me/trackman/export")
        data = json.loads(export.data)
        self.assertEqual(len(data["records"]), 1)
        self.assertEqual(data["records"][0]["remote_id"], "own-card")
        self.assertNotIn(b"credentials", export.data)
        self.assertEqual(export.headers["Cache-Control"], "private, no-store")

    def test_csrf_rejects_connection_and_disconnect(self):
        for endpoint in ("connect", "disconnect", "poll", "sync"):
            self.assertEqual(self.client.post("/me/trackman/" + endpoint).status_code, 400)

    def test_views_and_native_statistics_source_filters(self):
        self.seed_card()
        for path in ("/me/trackman/", "/me/rounds", "/stats/", "/stats/ai"):
            response = self.client.get(path + "?environment=simulator")
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(b"Kun simulator", response.data)
        sim = self.client.get("/api/v1/shanklife/stats?environment=simulator").json["stats"]
        outdoor = self.client.get("/api/v1/shanklife/stats?environment=outdoor").json["stats"]
        self.assertEqual(sim["scored_holes"], 9)
        self.assertEqual(sim["completed_round_count"], 1)
        self.assertEqual(sim["avg_putts"], 2)
        self.assertEqual(outdoor["scored_holes"], 0)

    def test_putting_auto_and_gimme_holes_excluded_without_erasing_raw(self):
        card = scorecard()
        card["holes"][0].update(putts=99, gimmeWasGiven=True)
        self.seed_card(holes=card["holes"])
        data = self.client.get("/api/v1/shanklife/stats?environment=simulator").json["stats"]
        self.assertEqual(data["avg_putts"], 2)
        self.seed_card(gameSettings={"puttingSettings": {"isAuto": True, "puttingMode": "AUTO"}})
        data = self.client.get("/api/v1/shanklife/stats?environment=simulator").json["stats"]
        self.assertIsNone(data["avg_putts"])
        self.assertIn(b'"putts":2', self.client.get("/me/trackman/export").data)

    def test_unknown_and_team_not_blended_into_individual_statistics(self):
        self.seed_card(bayKind="UNKNOWN")
        self.assertEqual(self.client.get("/api/v1/shanklife/stats").json["stats"]["scored_holes"], 0)
        self.seed_card(isTeamScorecard=True)
        data = self.client.get("/api/v1/shanklife/stats").json["stats"]
        self.assertEqual(data["scored_holes"], 0)
        self.assertEqual(len(data["round_rows"]), 1)

    def test_combined_statistics_pool_real_sample_counts(self):
        from models import Course, CourseHole, Round, RoundPlayer, ScoreEntry, ScoreStat, User
        with self.app.app_context():
            user = self.db.session.get(User, self.owner)
            course = Course(name="Outdoor test", hole_count=9)
            self.db.session.add(course); self.db.session.flush()
            for n in range(1, 10):
                self.db.session.add(CourseHole(course_id=course.id, hole_number=n, par=4, stroke_index=n))
            r = Round(course_id=course.id, status="finished", stats_user_id=user.id, played_hole_count=9)
            self.db.session.add(r); self.db.session.flush()
            rp = RoundPlayer(round_id=r.id, player_id=user.player_id, player_name_snapshot=user.player.name, hcp_for_round=0, tracks_stats=True)
            self.db.session.add(rp); self.db.session.flush()
            for n in range(1, 10):
                e = ScoreEntry(round_id=r.id, round_player_id=rp.id, hole_number=n, strokes=5 if n == 1 else 4)
                self.db.session.add(e); self.db.session.flush()
                self.db.session.add(ScoreStat(score_entry_id=e.id, putts=None if n == 1 else 2, fairway_result="hit" if n <= 4 else "left"))
            self.db.session.commit()
        self.seed_card()
        data = self.client.get("/api/v1/shanklife/stats?environment=all").json["stats"]
        self.assertEqual(data["completed_round_count"], 2)
        self.assertEqual(data["scored_holes"], 18)
        self.assertEqual(data["avg_round_vs_par"], 0.5)
        self.assertEqual(data["gir_percent"], 100.0)
        self.assertEqual(data["fairway_hit_percent"], 47.1)

    def test_simulator_clubs_include_unknown_clubs_and_distances(self):
        card = scorecard()
        for hole in card["holes"]:
            hole["shots"] = [{"shotNumber": 1, "club": "Driver", "measurement": {"total": 220, "carry": 200}}]
        card["holes"][0]["shots"][0]["club"] = None
        self.seed_card(holes=card["holes"])
        data = self.client.get("/api/v1/shanklife/stats?environment=simulator").json["stats"]
        clubs = {c["name"]: c for c in data["club_rows"]}
        self.assertEqual(clubs["Driver"]["count"], 8)
        self.assertEqual(clubs["Driver"]["avg_drive_distance"], 220)
        self.assertEqual(clubs["Ukjent kølle (TrackMan)"]["count"], 1)
        self.assertIsNone(clubs["Driver"]["fairway_percent"])

    def test_expired_device_does_not_keep_polling(self):
        from services.secret_store import encrypt_secret
        from services.trackman_models import TrackManAccount
        with self.app.app_context():
            account = self.db.session.get(TrackManAccount, self.owner)
            account.device_credentials = encrypt_secret("private-device")
            account.device_expires_at = datetime.now() - timedelta(seconds=1)
            self.db.session.commit()
        with patch("routes.trackman.oauth_form") as oauth:
            response = self.client.post("/me/trackman/poll", headers={"X-CSRF-Token": "csrf-test"})
            self.assertEqual(response.json["state"], "expired")
            oauth.assert_not_called()

    def test_tokens_encrypted_refresh_preserves_refresh_token(self):
        from services.secret_store import decrypt_secret
        from services.trackman_models import TrackManAccount
        from services.trackman_sync import access_token, store_tokens
        with self.app.app_context():
            account = self.db.session.get(TrackManAccount, self.owner)
            store_tokens(account, {"access_token": "first-access", "refresh_token": "private-refresh", "expires_in": 0})
            self.assertNotIn("private-refresh", account.credentials)
            with patch("services.trackman_sync.oauth_form", return_value={"access_token": "next-access", "expires_in": 3600}):
                self.assertEqual(access_token(account), "next-access")
            self.assertEqual(json.loads(decrypt_secret(account.credentials))["refresh_token"], "private-refresh")


class TrackManPaginationTests(unittest.TestCase):
    def test_nested_collection_pagination_follows_all_pages(self):
        def field(name, kind="SCALAR", target="Int", args=None):
            return {"name": name, "type": {"kind": kind, "name": target}, "args": args or []}
        arg = lambda name: {"name": name, "type": {"kind": "SCALAR", "name": "Int"}, "defaultValue": None}
        requests = []
        def handler(request):
            query = json.loads(request.content)["query"]
            requests.append(query)
            self.assertIn("skip:1,take:50", query)
            return httpx.Response(200, json={"data": {"node": {"events": {"items": [{"id": "b"}], "totalCount": 2, "pageInfo": {"hasNextPage": False}}}}})
        client = TrackManClient(transport=httpx.MockTransport(handler))
        client.schema = {
            "Thing": {"kind": "OBJECT", "fields": [field("events", "OBJECT", "Segment", [arg("skip"), arg("take")])]},
            "Segment": {"kind": "OBJECT", "fields": [field("totalCount"), field("items", "LIST", None)]},
            "Node": {"possibleTypes": []},
        }
        client.schema["Segment"]["fields"][1]["type"] = {"kind": "LIST", "name": None, "ofType": {"kind": "OBJECT", "name": "Item"}}
        client.schema["Item"] = {"kind": "OBJECT", "fields": [field("id", target="ID")]}
        record = {"events": {"items": [{"id": "a"}], "totalCount": 2, "pageInfo": {"hasNextPage": True}}}
        client.expand_pages(record, 'node(id:"private-node")', "Thing")
        self.assertEqual([r["id"] for r in record["events"]["items"]], ["a", "b"])
        self.assertEqual(len(requests), 1)
        client.close()

    def test_nested_page_total_mismatch_and_repeat_fail_loudly(self):
        for repeated in (True, False):
            client = TrackManClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": {"node": {"events": {"items": [{"id": "a" if repeated else "b"}], "totalCount": 3, "pageInfo": {"hasNextPage": False}}}}})))
            client.schema = {"Thing": {"fields": [{"name": "events", "type": {"kind": "OBJECT", "name": "Segment"}, "args": [{"name": "skip"}, {"name": "take"}]}]}, "Node": {"possibleTypes": []}}
            client.selection = lambda *args, **kwargs: "items{id} totalCount pageInfo{hasNextPage}"
            record = {"events": {"items": [{"id": "a"}], "totalCount": 3, "pageInfo": {"hasNextPage": True}}}
            with self.assertRaises(TrackManError):
                client.expand_pages(record, 'node(id:"private-node")', "Thing")
            client.close()
