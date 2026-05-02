import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT.parent / "golftracker"
SOURCE_DB = SOURCE_ROOT / "golf.db"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from werkzeug.security import generate_password_hash  # noqa: E402

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import (  # noqa: E402
    Club,
    Course,
    CourseHole,
    CourseTee,
    CourseTeeLength,
    CourseTeeRating,
    Player,
    PlayerHoleDefaultClub,
    Round,
    RoundImage,
    RoundPlayer,
    ScoreEntry,
    Series,
    SeriesPlayer,
    User,
)
from services.time import server_now  # noqa: E402

LEGACY_SOURCE = "golftracker"
SERIES_NAME = "Balletour"
COURSE_NAME = "Balletour Par 3"


def connect_source():
    conn = sqlite3.connect(SOURCE_DB)
    conn.row_factory = sqlite3.Row
    return conn


def parse_started_at(played_date, start_time):
    raw = f"{played_date} {start_time or '12:00'}"
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    return datetime.strptime(played_date, "%Y-%m-%d")


def get_or_create_player(old_player):
    mapping = {
        "Kristian S": "Kristian S",
        "Erik": "Erik",
        "Martin": "Martin",
        "Christian H": "Christian H",
    }
    name = mapping.get(old_player["name"], old_player["name"])
    player = Player.query.filter_by(name=name).first()
    if not player:
        player = Player(name=name, gender="male", default_hcp=0.0)
        db.session.add(player)
        db.session.flush()
    player.legacy_source = LEGACY_SOURCE
    player.legacy_id = old_player["id"]
    player.profile_image_filename = old_player["profile_image_filename"]
    return player


def ensure_user_for_player(old_player, player):
    username = (old_player["username"] or "").strip()
    password_hash = old_player["password_hash"]
    if not username:
        return

    existing = User.query.filter_by(username=username).first()
    if existing:
        existing.player_id = player.id
        if old_player["is_admin"]:
            existing.is_admin = True
        return

    db.session.add(
        User(
            username=username,
            password_hash=password_hash or generate_password_hash(username),
            player_id=player.id,
            is_admin=bool(old_player["is_admin"]),
        )
    )


def ensure_course(conn):
    course = Course.query.filter_by(legacy_source=LEGACY_SOURCE, legacy_id=1).first()
    if not course:
        course = Course.query.filter_by(name=COURSE_NAME).first()
    if not course:
        course = Course(name=COURSE_NAME, hole_count=9, legacy_source=LEGACY_SOURCE, legacy_id=1)
        db.session.add(course)
        db.session.flush()

    course.name = COURSE_NAME
    course.hole_count = 9
    course.legacy_source = LEGACY_SOURCE
    course.legacy_id = 1

    holes = conn.execute("SELECT * FROM holes ORDER BY hole_number").fetchall()
    old_hole_map = {}
    for old_hole in holes:
        hole = CourseHole.query.filter_by(course_id=course.id, hole_number=old_hole["hole_number"]).first()
        if not hole:
            hole = CourseHole(
                course_id=course.id,
                hole_number=old_hole["hole_number"],
                par=old_hole["par"],
                stroke_index=old_hole["hole_number"],
            )
            db.session.add(hole)
            db.session.flush()
        hole.par = old_hole["par"]
        old_hole_map[old_hole["id"]] = hole

    tee_map = {}
    for display_order, old_name in enumerate(("gul", "rod"), start=1):
        tee_name = old_name.capitalize()
        tee = CourseTee.query.filter_by(course_id=course.id, name=tee_name).first()
        if not tee:
            tee = CourseTee(course_id=course.id, name=tee_name, display_order=display_order)
            db.session.add(tee)
            db.session.flush()
        tee.display_order = display_order
        tee_map[old_name] = tee

        for gender in ("male", "female"):
            rating = CourseTeeRating.query.filter_by(tee_id=tee.id, gender=gender).first()
            if not rating:
                db.session.add(
                    CourseTeeRating(
                        tee_id=tee.id,
                        gender=gender,
                        slope=113,
                        course_rating=27.0,
                    )
                )

        for old_hole in holes:
            hole = old_hole_map[old_hole["id"]]
            length = CourseTeeLength.query.filter_by(tee_id=tee.id, hole_number=hole.hole_number).first()
            if not length:
                length = CourseTeeLength(tee_id=tee.id, hole_id=hole.id, hole_number=hole.hole_number, length_meters=1)
                db.session.add(length)
            length.hole_id = hole.id
            length.length_meters = old_hole[f"length_{old_name}"]

    return course, tee_map, old_hole_map


def ensure_clubs(conn):
    club_map = {}
    for old_club in conn.execute("SELECT * FROM clubs ORDER BY sort_order, id").fetchall():
        club = Club.query.filter_by(legacy_source=LEGACY_SOURCE, legacy_id=old_club["id"]).first()
        if not club:
            club = Club.query.filter_by(name=old_club["name"]).first()
        if not club:
            club = Club(name=old_club["name"])
            db.session.add(club)
            db.session.flush()
        club.sort_order = old_club["sort_order"]
        club.legacy_source = LEGACY_SOURCE
        club.legacy_id = old_club["id"]
        club_map[old_club["id"]] = club
    return club_map


def copy_images():
    uploads_root = ROOT / "uploads"
    for folder in ("profile-images", "round-images"):
        src = SOURCE_ROOT / "static" / "uploads" / folder
        dst = uploads_root / folder
        dst.mkdir(parents=True, exist_ok=True)
        if not src.exists():
            continue
        for path in src.iterdir():
            if path.is_file() and not (dst / path.name).exists():
                shutil.copy2(path, dst / path.name)


