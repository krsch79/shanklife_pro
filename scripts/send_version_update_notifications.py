import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
from services.user_notifications import send_version_update_notifications  # noqa: E402


def main():
    with app.app_context():
        sent = send_version_update_notifications(app.instance_path)
    print(f"Versjonsvarsel sendt til {sent} mottaker(e).")


if __name__ == "__main__":
    main()
