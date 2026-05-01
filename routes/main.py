from flask import Blueprint, current_app, render_template, send_from_directory

from models import Round, Player, Course

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    ongoing_count = Round.query.filter_by(status="ongoing").count()
    finished_count = Round.query.filter_by(status="finished").count()
    player_count = Player.query.count()
    course_count = Course.query.count()

    return render_template(
        "index.html",
        ongoing_count=ongoing_count,
        finished_count=finished_count,
        player_count=player_count,
        course_count=course_count,
    )


@main_bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
