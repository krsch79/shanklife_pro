from flask import Blueprint, render_template, request

from services.leaderboard import build_live_leaderboards, build_round_player_modal_data

leaderboard_bp = Blueprint("leaderboard", __name__)


@leaderboard_bp.route("/leaderboard/live")
def live_leaderboard():
    view_mode = request.args.get("view", "gross").strip().lower()
    if view_mode not in ("gross", "net"):
        view_mode = "gross"

    boards = build_live_leaderboards(view_mode=view_mode)
    return render_template("live_leaderboard.html", boards=boards, view_mode=view_mode)


@leaderboard_bp.route("/leaderboard/live/partial")
def live_leaderboard_partial():
    view_mode = request.args.get("view", "gross").strip().lower()
    if view_mode not in ("gross", "net"):
        view_mode = "gross"

    boards = build_live_leaderboards(view_mode=view_mode)
    return render_template("live_leaderboard_content.html", boards=boards, view_mode=view_mode)


@leaderboard_bp.route("/leaderboard/player/<int:round_player_id>/modal")
def leaderboard_player_modal(round_player_id):
    data = build_round_player_modal_data(round_player_id)
    return render_template("leaderboard_player_modal.html", data=data)
