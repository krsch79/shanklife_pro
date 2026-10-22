"""Small vendored web-security layer, version 1.0.0.

CSRF for cookie-authenticated mutations, revocable login sessions and one-use
challenges. State is per application, never in the shared user database.
"""
import hashlib
from contextlib import contextmanager, closing
import hmac
import html
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit, unquote

from flask import Response, abort, g, jsonify, request, session, redirect, render_template_string, url_for
from werkzeug.security import check_password_hash

VERSION = "1.0.0"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CLIENT_PATH = "/_security/client-1.0.0.js"
CLIENT_JS = r"""(() => {
  const token = document.querySelector('meta[name="shanklife-csrf-token"]')?.content;
  if (!token) return;
  const unsafe = m => !['GET','HEAD','OPTIONS'].includes(String(m || 'GET').toUpperCase());
  const local = u => new URL(u, location.href).origin === location.origin;
  const original = window.fetch.bind(window);
  window.fetch = (input, options = {}) => {
    const method = options.method || (input instanceof Request ? input.method : 'GET');
    const url = input instanceof Request ? input.url : input;
    if (unsafe(method) && local(url)) {
      const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
      headers.set('X-Shanklife-CSRF', token);
      options = {...options, headers};
    }
    return original(input, options);
  };
  const open = XMLHttpRequest.prototype.open, send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url, ...args) {
    this._shanklifeCsrf = unsafe(method) && local(url);
    return open.call(this, method, url, ...args);
  };
  XMLHttpRequest.prototype.send = function(body) {
    if (this._shanklifeCsrf) this.setRequestHeader('X-Shanklife-CSRF', token);
    return send.call(this, body);
  };
  document.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !unsafe(form.method) || !local(form.getAttribute('action') || location.href)) return;
    let field = form.querySelector('input[name="_shanklife_csrf"]');
    if (!field) { field = document.createElement('input'); field.type = 'hidden'; field.name = '_shanklife_csrf'; form.append(field); }
    field.value = token;
  }, true);
})();"""


def safe_next(value, default="/"):
    """Allow only root-relative local paths, including after URL decoding."""
    if not isinstance(value, str) or not value.startswith("/"):
        return default
    decoded = value
    for _ in range(3):
        decoded = unquote(decoded)
    if decoded.startswith("//") or "\\" in decoded or any(ord(c) < 32 or ord(c) == 127 for c in decoded):
        return default
    parsed = urlsplit(value)
    return value if not parsed.scheme and not parsed.netloc else default


class SecurityState:
    def __init__(self, app):
        self.app = app

    @contextmanager
    def connect(self):
        path = Path(self.app.config.get("SECURITY_STATE_DB") or os.environ.get("SECURITY_STATE_DB") or Path(self.app.instance_path) / "security.sqlite3")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        conn = sqlite3.connect(path, timeout=10)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("CREATE TABLE IF NOT EXISTS security_state (kind TEXT, key TEXT, value TEXT, expires REAL, PRIMARY KEY(kind,key))")
        try:
            path.chmod(0o600)
        except PermissionError:
            pass
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get(self, kind, key):
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM security_state WHERE kind=? AND key=? AND expires>?", (kind, key, time.time())).fetchone()
        return row[0] if row else None

    def put(self, kind, key, value, ttl):
        with self.connect() as conn:
            conn.execute("DELETE FROM security_state WHERE expires<=?", (time.time(),))
            conn.execute("INSERT OR REPLACE INTO security_state VALUES (?,?,?,?)", (kind, key, value, time.time() + ttl))

    def consume(self, kind, key):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT value,expires FROM security_state WHERE kind=? AND key=?", (kind, key)).fetchone()
            conn.execute("DELETE FROM security_state WHERE kind=? AND key=?", (kind, key))
        return row[0] if row and row[1] > time.time() else None

    def revoke(self, sid):
        if sid:
            self.consume("login", sid)


def _subject():
    for key in ("_shared_user_id", "admin_id", "user_id", "user", "passkey_authenticated"):
        if session.get(key):
            return key + ":" + str(session[key])
    return None


