# Generated: 2026-04-18 01:35 Europe/Oslo
# Version: 1.0.0

import os
from pathlib import Path

from flask import Flask, g, redirect, request, send_file, session, url_for
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from extensions import db
from models import Club, Course, CourseHole, Player, RoundPlayer, User
from routes.main import main_bp
from routes.players import players_bp
from routes.courses import courses_bp
from routes.rounds import rounds_bp
from routes.leaderboard import leaderboard_bp
from routes.auth import auth_bp
from routes.profile import profile_bp
from routes.admin import admin_bp
from routes.series import series_bp
from routes.stats import stats_bp
from routes.balletour import balletour_bp
from routes.golfbox_scores import golfbox_scores_bp
from services.balletour import is_balletour_player
from services.golfbox import migrate_golfbox_password_tokens
from services.time import format_server_datetime


def maintenance_file_path(app):
    configured_path = os.environ.get("SHANKLIFE_MAINTENANCE_FILE", "").strip()
    if configured_path:
        return Path(configured_path)
    return Path(app.instance_path) / "maintenance.lock"


def load_env_file():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def ensure_schema_updates(app):
    with app.app_context():
        inspector = inspect(db.engine)
        table_names = set(inspector.get_table_names())

        def add_column_if_missing(table, column, ddl):
            if table not in table_names:
                return
            columns = {col["name"] for col in inspector.get_columns(table)}
            if column not in columns:
                with db.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))

        if "round_players" in table_names:
            add_column_if_missing("round_players", "selected_tee_id", "selected_tee_id INTEGER")
            add_column_if_missing(
                "round_players",
                "tracks_stats",
                "tracks_stats BOOLEAN DEFAULT 0 NOT NULL",
            )

        if "players" in table_names:
            add_column_if_missing("players", "gender", "gender VARCHAR(10) DEFAULT 'male'")
            add_column_if_missing("players", "profile_image_filename", "profile_image_filename VARCHAR(255)")
            add_column_if_missing("players", "legacy_source", "legacy_source VARCHAR(50)")
            add_column_if_missing("players", "legacy_id", "legacy_id INTEGER")

        if "courses" in table_names:
            add_column_if_missing("courses", "legacy_source", "legacy_source VARCHAR(50)")
            add_column_if_missing("courses", "legacy_id", "legacy_id INTEGER")

        if "rounds" in table_names:
            add_column_if_missing("rounds", "stats_user_id", "stats_user_id INTEGER")
            add_column_if_missing("rounds", "weather_json", "weather_json TEXT")
            add_column_if_missing("rounds", "notes", "notes TEXT")
            add_column_if_missing("rounds", "legacy_source", "legacy_source VARCHAR(50)")
            add_column_if_missing("rounds", "legacy_id", "legacy_id INTEGER")

        if "round_images" in table_names:
            add_column_if_missing("round_images", "hole_number", "hole_number INTEGER")

        if "score_entries" in table_names:
            add_column_if_missing("score_entries", "tee_club_id", "tee_club_id INTEGER")

        if "score_stats" in table_names:
            add_column_if_missing("score_stats", "last_putt_distance_m", "last_putt_distance_m FLOAT")

        if "ai_fix_requests" in table_names:
            add_column_if_missing("ai_fix_requests", "github_issue_number", "github_issue_number INTEGER")
            add_column_if_missing("ai_fix_requests", "github_issue_url", "github_issue_url VARCHAR(255)")
            add_column_if_missing("ai_fix_requests", "github_issue_state", "github_issue_state VARCHAR(30)")
            add_column_if_missing("ai_fix_requests", "github_issue_labels", "github_issue_labels TEXT")
            add_column_if_missing("ai_fix_requests", "github_issue_updated_at", "github_issue_updated_at DATETIME")
            add_column_if_missing("ai_fix_requests", "github_sync_error", "github_sync_error TEXT")

        if "users" in table_names:
            add_column_if_missing("users", "is_admin", "is_admin BOOLEAN DEFAULT 0 NOT NULL")
            add_column_if_missing("users", "email", "email VARCHAR(255)")
            add_column_if_missing(
                "users",
                "email_notifications_enabled",
                "email_notifications_enabled BOOLEAN DEFAULT 1 NOT NULL",
            )
            add_column_if_missing(
                "users",
                "notify_balletour_round_started",
                "notify_balletour_round_started BOOLEAN DEFAULT 1 NOT NULL",
            )
            add_column_if_missing(
                "users",
                "notify_balletour_round_finished",
                "notify_balletour_round_finished BOOLEAN DEFAULT 1 NOT NULL",
            )
            add_column_if_missing(
                "users",
                "notify_shanklife_round_started",
                "notify_shanklife_round_started BOOLEAN DEFAULT 1 NOT NULL",
            )
            add_column_if_missing(
                "users",
                "notify_shanklife_round_finished",
                "notify_shanklife_round_finished BOOLEAN DEFAULT 1 NOT NULL",
            )
            add_column_if_missing(
                "users",
                "notify_version_updates",
                "notify_version_updates BOOLEAN DEFAULT 1 NOT NULL",
            )
            add_column_if_missing(
                "users",
                "balletour_round_notification_player_ids",
                "balletour_round_notification_player_ids TEXT",
            )
            add_column_if_missing("users", "golfbox_username", "golfbox_username VARCHAR(255)")
            add_column_if_missing("users", "golfbox_password_token", "golfbox_password_token TEXT")
            add_column_if_missing("users", "golfbox_player_name", "golfbox_player_name VARCHAR(255)")
            add_column_if_missing("users", "golfbox_home_club_name", "golfbox_home_club_name VARCHAR(255)")
            add_column_if_missing("users", "golfbox_member_number", "golfbox_member_number VARCHAR(50)")
            add_column_if_missing("users", "golfbox_memberships_json", "golfbox_memberships_json TEXT")
            add_column_if_missing("users", "golfbox_credentials_updated_at", "golfbox_credentials_updated_at DATETIME")

            defaults_marker = Path(app.instance_path) / "email_notification_defaults_v2.lock"
            if not defaults_marker.exists():
                with db.engine.begin() as conn:
                    conn.execute(text("UPDATE users SET email_notifications_enabled = 1"))
                    conn.execute(text("UPDATE users SET notify_balletour_round_finished = 1"))
                    conn.execute(text("UPDATE users SET notify_version_updates = 1"))
                    conn.execute(text("UPDATE users SET balletour_round_notification_player_ids = NULL"))
                defaults_marker.parent.mkdir(parents=True, exist_ok=True)
                defaults_marker.write_text("Applied email notification defaults v2.\n", encoding="utf-8")

            migrate_golfbox_password_tokens()

        if "golfbox_recurring_bookings" in table_names:
            add_column_if_missing("golfbox_recurring_bookings", "last_run_at", "last_run_at DATETIME")
            add_column_if_missing("golfbox_recurring_bookings", "last_result_message", "last_result_message TEXT")
            add_column_if_missing("golfbox_recurring_bookings", "last_error_message", "last_error_message TEXT")
            add_column_if_missing("golfbox_recurring_bookings", "cancelled_at", "cancelled_at DATETIME")

        if "golfbox_watch_bookings" in table_names:
            add_column_if_missing("golfbox_watch_bookings", "booked_at", "booked_at DATETIME")
            add_column_if_missing("golfbox_watch_bookings", "booked_time", "booked_time VARCHAR(5)")
            add_column_if_missing("golfbox_watch_bookings", "cancelled_at", "cancelled_at DATETIME")


