#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    flag = Path(os.environ.get("SHANKLIFE_MAINTENANCE_FILE", str(ROOT / "instance" / "maintenance.lock")))
    if flag.exists():
        print("GolfBox scheduled work deferred during maintenance.")
        return
    from app import create_app
    from services.golfbox import run_due_golfbox_scheduled_bookings
    app = create_app()
    with app.app_context():
        results = run_due_golfbox_scheduled_bookings()
    if results:
        print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
