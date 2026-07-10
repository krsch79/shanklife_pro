#!/usr/bin/env python3
import argparse
import getpass
import os

from garminconnect import Garmin

from app import app
from models import User
from services.garmin_golf import garmin_token_store_path


def main():
    parser = argparse.ArgumentParser(description="Koble en Shanklife-bruker til Garmin uten å lagre passordet.")
    parser.add_argument("--username", required=True, help="Shanklife-brukernavn")
    args = parser.parse_args()

    with app.app_context():
        user = User.query.filter(User.username.ilike(args.username)).first()
        if not user:
            raise SystemExit(f"Fant ikke Shanklife-brukeren {args.username!r}.")
        token_store = garmin_token_store_path(user)

    email = input("Garmin e-post: ").strip()
    password = getpass.getpass("Garmin passord (lagres ikke): ")
    if not email or not password:
        raise SystemExit("Både e-post og passord må fylles ut.")

    old_umask = os.umask(0o077)
    try:
        token_store.mkdir(parents=True, exist_ok=True, mode=0o700)
        client = Garmin(email, password, prompt_mfa=lambda: input("Garmin engangskode: ").strip())
        client.login(str(token_store))
        token_store.chmod(0o700)
        for token_file in token_store.iterdir():
            if token_file.is_file():
                token_file.chmod(0o600)
    finally:
        os.umask(old_umask)
        password = ""

    print(f"Garmin er koblet til Shanklife-brukeren {args.username}. Passordet ble ikke lagret.")


if __name__ == "__main__":
    main()
