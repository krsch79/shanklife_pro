from flask import Blueprint, current_app, render_template, send_from_directory

from models import Round, Player, Course
from services.version import APP_VERSION, get_changelog_entries

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
        app_version=APP_VERSION,
    )


@main_bp.route("/changelog")
def changelog():
    return render_template(
        "changelog.html",
        app_version=APP_VERSION,
        changelog_entries=get_changelog_entries(),
    )


@main_bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