def install_security(app, *, csrf_exempt_endpoints=(), native_json_prefixes=()):
    """Install once after app setup. Existing auth hooks still authorize routes.

    Native JSON exceptions require an absent Origin and application/json, which
    cannot be posted by an ordinary cross-origin HTML form. Browser origins are
    always checked; no wildcard CORS is installed.
    """
    if "shanklife_security" in app.extensions:
        return app.extensions["shanklife_security"]
    state = SecurityState(app)
    app.extensions["shanklife_security"] = state
    version_root = Path(app.root_path)
    if version_root.name == "app":
        version_root = version_root.parent
    version_path = version_root / "VERSION"
    app_version = version_path.read_text().strip() if version_path.is_file() else VERSION
    app.config.setdefault("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)
    if app.config.get("MAX_CONTENT_LENGTH") is None:
        app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    if os.environ.get("SESSION_COOKIE_SECURE") == "1":
        app.config["SESSION_COOKIE_SECURE"] = True
    if app.config.get("SESSION_COOKIE_SECURE"):
        # Prevent a compromised sibling subdomain from planting an auth cookie.
        app.config.update(SESSION_COOKIE_NAME="__Host-session", SESSION_COOKIE_PATH="/", SESSION_COOKIE_DOMAIN=None)
    app.config.setdefault("MAX_FORM_PARTS", 500)
    app.config.setdefault("MAX_FORM_MEMORY_SIZE", 512 * 1024)

    def token():
        if "_shanklife_csrf" not in session:
            session["_shanklife_csrf"] = secrets.token_urlsafe(32)
        return session["_shanklife_csrf"]

    app.jinja_env.globals["shanklife_csrf_token"] = token

    def guard():
        g._security_sid = session.get("_security_sid")
        subject = _subject()
        allow_fixture = app.testing and app.config.get("SECURITY_ALLOW_TEST_SESSIONS", False)
        if subject and not allow_fixture and state.get("login", session.get("_security_sid", "")) != subject:
            session.clear()
        if request.path == CLIENT_PATH and request.method in {"GET", "HEAD"}:
            response = Response(CLIENT_JS, mimetype="application/javascript")
            response.headers["Cache-Control"] = "public, max-age=86400, immutable"
            return response
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("Origin")
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                abort(403, "Ugyldig forespørselsopprinnelse.")
            if origin is not None and origin.rstrip("/") != request.host_url.rstrip("/"):
                abort(403, "Ugyldig forespørselsopprinnelse.")
            if origin is None and request.headers.get("Referer"):
                ref = urlsplit(request.headers["Referer"])
                if (ref.scheme + "://" + ref.netloc) != request.host_url.rstrip("/"):
                    abort(403, "Ugyldig forespørselsopprinnelse.")
            native_body = request.is_json or (
                request.headers.get("Accept") == "application/json" and (
                    not request.content_length or (
                        request.path == "/api/v1/shanklife/courses/import" and request.mimetype == "multipart/form-data"
                    )
                )
            )
            native = origin is None and not request.headers.get("Sec-Fetch-Site") and native_body and any(request.path.startswith(p) for p in native_json_prefixes)
            if not native and request.endpoint not in csrf_exempt_endpoints:
                submitted = request.headers.get("X-Shanklife-CSRF") or request.form.get("_shanklife_csrf", "")
                expected = session.get("_shanklife_csrf", "")
                if not expected or not isinstance(submitted, str) or not submitted.isascii() or not hmac.compare_digest(expected, submitted):
                    abort(400, "Skjemaet er utløpt. Last siden på nytt.")
        # This route is safe to expose: token is tied to the caller's own cookie.
        if request.path == "/_security/csrf" and request.method == "GET":
            response = jsonify(csrf_token=token())
            response.headers["Cache-Control"] = "no-store"
            return response

    app.before_request_funcs.setdefault(None, []).insert(0, guard)

    @app.after_request
    def secure_response(response):
        old_sid = getattr(g, "_security_sid", None)
        subject = _subject()
        sid = session.get("_security_sid")
        if old_sid and (not subject or sid != old_sid):
            state.revoke(old_sid)
        if subject and not sid:
            sid = secrets.token_urlsafe(32)
            session["_security_sid"] = sid
            token()
            ttl = min(int(app.permanent_session_lifetime.total_seconds()), 180 * 86400)
            state.put("login", sid, subject, ttl)
        if response.mimetype == "text/html" and not response.is_streamed and response.status_code < 400:
            csrf = html.escape(token(), quote=True)
            text = response.get_data(as_text=True)
            field = '<input type="hidden" name="_shanklife_csrf" value="' + csrf + '">'
            def form(match):
                tag = match.group(0)
                return tag + field if re.search(r'\bmethod\s*=\s*[\x22\x27]?post\b', tag, re.I) else tag
            text = re.sub(r"<form\b[^>]*>", form, text, flags=re.I)
            bootstrap = '<meta name="shanklife-csrf-token" content="' + csrf + '"><script src="' + CLIENT_PATH + '"></script>'
            if re.search(r"<head\b[^>]*>", text, re.I):
                text = re.sub(r"(<head\b[^>]*>)", lambda m: m.group(0) + bootstrap, text, count=1, flags=re.I)
            else:
                text = bootstrap + text
            response.set_data(text)
            response.headers["Cache-Control"] = "no-store, private"
            response.vary.add("Cookie")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-App-Version", app_version)
        return response

    return state


def shared_user(app, slug, *, user_id=None, username=None):
    """Read authoritative app grant and password version; never mutate auth DB."""
    path = app.config.get("SHANKLIFE_DB_PATH") or os.environ.get("SHANKLIFE_DB_PATH", "/home/kristian/shanklife_pro/instance/shanklife_pro.db")
    try:
        with closing(sqlite3.connect("file:" + str(Path(path).resolve()) + "?mode=ro", uri=True)) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.row_factory = sqlite3.Row
            user_columns = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
            email_clause = " OR lower(coalesce(u.email,''))=lower(?)" if "email" in user_columns else ""
            identity = "((? IS NOT NULL AND u.id=?) OR (? IS NOT NULL AND (lower(u.username)=lower(?)" + email_clause + ")))"
            args = [user_id, user_id, username, username] + ([username] if email_clause else [])
            if slug is None:
                row = conn.execute("SELECT u.* FROM users u WHERE " + identity, args).fetchone()
            else:
                registry_columns = {r[1] for r in conn.execute("PRAGMA table_info(app_registry)")}
                active = " AND r.is_active=1" if "is_active" in registry_columns else ""
                row = conn.execute("SELECT u.*,a.is_app_admin FROM users u JOIN user_app_access a ON a.user_id=u.id JOIN app_registry r ON r.id=a.app_id WHERE r.slug=? AND a.has_access=1" + active + " AND " + identity, [slug] + args).fetchone()
        result = dict(row) if row else None
        if result is not None:
            result.setdefault("email", None)
            result.setdefault("is_app_admin", result.get("is_admin", 0))
        return result
    except (sqlite3.Error, OSError):
        return None


def password_version(row):
    return hashlib.sha256(row["password_hash"].encode()).hexdigest()


def install_shared_login(app, slug, *, admin_only=False, public_endpoints=(), on_login=None):
    """Protect an existing app using authoritative Shanklife app grants."""
    if not app.secret_key:
        app.secret_key = os.environ.get("SECURITY_SESSION_SECRET")
    if not app.secret_key:
        raise RuntimeError("SECURITY_SESSION_SECRET must be configured for shared login")
    app.config.update(SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "1") == "1")
    public = set(public_endpoints) | {"security_login", "security_logout", "static", "health"}

    @app.route("/_security/login", methods=["GET", "POST"], endpoint="security_login")
    def login():
        error = ""
        if request.method == "POST":
            row = shared_user(app, slug, username=request.form.get("username", "").strip())
            if row and (not admin_only or row["is_app_admin"]) and check_password_hash(row["password_hash"], request.form.get("password", "")):
                session.clear()
                session["_shared_user_id"] = row["id"]
                session["_security_password_version"] = password_version(row)
                session.permanent = True
                if on_login:
                    on_login(row)
                return redirect(safe_next(request.args.get("next")))
            error = "Feil brukernavn eller passord, eller du mangler tilgang."
        return render_template_string('''<!doctype html><html lang="no"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Logg inn</title></head><body><main><h1>Logg inn med Shanklife</h1><p role="alert">{{ error }}</p><form method="post"><p><label>Brukernavn <input name="username" autocomplete="username" required></label></p><p><label>Passord <input type="password" name="password" autocomplete="current-password" required></label></p><button type="submit">Logg inn</button></form></main></body></html>''', error=error)

    @app.post("/_security/logout", endpoint="security_logout")
    def logout():
        session.clear()
        return redirect(url_for("security_login"))

    @app.before_request
    def authorize():
        g.shared_user = None
        if session.get("_shared_user_id"):
            row = shared_user(app, slug, user_id=session["_shared_user_id"])
            if not row or (admin_only and not row["is_app_admin"]) or password_version(row) != session.get("_security_password_version"):
                session.clear()
            else:
                g.shared_user = row
        if request.endpoint in public:
            return None
        if not g.shared_user:
            if request.path.startswith("/api/"):
                return jsonify(error="Du må logge inn med riktig apptilgang."), 401
            return redirect(url_for("security_login", next=safe_next(request.path)))
        return None


