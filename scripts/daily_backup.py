import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app
from services.admin_tools import create_backup


with app.app_context():
    filename = create_backup("Automatisk daglig backup")
    print(f"Backup lagret: {filename}")
