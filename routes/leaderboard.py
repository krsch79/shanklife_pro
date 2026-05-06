from flask import Blueprint, render_template, request

from services.leaderboard import build_live_leaderboards, build_round_player_modal_data
from services.tee_filters import selected_tee_key, tee_filter_options

leaderboard_bp = Blueprint("leaderboard", __name__)


@leaderboard_bp.route("/leaderboard/live")
def live_leaderboard():
    view_mode = request.args.get("view", "gross").strip().lower()
    if view_mode not in ("gross", "net"):
        view_mode = "gross"

    tee_key = selected_tee_key(request.args.get("tee"))
    boards = build_live_leaderboards(view_mode=view_mode, tee_key=tee_key)
    return render_template(
        "live_leaderboard.html",
        boards=boards,
        view_mode=view_mode,
        selected_tee_key=tee_key,
        tee_options=tee_filter_options(),
    )


@leaderboard_bp.route("/leaderboard/live/partial")
def live_leaderboard_partial():
    view_mode = request.args.get("view", "gross").strip().lower()
    if view_mode not in ("gross", "net"):
        view_mode = "gross"

    tee_key = selected_tee_key(request.args.get("tee"))
    boards = build_live_leaderboards(view_mode=view_mode, tee_key=tee_key)
    return render_template(
        "live_leaderboard_content.html",
        boards=boards,
        view_mode=view_mode,
        selected_tee_key=tee_key,
    )


@leaderboard_bp.route("/leaderboard/player/<int:round_player_id>/modal")
def leaderboard_player_modal(round_player_id):
    data = build_round_player_modal_data(round_player_id)
    return render_template("leaderboard_player_modal.html", data=data)
