#!/usr/bin/env python3
"""Admin-only transfer of an approved private archive through standard input.

No passwords, cookies or OAuth values may be passed in command arguments.
The target user and TrackMan player binding are checked before any writes.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.umask(0o077)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    transfer_limit = 512 * 1024 * 1024
    raw = sys.stdin.buffer.read(transfer_limit + 1)
    if len(raw) > transfer_limit:
        raise ValueError("Private transfer exceeds the 512 MiB limit.")
    payload = json.loads(raw)
    del raw
    from app import app
    from extensions import db
    from models import User
    from services.time import server_now
    from services.trackman_api import ROOTS, TrackManClient, TrackManError
    from services.trackman_models import TrackManAccount, TrackManSyncRun
    from services.trackman_rounds import parse_time, save_scorecard
    from services.trackman_sync import account_lock, archive, store_tokens
    with app.app_context():
        user = User.query.filter_by(username=args.username).one()
        with account_lock(user.id):
            account = db.session.get(TrackManAccount, user.id)
            if account is None:
                account = TrackManAccount(user_id=user.id)
                db.session.add(account)
            binding = payload["remote_player_id"]
            if account.remote_player_id and account.remote_player_id != binding:
                raise TrackManError("Target user is already bound to a different TrackMan account.")
            client = TrackManClient(payload["tokens"]["access_token"])
            try:
                profile = client.query("{me{profile{id}}}")["me"]["profile"]
                if profile["id"] != binding:
                    raise TrackManError("The token does not match the approved archive's player.")
            finally:
                client.close()
            allowed = set(ROOTS) | {"schema", "activities_index", "scorecards_index", "partial_responses"}
            count = 0
            for item in payload["records"]:
                if item["category"] not in allowed:
                    raise TrackManError("Unexpected archive category.")
                saved = archive(user.id, item["category"], item["remote_id"], item["data"])
                saved.fetched_at = parse_time(item.get("fetched_at")) or server_now()
                if item["category"] == "scorecards":
                    save_scorecard(user.id, item["data"])
                count += 1
            account.remote_player_id = binding
            store_tokens(account, payload["tokens"])
            account.last_sync_at = server_now()
            account.sync_state = payload["state"]
            account.sync_message = "Historikken er hentet. Se datadekning for begrensninger."
            run = TrackManSyncRun(user_id=user.id, state=payload["state"], finished_at=server_now(), manifest=json.dumps(payload["manifest"], ensure_ascii=False))
            db.session.add(run)
            db.session.commit()
            print("Private TrackMan archive imported for user", user.id, ":", count, "records. Credentials encrypted; binding verified.")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # Do not print a traceback or SQL parameters containing private payloads.
        print("Private TrackMan import failed; no uncommitted records saved.", file=sys.stderr)
        raise SystemExit(1)