def ensure_shanklife_club_options(app):
    required_clubs = [
        ("Driver", -30),
        ("3-wood", -20),
        ("5-wood", -10),
        ("2 hybrid", 0),
    ]
    with app.app_context():
        changed = False
        for name, sort_order in required_clubs:
            if Club.query.filter_by(name=name).first():
                continue
            db.session.add(Club(name=name, sort_order=sort_order))
            changed = True
        if changed:
            db.session.commit()


def ensure_course_data_corrections(app):
    with app.app_context():
        changed = False
        for course in Course.query.all():
            normalized_name = course.name.strip().lower().replace(" ", "")
            if normalized_name not in {"hagablå+gul", "hagabla+gul"}:
                continue
            hole = CourseHole.query.filter_by(course_id=course.id, hole_number=17).first()
            if hole and hole.par != 5:
                hole.par = 5
                changed = True
        if changed:
            db.session.commit()


def seed_initial_user(app):
    with app.app_context():
        has_admin = User.query.filter_by(is_admin=True).first() is not None
        kristian_s = Player.query.filter_by(name="Kristian S").first()
        if not kristian_s:
            kristian_s = Player(name="Kristian S", default_hcp=0.0, gender="male")
            db.session.add(kristian_s)
            db.session.flush()

        duplicate = Player.query.filter_by(name="Kristian").first()
        if duplicate and duplicate.id != kristian_s.id:
            RoundPlayer.query.filter_by(player_id=duplicate.id).update(
                {"player_id": kristian_s.id, "player_name_snapshot": kristian_s.name}
            )
            db.session.delete(duplicate)

        user = User.query.filter_by(username="Kristian").first()
        if not user:
            user = User(
                username="Kristian",
                password_hash=generate_password_hash("Kristian"),
                player_id=kristian_s.id,
                is_admin=not has_admin,
            )
            db.session.add(user)
            if user.is_admin:
                has_admin = True
        else:
            user.player_id = kristian_s.id
            if not has_admin:
                user.is_admin = True
                has_admin = True

        erik = Player.query.filter_by(name="Erik").first()
        if not erik:
            erik = Player(name="Erik", default_hcp=18.0, gender="male")
            db.session.add(erik)
            db.session.flush()

        erik_user = User.query.filter_by(username="Erik").first()
        if not erik_user:
            erik_user = User(
                username="Erik",
                password_hash=generate_password_hash("Erik"),
                player_id=erik.id,
                is_admin=False,
            )
            db.session.add(erik_user)
        else:
            erik_user.player_id = erik.id

        db.session.commit()


