"""Four-area Starttider workspace. Existing BalleTour entitlement is retained."""
import hmac
import json
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, abort, g, jsonify, render_template, request, session, url_for

from extensions import db
from routes.auth import login_required
from services import golfbox as gb
from services import starttider as st
from services.sportsmode import product_access
from services.time import server_now

starttider_bp = Blueprint("starttider", __name__, url_prefix="/starttider")


@starttider_bp.before_request
@login_required
def guard():
    if not product_access(g.current_user)["tour"]:
        abort(403)
    if request.method == "POST":
        if request.content_length and request.content_length > 24000:
            abort(413)
        csrf = session.get("starttider_csrf", "")
        if not csrf or not hmac.compare_digest(csrf, request.headers.get("X-CSRF-Token", "")):
            return jsonify(message="Økten må oppdateres før du sender. Last siden på nytt."), 403
        if session.get("balletour_database_view") == "test":
            return jsonify(message="Booking er deaktivert i BalleTour-testvisning. Bytt til produksjonsvisning først."), 409


@starttider_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@starttider_bp.get("")
@login_required
def index():
    session.setdefault("starttider_csrf", secrets.token_urlsafe(24))
    # Retire only the old oversized cookie-backed booking flow on first entry.
    for key in ("golfbox_ai_chat", "golfbox_pending_booking", "golfbox_pending_cancel", "golfbox_pending_slot_booking"):
        session.pop(key, None)
    row = st.workspace(g.current_user)
    return render_template("starttider.html", initial=st.public_state(row), csrf=session["starttider_csrf"],
        connection=gb.golfbox_connection_summary(g.current_user), today=server_now().date().isoformat(),
        self_name=g.current_user.golfbox_player_name or g.current_user.player.name,
        course_options=sorted(set(gb.OSLO_AREA_COURSES + ["Hauger"]), key=str.casefold))


@starttider_bp.get("/data")
@login_required
def data():
    user = g.current_user
    kind = request.args.get("kind", "state")
    row = st.workspace(user)
    if kind == "state":
        return jsonify(st.public_state(row))
    if kind == "course_resources":
        try:
            return jsonify(st.course_resources(user, row, request.args.get("club")))
        except ValueError as exc:
            return jsonify(message=str(exc)), 400
    if kind == "courses":
        return jsonify(st.course_catalog(user, row, refresh=request.args.get("refresh") == "1"))
    if kind == "favorites":
        options = st.favorites(user)
        from models import GolfBoxFavorite
        latest = db.session.query(db.func.max(GolfBoxFavorite.updated_at)).filter(GolfBoxFavorite.user_id == user.id).scalar()
        return jsonify(players=options, fetched_at=latest.isoformat() if latest else None)
    if kind == "jobs":
        from models import GolfBoxRecurringBooking, GolfBoxScheduledBooking, GolfBoxWatchBooking
        rows = gb.upcoming_golfbox_scheduled_bookings(user)
        models = {"scheduled": GolfBoxScheduledBooking, "recurring": GolfBoxRecurringBooking, "watch": GolfBoxWatchBooking}
        for item in rows:
            job = db.session.get(models[item["type"]], item["id"])
            last = getattr(job, "last_run_at", None)
            item["last_run_at"] = last.isoformat() if last else None
            item["last_message"] = getattr(job, "last_error_message", None) or getattr(job, "last_result_message", None)
        return jsonify(jobs=sorted(rows, key=lambda r: r["execute_at"]))
    if kind == "history":
        try:
            page = max(1, min(100, int(request.args.get("page", "1"))))
        except ValueError:
            return jsonify(message="Ugyldig side."), 400
        rows = gb.golfbox_booking_history(user, limit=page * 10 + 1)
        selected = rows[(page - 1) * 10:page * 10]
        for item in selected:
            item["url"] = url_for("balletour.ai_booking_history_detail", record_type=item["record_type"], record_id=item["id"])
        return jsonify(history=selected, page=page, has_more=len(rows) > page * 10)
    if kind == "bookings":
        cache = json.loads(row.cache_json)
        if request.args.get("refresh") != "1" and cache.get("fetched_at") and datetime.fromisoformat(cache["fetched_at"]) > server_now() - timedelta(seconds=90):
            return jsonify(cache)
        # Release all transaction state before the external login/read.
        db.session.commit()
        result = gb.upcoming_golfbox_bookings(user)
        if result.get("status") == "ok":
            cache = {**result, "fetched_at": server_now().isoformat()}
            db.session.refresh(row)
            catalog = json.loads(row.cache_json).get("course_catalog")
            row.cache_json = st.dumps({**cache, **({"course_catalog": catalog} if catalog else {})})
            db.session.commit()
            return jsonify(cache)
        return jsonify({**result, "bookings": cache.get("bookings", []), "fetched_at": cache.get("fetched_at"),
                        "stale": bool(cache.get("fetched_at"))})
    return jsonify(message="Ukjent visning."), 400


@starttider_bp.post("/players")
@login_required
def players():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(message="Ugyldig spillersøk."), 400
    try:
        return jsonify(players=st.search_players(g.current_user, payload.get("query")))
    except ValueError as exc:
        return jsonify(message=str(exc)), 400
    except Exception:
        db.session.rollback()
        return jsonify(message="Kunne ikke hente spillere fra GolfBox. Prøv igjen. Valgene dine er beholdt."), 502