def import_data():
    if not SOURCE_DB.exists():
        raise RuntimeError(f"Fant ikke gammel database: {SOURCE_DB}")

    conn = connect_source()
    course, tee_map, old_hole_map = ensure_course(conn)
    club_map = ensure_clubs(conn)

    player_map = {}
    for old_player in conn.execute("SELECT * FROM players ORDER BY id").fetchall():
        player = get_or_create_player(old_player)
        ensure_user_for_player(old_player, player)
        player_map[old_player["id"]] = player

    series = Series.query.filter_by(name=SERIES_NAME).first()
    if not series:
        series = Series(name=SERIES_NAME, course_id=course.id, min_qualifying_rounds=20)
        db.session.add(series)
        db.session.flush()
    series.course_id = course.id

    for index, player in enumerate(player_map.values(), start=1):
        membership = SeriesPlayer.query.filter_by(series_id=series.id, player_id=player.id).first()
        if not membership:
            db.session.add(SeriesPlayer(series_id=series.id, player_id=player.id, display_order=index))

    round_map = {}
    for old_round in conn.execute("SELECT * FROM rounds ORDER BY id").fetchall():
        existing = Round.query.filter_by(legacy_source=LEGACY_SOURCE, legacy_id=old_round["id"]).first()
        if existing:
            round_map[old_round["id"]] = existing
            continue

        old_round_players = conn.execute("SELECT * FROM round_players WHERE round_id = ?", (old_round["id"],)).fetchall()
        score_count = conn.execute("SELECT COUNT(*) AS count FROM hole_scores WHERE round_id = ?", (old_round["id"],)).fetchone()["count"]
        expected_scores = len(old_round_players) * course.hole_count
        status = "finished" if score_count == expected_scores else "ongoing"
        started_at = parse_started_at(old_round["played_date"], old_round["start_time"])
        weather_json = old_round["weather"] if "weather" in old_round.keys() else None

        round_obj = Round(
            course_id=course.id,
            status=status,
            started_at=started_at,
            finished_at=started_at if status == "finished" else None,
            weather_json=weather_json,
            notes=old_round["notes"] if "notes" in old_round.keys() else None,
            legacy_source=LEGACY_SOURCE,
            legacy_id=old_round["id"],
        )
        db.session.add(round_obj)
        db.session.flush()
        round_map[old_round["id"]] = round_obj

        round_player_map = {}
        for old_rp in old_round_players:
            player = player_map[old_rp["player_id"]]
            rp = RoundPlayer(
                round_id=round_obj.id,
                player_id=player.id,
                selected_tee_id=tee_map[old_round["tee_type"]].id,
                player_name_snapshot=player.name,
                hcp_for_round=player.default_hcp,
            )
            db.session.add(rp)
            db.session.flush()
            round_player_map[old_rp["player_id"]] = rp

        old_scores = conn.execute("SELECT * FROM hole_scores WHERE round_id = ?", (old_round["id"],)).fetchall()
        scores_by_player_hole = {
            (row["player_id"], old_hole_map[row["hole_id"]].hole_number): row
            for row in old_scores
        }

        for old_player_id, rp in round_player_map.items():
            for hole_number in range(1, course.hole_count + 1):
                old_score = scores_by_player_hole.get((old_player_id, hole_number))
                db.session.add(
                    ScoreEntry(
                        round_id=round_obj.id,
                        round_player_id=rp.id,
                        hole_number=hole_number,
                        strokes=old_score["strokes"] if old_score else None,
                        tee_club_id=club_map[old_score["tee_club_id"]].id if old_score and old_score["tee_club_id"] else None,
                    )
                )

    if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='player_hole_defaults'").fetchone():
        for row in conn.execute("SELECT * FROM player_hole_defaults").fetchall():
            player = player_map.get(row["player_id"])
            hole = old_hole_map.get(row["hole_id"])
            club = club_map.get(row["default_club_id"])
            if not player or not hole or not club:
                continue
            default = PlayerHoleDefaultClub.query.filter_by(
                player_id=player.id,
                course_id=course.id,
                hole_number=hole.hole_number,
            ).first()
            if not default:
                default = PlayerHoleDefaultClub(
                    player_id=player.id,
                    course_id=course.id,
                    hole_number=hole.hole_number,
                    club_id=club.id,
                )
                db.session.add(default)
            default.club_id = club.id

    if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='round_images'").fetchone():
        for old_image in conn.execute("SELECT * FROM round_images").fetchall():
            if RoundImage.query.filter_by(legacy_source=LEGACY_SOURCE, legacy_id=old_image["id"]).first():
                continue
            round_obj = round_map.get(old_image["round_id"])
            if not round_obj:
                continue
            tagged_player = player_map.get(old_image["tagged_player_id"]) if old_image["tagged_player_id"] else None
            uploaded_at = datetime.fromisoformat(old_image["uploaded_at"]) if old_image["uploaded_at"] else server_now()
            db.session.add(
                RoundImage(
                    round_id=round_obj.id,
                    filename=old_image["filename"],
                    tagged_player_id=tagged_player.id if tagged_player else None,
                    uploaded_at=uploaded_at,
                    legacy_source=LEGACY_SOURCE,
                    legacy_id=old_image["id"],
                )
            )

    copy_images()
    db.session.commit()
    conn.close()


def main():
    app = create_app()
    with app.app_context():
        import_data()
        print("Golftracker er importert til Shanklife Pro.")


if __name__ == "__main__":
    main()
