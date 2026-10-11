"""Resumable private archive, token refresh, and full-history reconciliation."""
import fcntl
import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from flask import current_app

from extensions import db
from services.secret_store import decrypt_secret, encrypt_secret
from services.time import server_now
from services.trackman_api import ROOTS, TrackManClient, TrackManError, has_next, items_of, named_type, oauth_form
from services.trackman_models import TrackManAccount, TrackManArchive, TrackManSyncRun
from services.trackman_rounds import save_scorecard


@contextmanager
def account_lock(user_id):
    directory = Path(current_app.instance_path) / "trackman_locks"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(directory / (str(user_id) + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise TrackManError("En TrackMan-jobb kjører allerede. Vent til den er ferdig.") from None
        yield
    finally:
        os.close(fd)


def store_tokens(account, tokens):
    if not tokens.get("access_token"):
        raise TrackManError("TrackMan ga ingen tilgangsnøkkel.")
    old = json.loads(decrypt_secret(account.credentials)) if account.credentials else {}
    saved = {"access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token") or old.get("refresh_token"), "expires_at": time.time() + tokens.get("expires_in", 3600)}
    account.credentials = encrypt_secret(json.dumps(saved))
    account.device_credentials = None
    account.user_code = None
    account.verification_uri = None
    account.device_expires_at = None
    account.connected_at = account.connected_at or server_now()
    account.sync_state = "connected"
    account.sync_message = "Tilkoblet. Første synkronisering gjenstår."


def access_token(account):
    try:
        credentials = json.loads(decrypt_secret(account.credentials))
    except (ValueError, TypeError):
        raise TrackManError("TrackMan-tilkoblingen må fornyes.") from None
    if credentials["expires_at"] <= time.time() + 120:
        token = oauth_form("token", {"grant_type": "refresh_token", "refresh_token": credentials.get("refresh_token", "")})
        if token.get("error"):
            raise TrackManError("TrackMan-tilkoblingen er utløpt. Koble til igjen.")
        store_tokens(account, token)
        db.session.commit()
        return token["access_token"]
    return credentials["access_token"]


def archive(user_id, category, identity, data):
    identity = str(identity)
    row = TrackManArchive.query.filter_by(user_id=user_id, category=category, remote_id=identity).first()
    if row is None:
        row = TrackManArchive(user_id=user_id, category=category, remote_id=identity)
        db.session.add(row)
    row.payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    row.typename = data.get("__typename") if isinstance(data, dict) else None
    row.fetched_at = server_now()
    return row


def sync_account(user_id):
    with account_lock(user_id):
        account = db.session.get(TrackManAccount, user_id)
        if not account or not account.credentials:
            raise TrackManError("Koble til TrackMan først.")
        run = TrackManSyncRun(user_id=user_id)
        db.session.add(run)
        account.sync_state = "syncing"
        account.sync_message = "Henter hele historikken fra TrackMan …"
        db.session.commit()
        client = None
        manifest = {"sources": {}, "errors": [], "scope": "Own player golf data, including hidden activities; no other players' scorecards or global discovery", "archive_version": 1}
        try:
            client = TrackManClient(access_token(account))
            schema = client.load_schema()
            archive(user_id, "schema", "current", schema)
            profile = client.query("{me{profile{id}}}")["me"]["profile"]
            remote_id = profile["id"]
            if account.remote_player_id and account.remote_player_id != remote_id:
                raise TrackManError("Dette er en annen TrackMan-konto. Eksisterende arkiv er ikke blandet med den nye kontoen.")
            account.remote_player_id = remote_id
            db.session.commit()
            scorecards = {}
            canonical_scorecards = set()
            for source in ROOTS:
                count = 0
                offset = 0
                seen = set()
                total = None
                detail_failures = 0
                detail_count = 0
                source_oldest = None
                try:
                    while True:
                        value, paging = client.root(source, offset, detail=source not in {"activities", "scorecards"})
                        if value is None:
                            required = any(gap.startswith("Me." + source + ": required") for gap in client.gaps)
                            manifest["sources"][source] = {"state": "unavailable" if required else "fetched", "count": count}
                            break
                        if isinstance(value, dict) and "totalCount" in value:
                            if total is not None and total != value["totalCount"]:
                                raise TrackManError("TrackMan-historikken endret seg under synken. Prøv igjen.")
                            total = value["totalCount"]
                        records = items_of(value) if paging else [value]
                        for index, record in enumerate(records):
                            if not isinstance(record, dict):
                                record = {"value": record}
                            identity = record.get("id") or ("current" if not paging else record.get("kind") or record.get("dbId") or record.get("reportId") or hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest())
                            if identity in seen:
                                raise TrackManError("TrackMan gjentok en post i historikken. Ingen poster slettes.")
                            seen.add(identity)
                            timestamp = record.get("time") or record.get("startedAt")
                            if timestamp and (source_oldest is None or timestamp < source_oldest):
                                source_oldest = timestamp
                            if source in {"activities", "scorecards"}:
                                archive(user_id, source + "_index", identity, record)
                                actual = record.get("__typename") or "Scorecard"
                                try:
                                    detail = client.node(identity, actual)
                                except TrackManError as exc:
                                    detail_failures += 1
                                    manifest["errors"].append({"source": source, "message": str(exc), "remote_id": identity})
                                    count += 1
                                    continue
                                detail_count += 1
                                archive(user_id, source, identity, detail)
                                if isinstance(detail.get("strokes"), list) and detail.get("strokeCount") is not None and len(detail["strokes"]) != detail["strokeCount"]:
                                    client.gaps.add(actual + ": fetched stroke count differs from reported count")
                                if actual == "PerformanceCenterActivity":
                                    fetched = sum(len(t.get("strokes") or []) for t in (detail.get("report") or {}).get("targets") or [])
                                    if detail.get("strokeCount") != fetched:
                                        client.gaps.add(actual + ": report stroke count differs from reported count")
                                    client.gaps.add("QuickPlayStroke.measurementId: full launch measurements are not exposed by this schema")
                                if source == "scorecards":
                                    scorecards[identity] = detail
                                    canonical_scorecards.add(identity)
                                elif isinstance(detail.get("scorecard"), dict) and detail["scorecard"].get("id"):
                                    card = detail["scorecard"]
                                    scorecards[card["id"]] = card
                            else:
                                if not paging:
                                    client.expand_pages(record, ["me", source], record.get("__typename") or named_type(next(f for f in client.schema["Me"]["fields"] if f["name"] == source)["type"])["name"])
                                archive(user_id, source, identity, record)
                            count += 1
                        # Durable progress per page. A later error leaves originals intact.
                        account.sync_message = "Henter " + source + ": " + str(count) + " poster"
                        db.session.commit()
                        offset += len(records)
                        more = paging and has_next(value, len(records))
                        if more and not records:
                            raise TrackManError("TrackMan returnerte en tom side før siste side.")
                        if not more:
                            if total is not None and count != total:
                                raise TrackManError("TrackMan-antallet stemmer ikke med hentede poster.")
                            manifest["sources"][source] = {"state": "partial" if detail_failures else "fetched", "count": count, "detail_count": detail_count if source in {"activities", "scorecards"} else count, "detail_failures": detail_failures, "reported_count": total, "oldest": source_oldest}
                            break
                        if offset > 1000000:
                            raise TrackManError("TrackMan-pagineringen overskred sikkerhetsgrensen.")
                except TrackManError as exc:
                    db.session.rollback()
                    manifest["sources"][source] = {"state": "failed", "count": count}
                    manifest["errors"].append({"source": source, "message": str(exc)})
                run.manifest = json.dumps(manifest, ensure_ascii=False)
                db.session.commit()
            for identity, card in scorecards.items():
                if identity not in canonical_scorecards:
                    try:
                        card = client.node(identity, "Scorecard")
                    except TrackManError as exc:
                        manifest["errors"].append({"source": "referenced_scorecards", "remote_id": identity, "message": str(exc)})
                        continue
                archive(user_id, "scorecards", identity, card)
                save_scorecard(user_id, card)
            manifest["referenced_scorecards"] = len(set(scorecards) - canonical_scorecards)
            # Cross-check server kind totals with enumerated activities when possible.
            summaries = TrackManArchive.query.filter_by(user_id=user_id, category="activitySummary").all()
            reported = {}
            for entry in summaries:
                item = json.loads(entry.payload)
                if item.get("kind") and item.get("activityCount") is not None:
                    reported[item["kind"]] = item["activityCount"]
            activity_rows = TrackManArchive.query.filter_by(user_id=user_id, category="activities").all()
            enumerated = {}
            for entry in activity_rows:
                kind = json.loads(entry.payload).get("kind", "UNKNOWN")
                enumerated[kind] = enumerated.get(kind, 0) + 1
            manifest["activity_kinds"] = enumerated
            manifest["reported_activity_kinds"] = reported
            if reported and any(enumerated.get(kind, 0) != count for kind, count in reported.items()):
                manifest["errors"].append({"source": "activitySummary", "message": "Antall per aktivitetstype avviker fra arkivet. Se datadekning."})
            manifest["field_gaps"] = sorted(client.gaps)
            manifest["privacy_boundaries"] = sorted(client.boundaries)
            manifest["asset_policy"] = "Original media/report URLs and metadata retained; binary videos/PDFs are not mirrored."
            manifest["raw_counts"] = {category: TrackManArchive.query.filter_by(user_id=user_id, category=category).count() for category in ROOTS}
            manifest["schema_sha256"] = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()
            run.state = "partial" if manifest["errors"] or client.gaps else "fetched"
            run.finished_at = server_now()
            run.manifest = json.dumps(manifest, ensure_ascii=False)
            account.last_sync_at = server_now()
            account.sync_state = run.state
            account.sync_message = "Historikken er hentet. Se datadekning for begrensninger." if run.state == "partial" else "Historikken er hentet og antall kontrollert."
            db.session.commit()
            return manifest
        except Exception as exc:
            db.session.rollback()
            run.state = "failed"
            run.finished_at = server_now()
            manifest["errors"].append({"source": "sync", "message": str(exc) if isinstance(exc, TrackManError) else "En intern synkfeil oppstod. Arkivet er beholdt."})
            run.manifest = json.dumps(manifest, ensure_ascii=False)
            account.sync_state = "failed"
            account.sync_message = manifest["errors"][-1]["message"]
            db.session.commit()
            if isinstance(exc, TrackManError):
                raise
            raise TrackManError(account.sync_message) from None
        finally:
            if client:
                client.close()


def start_sync(app, user_id):
    def worker():
        with app.app_context():
            try:
                sync_account(user_id)
            except TrackManError:
                pass  # Stored safely on the account/run; no private upstream body logged.
            finally:
                db.session.remove()
    thread = threading.Thread(target=worker, name="trackman-sync-" + str(user_id), daemon=True)
    thread.start()
