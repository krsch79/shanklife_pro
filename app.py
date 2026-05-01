# Generated: 2026-04-18 01:35 Europe/Oslo
# Version: 1.0.0

import os

from flask import Flask, g, session
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from extensions import db
from models import Player, RoundPlayer, User
from routes.main import main_bp
from routes.players import players_bp
from routes.courses import courses_bp
from routes.rounds import rounds_bp
from routes.leaderboard import leaderboard_bp
from routes.auth import auth_bp
from routes.profile import profile_bp
from routes.admin import admin_bp
from routes.series import series_bp
from routes.balletour import balletour_bp
from services.balletour import is_balletour_player


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
            add_column_if_missing("ai_fix_requests", "github_sync_error", "github_sync_error TEXT")

        if "users" in table_names:
            add_column_if_missing("users", "is_admin", "is_admin BOOLEAN DEFAULT 0 NOT NULL")


def seed_initial_user(app):
    with app.app_context():
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
                is_admin=True,
            )
            db.session.add(user)
        else:
            user.player_id = kristian_s.id
            user.is_admin = True

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
    seed_initial_user(app)

    @app.template_filter("datetime_local")
    def datetime_local(value):
        if not value:
            return "-"
        return value.strftime("%d.%m.%Y %H:%M")

    @app.before_request
    def load_current_user():
        user_id = session.get("user_id")
        g.current_user = User.query.get(user_id) if user_id else None

    @app.context_processor
    def inject_current_user():
        current_user = g.get("current_user")
        return {
            "current_user": current_user,
            "current_user_is_balletour_player": is_balletour_player(current_user),
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
    app.register_blueprint(balletour_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5055, debug=True)
