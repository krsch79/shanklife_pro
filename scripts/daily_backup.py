import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app
from services.admin_tools import create_backup, create_daily_backup_if_due


parser = argparse.ArgumentParser()
parser.add_argument("--force", action="store_true", help="Ta backup uavhengig av daglig tidsvindu.")
parser.add_argument("--name", default="Automatisk daglig backup")
args = parser.parse_args()

with app.app_context():
    if args.force:
        filename = create_backup(args.name)
        print(f"Backup lagret: {filename}")
    else:
        filename, reason = create_daily_backup_if_due()
        if filename:
            print(f"Backup lagret: {filename}")
        else:
            print(f"Hopper over backup: {reason}")
