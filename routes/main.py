from flask import Blueprint, current_app, g, render_template, send_from_directory, request

from models import Round, Player, Course
from services.version import APP_VERSION, get_balletour_changelog_entries, get_shanklife_changelog_entries

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    from services.sportsmode import dashboard_payload
    return render_template("index.html", dashboard=dashboard_payload(g.current_user), app_version=APP_VERSION)



@main_bp.route("/changelog")
def changelog():
    return render_template(
        "changelog.html",
        app_version=APP_VERSION,
        changelog_entries=get_shanklife_changelog_entries(),
        balletour_changelog_entries=get_balletour_changelog_entries(),
    )


@main_bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@main_bp.get("/sports/start")
def sports_start():
    return render_template("sports_start.html")


@main_bp.get("/sports/insight")
def sports_insight():
    from services.sportsmode import product_access
    from routes.stats import _player_stats
    from services.trackman_rounds import merge_stats, environment_filter, user_rounds
    access = product_access(g.current_user)
    environment = environment_filter(request.args.get("environment"))
    stats = merge_stats(_player_stats(g.current_user.player, environment), user_rounds(g.current_user.id, environment)) if access["shanklife"] else None
    return render_template("sports_insight.html", stats=stats, environment=environment)


@main_bp.get("/sports/rounds")
def sports_rounds():
    from services.sportsmode import personal_round_items
    from services.trackman_rounds import environment_filter
    environment = environment_filter(request.args.get("environment"))
    source = request.args.get("source", "all")
    if source not in {"all", "shanklife", "balletour", "trackman"}: source = "all"
    rows = personal_round_items(g.current_user, environment, source)
    return render_template("sports_rounds.html", round_items=rows, environment=environment, source=source)


@main_bp.get("/sports/tour")
def sports_tour():
    from services.sportsmode import product_access
    from flask import redirect, url_for
    if product_access(g.current_user)["tour"]:
        return redirect(url_for("balletour.index"))
    return render_template("sports_tour.html")
