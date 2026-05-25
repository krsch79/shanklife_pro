import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


FERNET_PREFIX = "fernet$"


def encrypt_secret(value):
    raw_value = value or ""
    token = _fernet().encrypt(raw_value.encode("utf-8")).decode("ascii")
    return f"{FERNET_PREFIX}{token}"


def decrypt_secret(token):
    raw_token = token or ""
    if not raw_token.startswith(FERNET_PREFIX):
        raise InvalidToken("Unknown secret token format.")
    encrypted = raw_token.removeprefix(FERNET_PREFIX).encode("ascii")
    return _fernet().decrypt(encrypted).decode("utf-8")


def is_encrypted_secret(token):
    return bool((token or "").startswith(FERNET_PREFIX))


def _fernet():
    return Fernet(_fernet_key())


def _fernet_key():
    configured_key = os.environ.get("SHANKLIFE_CREDENTIAL_KEY", "").strip()
    if configured_key:
        return _normalize_key(configured_key)

    secret_key = current_app.config.get("SECRET_KEY") or "shanklife-pro-local-dev-key"
    return _derive_key(f"shanklife-credential-store:{secret_key}")


def _normalize_key(value):
    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii"))
    except (ValueError, TypeError):
        decoded = b""
    if len(decoded) == 32:
        return value.encode("ascii")
    return _derive_key(value)


def _derive_key(value):
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)