def create_app():
    load_env_file()
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "shanklife-pro-local-dev-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///shanklife_pro.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = "uploads"
    app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

    db.init_app(app)

    with app.app_context():
        db.create_all()

    ensure_schema_updates(app)
    ensure_shanklife_club_options(app)
    ensure_course_data_corrections(app)
    seed_initial_user(app)

    @app.template_filter("datetime_local")
    def datetime_local(value):
        return format_server_datetime(value)

    @app.before_request
    def show_maintenance_page():
        if request.path.startswith("/static/"):
            return None
        if maintenance_file_path(app).exists():
            return send_file(
                app.root_path + "/static/maintenance.html",
                mimetype="text/html",
                max_age=0,
            ), 503
        return None

    @app.before_request
    def load_current_user():
        user_id = session.get("user_id")
        g.current_user = User.query.get(user_id) if user_id else None

    @app.before_request
    def require_login_for_shanklife():
        if g.get("current_user"):
            return None
        endpoint = request.endpoint or ""
        public_endpoints = {
            "auth.login",
            "auth.accept_balletour_invitation",
            "leaderboard.live_leaderboard",
            "leaderboard.live_leaderboard_partial",
            "leaderboard.leaderboard_player_modal",
            "static",
        }
        if endpoint in public_endpoints:
            return None
        return redirect(url_for("auth.login", next=request.path))

    @app.context_processor
    def inject_current_user():
        current_user = g.get("current_user")
        return {
            "current_user": current_user,
            "current_user_is_balletour_player": is_balletour_player(current_user),
            "current_user_missing_balletour_email": (
                bool(current_user)
                and is_balletour_player(current_user)
                and not (current_user.email or "").strip()
            ),
        }

    app.register_blueprint(main_bp)
    app.register_blueprint(players_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(rounds_bp)
    app.register_blueprint(leaderboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(series_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(balletour_bp)
    app.register_blueprint(golfbox_scores_bp)

    return app


app = create_app()

if __name__ == "__main__":
    debug_enabled = os.environ.get("SHANKLIFE_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=5055, debug=debug_enabled, use_reloader=debug_enabled)
