#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from services.golfbox import run_due_golfbox_scheduled_bookings


def main():
    app = create_app()
    with app.app_context():
        results = run_due_golfbox_scheduled_bookings()
    if results:
        print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