def revalidate_shared_sessions(app, slug, identity_key="user_id"):
    """Refresh grants and reject sessions after central password/access changes."""
    @app.before_request
    def refresh_grant():
        if not session.get(identity_key) or (app.testing and app.config.get("SECURITY_ALLOW_TEST_SESSIONS")):
            return None
        row = shared_user(app, slug, **({"username": session[identity_key]} if identity_key == "user" else {"user_id": session[identity_key]}))
        if not row or session.get("_security_password_version") != password_version(row):
            session.clear()
        else:
            session["is_admin"] = bool(row["is_app_admin"])
            session["username"] = row["username"]
            if identity_key == "user":
                session["role"] = "owner" if row["is_app_admin"] else "guest"

    # Run before app-specific hooks populate g or authorize a protected action.
    app.before_request_funcs[None].remove(refresh_grant)
    app.before_request_funcs[None].insert(0, refresh_grant)

    @app.after_request
    def remember_password(response):
        if session.get(identity_key) and not session.get("_security_password_version"):
            row = shared_user(app, slug, **({"username": session[identity_key]} if identity_key == "user" else {"user_id": session[identity_key]}))
            if row:
                session["_security_password_version"] = password_version(row)
            elif not (app.testing and app.config.get("SECURITY_ALLOW_TEST_SESSIONS")):
                session.clear()
        return response
