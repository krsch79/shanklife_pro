"""Owner-scoped TrackMan connection, archive and export."""
import json
import secrets
from datetime import timedelta

from flask import Blueprint, Response, abort, current_app, flash, g, jsonify, redirect, render_template, request, session, stream_with_context, url_for

from extensions import db
from routes.auth import login_required
from services.secret_store import decrypt_secret, encrypt_secret
from services.time import server_now
from services.trackman_api import TrackManClient, TrackManError, device_authorization, oauth_form
from services.trackman_models import TrackManAccount, TrackManArchive, TrackManRound, TrackManSyncRun
from services.trackman_rounds import ENVIRONMENTS, environment_filter, row_summary, user_rounds
from services.trackman_sync import account_lock, start_sync, store_tokens

trackman_bp = Blueprint("trackman", __name__, url_prefix="/me/trackman")


def csrf_token():
    if "trackman_csrf" not in session:
        session["trackman_csrf"] = secrets.token_urlsafe(32)
    return session["trackman_csrf"]


def require_csrf():
    actual = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("trackman_csrf", "")
    if not expected or not secrets.compare_digest(actual, expected):
        abort(400)


@trackman_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


def latest_run(user_id):
    return TrackManSyncRun.query.filter_by(user_id=user_id).order_by(TrackManSyncRun.id.desc()).first()


@trackman_bp.route("/")
@login_required
def index():
    user_id = g.current_user.id
    account = db.session.get(TrackManAccount, user_id)
    run = latest_run(user_id)
    environment = environment_filter(request.args.get("environment"))
    rows = [row_summary(r) for r in user_rounds(user_id, environment)]
    page = max(request.args.get("page", 1, type=int), 1)
    category = request.args.get("category", "activities")
    categories = [r[0] for r in db.session.query(TrackManArchive.category).filter_by(user_id=user_id).distinct().all() if r[0] != "schema"]
    if category not in categories:
        category = "activities"
    query = TrackManArchive.query.filter_by(user_id=user_id, category=category).order_by(TrackManArchive.id.desc())
    count = query.count()
    entries = []
    for row in query.offset((page - 1) * 30).limit(30):
        data = json.loads(row.payload)
        entries.append({"id": row.id, "kind": data.get("kind") or row.typename or category, "time": data.get("time") or data.get("startedAt"), "strokes": data.get("strokeCount"), "title": (data.get("course") or {}).get("displayName") or data.get("subject") or data.get("title") or "TrackMan-data"})
    return render_template("trackman.html", account=account, manifest=json.loads(run.manifest) if run else {}, run=run, rows=rows, csrf_token=csrf_token(), environments=ENVIRONMENTS, environment=environment, entries=entries, categories=categories, category=category, page=page, more=page * 30 < count, archive_count=TrackManArchive.query.filter_by(user_id=user_id).filter(TrackManArchive.category != "schema").count())


@trackman_bp.route("/connect", methods=["POST"])
@login_required
def connect():
    require_csrf()
    try:
        with account_lock(g.current_user.id):
            account = db.session.get(TrackManAccount, g.current_user.id)
            if account is None:
                account = TrackManAccount(user_id=g.current_user.id)
                db.session.add(account)
            device = device_authorization()
            account.device_credentials = encrypt_secret(device["device_code"])
            account.user_code = device["user_code"]
            account.verification_uri = device["verification_uri"]
            account.device_expires_at = server_now() + timedelta(seconds=device["expires_in"])
            account.poll_interval = max(int(device.get("interval", 5)), 5)
            account.next_poll_at = server_now() + timedelta(seconds=account.poll_interval)
            account.sync_state = "authorizing"
            account.sync_message = "Godkjenn tilkoblingen hos TrackMan."
            db.session.commit()
    except TrackManError as exc:
        flash(str(exc), "error")
    return redirect(url_for("trackman.index"))


