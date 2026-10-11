#!/usr/bin/env python3
"""Full-history scheduled sync. Private credentials remain in the database."""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.umask(0o077)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int)
    args = parser.parse_args()
    if Path(os.environ.get("SHANKLIFE_MAINTENANCE_FILE", str(ROOT / "instance" / "maintenance.lock"))).exists():
        print("TrackMan sync deferred during maintenance.")
        return 0
    from app import create_app
    from extensions import db
    from services.trackman_api import TrackManError
    from services.trackman_models import TrackManAccount
    from services.trackman_sync import sync_account
    app = create_app()
    failed = False
    with app.app_context():
        from app import maintenance_file_path
        if maintenance_file_path(app).exists():
            print("TrackMan sync deferred during maintenance.")
            return 0
        accounts = TrackManAccount.query.filter(TrackManAccount.credentials.isnot(None), TrackManAccount.device_credentials.is_(None))
        if args.user_id:
            accounts = accounts.filter_by(user_id=args.user_id)
        ids = [a.user_id for a in accounts.all()]
        for user_id in ids:
            try:
                report = sync_account(user_id)
                # Only counts/status in operational output, never user payloads.
                print("TrackMan user", user_id, "sources", len(report["sources"]), "failed", len(report["errors"]), "coverage gaps", len(report["field_gaps"]))
                failed |= bool(report["errors"])
            except TrackManError:
                print("TrackMan user", user_id, "sync failed or busy; see private connection page.")
                failed = True
            finally:
                db.session.remove()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