@starttider_bp.post("/action")
@login_required
def action():
    user = g.current_user
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(message="Ugyldig forespørsel."), 400
    row = st.workspace(user)
    state = st.public_state(row)
    state.pop("revision", None); state.pop("busy", None)
    try:
        st.claim(row, payload.get("revision"))
    except st.StaleDraft as exc:
        return jsonify({**st.public_state(row), "message": str(exc)}), 409
    try:
        operation = payload.get("action")
        state.pop("message", None)
        if operation == "reset":
            state = {"draft": st.default_draft()}
        elif operation in {"draft", "search"}:
            raw = payload.get("draft")
            if not isinstance(raw, dict):
                raise ValueError("Ugyldig søk.")
            state["draft"] = st.validate_draft({**raw, "player_refs": ["self"], "unresolved_names": []}, user)
            state["recent_refs"] = list(dict.fromkeys(state["draft"]["player_refs"] + state.get("recent_refs", [])))[:12]
            state.pop("review", None)
            state.pop("result", None)
            if operation == "search":
                state["result"] = st.search(state["draft"], user)
        elif operation == "interpret":
            draft = st.validate_draft({**payload.get("draft", state["draft"]), "player_refs": ["self"], "unresolved_names": []}, user)
            prompt = str(payload.get("prompt", ""))
            updated, method = st.interpret(prompt, draft, user)
            state["draft"] = updated
            state["method"] = method
            state["chat"] = (state.get("chat", []) + [{"text": prompt[:1000], "reply": "Søket er oppdatert. Kontroller valgene før du søker."}])[-6:]
            state.pop("result", None); state.pop("review", None)
            state["message"] = "Søket er oppdatert. Kontroller valgene før du søker."
        elif operation == "review_slot":
            # Apply current player selection without accepting a client-supplied slot.
            draft = st.validate_draft(payload.get("draft", state["draft"]), user)
            previous = state["draft"]
            if any(draft[k] != previous[k] for k in ("courses", "date", "time_from", "time_to")) or draft["players"] != previous["players"]:
                raise ValueError("Søket er endret. Hent nye tider før du velger.")
            state["draft"] = draft
            state["recent_refs"] = list(dict.fromkeys(draft["player_refs"] + state.get("recent_refs", [])))[:12]
            state["review"] = st.review_slot(payload.get("index"), state, user)
        elif operation == "review_job":
            draft = st.validate_draft(payload.get("draft", state["draft"]), user)
            state["draft"] = draft
            state["recent_refs"] = list(dict.fromkeys(draft["player_refs"] + state.get("recent_refs", [])))[:12]
            state["review"] = st.review_job(payload.get("job") or {}, draft, user)
        elif operation == "review_cancel":
            cache = json.loads(row.cache_json)
            bookings = cache.get("bookings", [])
            index = payload.get("index")
            if not isinstance(index, int) or not 0 <= index < len(bookings) or not bookings[index].get("can_cancel"):
                raise ValueError("Hent Mine tider på nytt og velg en booking som kan avbestilles.")
            b = bookings[index]
            selected = {k: b.get(k) for k in ("booking_guid", "booking_start", "resource_guid")}
            state["review"] = st.new_review(user, "cancel", selected, {"course": b.get("course") or b.get("club"),
                "date": b.get("date"), "time": b.get("time"), "players": [g.current_user.player.name],
                "message": "Avbestiller bare din egen plass i GolfBox. Medspillernes plasser blir stående."})
        elif operation == "review_stop":
            jobs = gb.upcoming_golfbox_scheduled_bookings(user)
            job = next((j for j in jobs if j["id"] == payload.get("id") and j["type"] == payload.get("type") and j["can_cancel"]), None)
            if not job:
                raise ValueError("Dette oppdraget finnes ikke eller kan ikke stoppes nå.")
            state["review"] = st.new_review(user, "stop", {"id": job["id"], "type": job["type"]},
                {"course": job["course"], "date": job["play_date"], "time": job["play_time"], "players": job["players"],
                 "message": "Stopper nye forsøk. Eventuelle bekreftede starttider blir stående."})
        elif operation == "confirm":
            result = st.confirm(str(payload.get("id", "")), user)
            state["outcome"] = result
            state.pop("review", None)
            # Watch activation can find an immediate slot: require a separate booking confirmation.
            if result.get("status") == "confirmation_required" and result.get("pending_booking"):
                p = result["pending_booking"]
                state["review"] = st.new_review(user, "booking", p, {"course": p["course"], "date": p["date"],
                    "time": p["time"], "players": [m["player_name"] for m in p["player_memberships"]],
                    "message": "En tid er ledig nå. Bekreft denne reservasjonen separat."})
            # Invalidate bookings while retaining the independently fetched catalog.
            catalog = json.loads(row.cache_json).get("course_catalog")
            row.cache_json = st.dumps({"course_catalog": catalog} if catalog else {})
        elif operation == "dismiss":
            state.pop("review", None)
        elif operation == "sync_favorites":
            gb.sync_golfbox_favorites(user)
            state["message"] = "Favorittene er oppdatert fra GolfBox."
        else:
            raise ValueError("Ukjent handling.")
        return jsonify(st.save(row, state))
    except (ValueError, TypeError, KeyError) as exc:
        db.session.rollback()
        row = db.session.get(type(row), user.id)
        row.busy = False
        db.session.commit()
        return jsonify({**st.public_state(row), "message": str(exc)}), 400
    except Exception:
        db.session.rollback()
        row = db.session.get(type(row), user.id)
        row.busy = False
        db.session.commit()
        return jsonify({**st.public_state(row), "message": "Tjenesten svarte ikke som forventet. Søket er beholdt. Prøv søket igjen eller bruk de vanlige feltene."}), 502
