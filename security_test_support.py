"""Browser-equivalent fixtures for existing route regression tests.

Real CSRF and session checks remain enabled. Explicit security negative tests
use Flask's default client instead of this convenience client.
"""
from contextlib import contextmanager
from pathlib import Path
import secrets
from flask.testing import FlaskClient


class SecurityTestClient(FlaskClient):
    def open(self, *args, **kwargs):
        method = kwargs.get("method", "GET").upper()
        if method not in {"GET", "HEAD", "OPTIONS"}:
            headers = dict(kwargs.get("headers") or {})
            if "X-Shanklife-CSRF" not in headers and "shanklife_security" in self.application.extensions:
                token_options = {"method": "GET"}
                if kwargs.get("base_url"):
                    token_options["base_url"] = kwargs["base_url"]
                result = super().open("/_security/csrf", **token_options)
                headers["X-Shanklife-CSRF"] = result.json["csrf_token"]
                kwargs["headers"] = headers
        return super().open(*args, **kwargs)

    @contextmanager
    def session_transaction(self, *args, **kwargs):
        with super().session_transaction(*args, **kwargs) as state:
            yield state
            registry = self.application.extensions.get("shanklife_security")
            if registry is None:
                return
            for key in ("_shared_user_id", "admin_id", "user_id", "user", "passkey_authenticated"):
                if state.get(key):
                    sid = state.setdefault("_security_sid", secrets.token_urlsafe(32))
                    registry.put("login", sid, key + ":" + str(state[key]), 3600)
                    if key in {"user_id", "user"}:
                        from shanklife_security import shared_user, password_version
                        app_name = Path(self.application.root_path).name
                        if app_name == "app":
                            app_name = Path(self.application.root_path).parent.name
                        slug = {"shanklife_pro": None, "Oppskrifter": "oppskrifter"}.get(app_name, app_name)
                        row = shared_user(self.application, slug, **({"username": state[key]} if key == "user" else {"user_id": state[key]}))
                        if row:
                            state["_security_password_version"] = password_version(row)
                    break


def pytest_configure(config):
    from flask import Flask
    Flask.test_client_class = SecurityTestClient
