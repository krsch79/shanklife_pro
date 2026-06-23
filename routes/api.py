from functools import wraps

from flask import Blueprint, g, jsonify, request, session
from werkzeug.security import check_password_hash

from models import Course, Round, SeriesPlayer, User
from services.balletour import BALLETOUR_MENU_LABEL, get_balletour_series, is_balletour_player
from services.version import APP_VERSION

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def _user_payload(user):
    player = user.player if user else None
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_admin": bool(user.is_admin),
        "player": {
            "id": player.id,
            "name": player.name,
            "gender": player.gender,
            "default_hcp": player.default_hcp,
            "profile_image_url": f"/uploads/{player.profile_image_filename}" if player.profile_image_filename else None,
        } if player else None,
        "products": {
            "shanklife": True,
            "balletour": is_balletour_player(user),
        },
    }


def _round_payload(round_obj):
    return {
        "id": round_obj.id,
        "status": round_obj.status,
        "started_at": round_obj.started_at.isoformat() if round_obj.started_at else None,
        "finished_at": round_obj.finished_at.isoformat() if round_obj.finished_at else None,
        "played_hole_count": round_obj.played_hole_count,
        "course": {
            "id": round_obj.course.id,
            "name": round_obj.course.name,
            "hole_count": round_obj.course.hole_count,
        } if round_obj.course else None,
        "players": [
            {
                "id": round_player.player_id,
                "name": round_player.player_name_snapshot,
                "hcp": round_player.hcp_for_round,
                "tracks_stats": bool(round_player.tracks_stats),
            }
            for round_player in round_obj.round_players
        ],
    }


def api_login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not g.get("current_user"):
            return jsonify({"error": {"code": "unauthorized", "message": "Du må logge inn først."}}), 401
        return view(*args, **kwargs)

    return wrapped_view


@api_bp.route("/health")
def health():
    return jsonify({"status": "ok", "version": APP_VERSION})


@api_bp.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": {"code": "invalid_credentials", "message": "Feil brukernavn eller passord."}}), 401

    session.clear()
    session["user_id"] = user.id
    return jsonify({"user": _user_payload(user)})


@api_bp.route("/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "logged_out"})


@api_bp.route("/auth/me")
@api_login_required
def me():
    return jsonify({"user": _user_payload(g.current_user)})


@api_bp.route("/bootstrap")
@api_login_required
def bootstrap():
    return jsonify({
        "version": APP_VERSION,
        "user": _user_payload(g.current_user),
        "products": [
            {
                "id": "shanklife",
                "name": "Shanklife Pro",
                "enabled": True,
                "navigation": [
                    {"id": "rounds", "title": "Runder"},
                    {"id": "stats", "title": "Statistikk"},
                    {"id": "courses", "title": "Baner"},
                    {"id": "profile", "title": "Profil"},
                ],
            },
            {
                "id": "balletour",
                "name": BALLETOUR_MENU_LABEL,
                "enabled": is_balletour_player(g.current_user),
                "navigation": [
                    {"id": "rounds", "title": "Runder"},
                    {"id": "leaderboard", "title": "Live"},
                    {"id": "stats", "title": "Statistikk"},
                    {"id": "players", "title": "Spillere"},
                ],
            },
        ],
    })


@api_bp.route("/shanklife/overview")
@api_login_required
def shanklife_overview():
    rounds = (
        Round.query.order_by(Round.started_at.desc())
        .limit(10)
        .all()
    )
    return jsonify({
        "course_count": Course.query.count(),
        "recent_rounds": [_round_payload(round_obj) for round_obj in rounds],
    })


@api_bp.route("/balletour/overview")
@api_login_required
def balletour_overview():
    balletour_series = get_balletour_series()
    memberships = (
        SeriesPlayer.query.filter_by(series_id=balletour_series.id)
        .join(SeriesPlayer.player)
        .order_by(SeriesPlayer.display_order.asc())
        .all()
        if balletour_series else []
    )
    return jsonify({
        "enabled": is_balletour_player(g.current_user),
        "players": [
            {
                "id": membership.player.id,
                "name": membership.player.name,
                "display_order": membership.display_order,
            }
            for membership in memberships
        ],
    })