@trackman_bp.route("/poll", methods=["POST"])
@login_required
def poll():
    require_csrf()
    try:
        with account_lock(g.current_user.id):
            account = db.session.get(TrackManAccount, g.current_user.id)
            if not account or not account.device_credentials:
                return jsonify({"state": "idle"})
            now = server_now()
            if account.device_expires_at <= now:
                account.device_credentials = None
                account.user_code = None
                account.sync_state = "connected" if account.credentials else "disconnected"
                account.sync_message = "Koden er utløpt. Start en ny tilkobling."
                db.session.commit()
                return jsonify({"state": "expired"})
            if account.next_poll_at and account.next_poll_at > now:
                return jsonify({"state": "pending"})
            token = oauth_form("token", {"device_code": decrypt_secret(account.device_credentials), "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
            reason = token.get("error")
            if reason in {"authorization_pending", "slow_down"}:
                if reason == "slow_down":
                    account.poll_interval += 5
                account.next_poll_at = now + timedelta(seconds=account.poll_interval)
                db.session.commit()
                return jsonify({"state": "pending", "interval": account.poll_interval})
            if reason:
                account.device_credentials = None
                account.user_code = None
                account.sync_state = "connected" if account.credentials else "disconnected"
                account.sync_message = "Tilkoblingen ble avbrutt. Prøv igjen."
                db.session.commit()
                return jsonify({"state": "denied"})
            client = TrackManClient(token.get("access_token"))
            try:
                profile = client.query("{me{profile{id}}}")["me"]["profile"]
                if account.remote_player_id and account.remote_player_id != profile["id"]:
                    raise TrackManError("Dette er en annen TrackMan-konto. Koble til den opprinnelige kontoen.")
                account.remote_player_id = profile["id"]
                store_tokens(account, token)
                db.session.commit()
            finally:
                client.close()
        start_sync(current_app._get_current_object(), g.current_user.id)
        return jsonify({"state": "connected"})
    except TrackManError as exc:
        return jsonify({"state": "error", "message": str(exc)}), 409


@trackman_bp.route("/sync", methods=["POST"])
@login_required
def sync():
    require_csrf()
    try:
        with account_lock(g.current_user.id):
            account = db.session.get(TrackManAccount, g.current_user.id)
            if not account or not account.credentials:
                raise TrackManError("Koble til TrackMan først.")
            account.sync_state = "starting"
            db.session.commit()
        start_sync(current_app._get_current_object(), g.current_user.id)
        flash("Synkroniseringen er startet. Du kan bruke appen mens historikken hentes.", "success")
    except TrackManError as exc:
        flash(str(exc), "error")
    return redirect(url_for("trackman.index"))


@trackman_bp.route("/disconnect", methods=["POST"])
@login_required
def disconnect():
    require_csrf()
    try:
        with account_lock(g.current_user.id):
            account = db.session.get(TrackManAccount, g.current_user.id)
            if account:
                account.credentials = None
                account.device_credentials = None
                account.user_code = None
                account.verification_uri = None
                account.sync_state = "disconnected"
                account.sync_message = "Frakoblet. Importerte data er beholdt."
                db.session.commit()
        flash("TrackMan er frakoblet.", "success")
    except TrackManError as exc:
        flash(str(exc), "error")
    return redirect(url_for("trackman.index"))


@trackman_bp.route("/status")
@login_required
def status():
    account = db.session.get(TrackManAccount, g.current_user.id)
    return jsonify({"state": account.sync_state if account else "disconnected", "message": account.sync_message if account else "", "interval": account.poll_interval if account else 5})


@trackman_bp.route("/archive/<int:archive_id>")
@login_required
def archive_detail(archive_id):
    row = TrackManArchive.query.filter_by(id=archive_id, user_id=g.current_user.id).first_or_404()
    return render_template("trackman_detail.html", row=row, data=json.loads(row.payload), raw=row.payload)


@trackman_bp.route("/round/<int:round_id>")
@login_required
def round_detail(round_id):
    row = TrackManRound.query.filter_by(id=round_id, user_id=g.current_user.id).first_or_404()
    archived = TrackManArchive.query.filter_by(user_id=g.current_user.id, category="scorecards", remote_id=row.remote_id).first_or_404()
    return redirect(url_for("trackman.archive_detail", archive_id=archived.id))


@trackman_bp.route("/export")
@login_required
def export():
    user_id = g.current_user.id
    run = latest_run(user_id)
    manifest = json.loads(run.manifest) if run else {}
    @stream_with_context
    def generate():
        yield '{"format":"shanklife-trackman-v1","coverage":' + json.dumps(manifest, ensure_ascii=False) + ',"records":['
        first = True
        for row in TrackManArchive.query.filter_by(user_id=user_id).order_by(TrackManArchive.id).yield_per(20):
            if not first:
                yield ","
            first = False
            yield '{"category":' + json.dumps(row.category) + ',"remote_id":' + json.dumps(row.remote_id) + ',"fetched_at":' + json.dumps(row.fetched_at.isoformat()) + ',"data":' + row.payload + '}'
        yield "]}"
    return Response(generate(), mimetype="application/json", headers={"Content-Disposition": 'attachment; filename="trackman-arkiv.json"', "Cache-Control": "private, no-store"})
