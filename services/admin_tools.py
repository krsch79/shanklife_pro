import json
import os
import random
import re
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from flask import current_app

from extensions import db
from models import Club, Course, Player, Round, RoundImage, RoundPlayer, ScoreEntry, ScoreStat, User


class DatabaseWriteError(RuntimeError):
    pass


def _instance_dir():
    return Path(db.engine.url.database).resolve().parent


def backup_dir():
    path = _instance_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path():
    return Path(db.engine.url.database).resolve()


def _make_writable(path):
    path = Path(path)
    if not path.exists():
        return
    mode = path.stat().st_mode
    if path.is_dir():
        path.chmod(mode | 0o700)
    else:
        path.chmod(mode | 0o600)


def ensure_database_writable():
    db_path = database_path()
    instance_path = db_path.parent

    _make_writable(instance_path)
    _make_writable(db_path)

    if not os.access(instance_path, os.W_OK | os.X_OK):
        raise DatabaseWriteError(f"Instance-mappen er ikke skrivbar: {instance_path}")

    if not os.access(db_path, os.W_OK):
        raise DatabaseWriteError(f"Databasefilen er ikke skrivbar: {db_path}")


def manifest_path():
    return backup_dir() / "manifest.json"


def _load_manifest():
    path = manifest_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_manifest(manifest):
    manifest_path().write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _slugify(value):
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return slug or "backup"


def list_backups():
    manifest = _load_manifest()
    backups = []
    for path in sorted(backup_dir().glob("*.db"), key=lambda item: item.stat().st_mtime, reverse=True):
        item = manifest.get(path.name, {})
        backups.append(
            {
                "filename": path.name,
                "name": item.get("name") or path.stem,
                "created_at": item.get("created_at"),
                "size_kb": round(path.stat().st_size / 1024, 1),
            }
        )
    return backups


def create_backup(name):
    ensure_database_writable()
    clean_name = name.strip() or "Backup"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{_slugify(clean_name)}.db"
    target = backup_dir() / filename

    source = database_path()
    with sqlite3.connect(source) as src_conn:
        with sqlite3.connect(target) as dst_conn:
            src_conn.backup(dst_conn)
    _make_writable(target)

    manifest = _load_manifest()
    manifest[filename] = {
        "name": clean_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_manifest(manifest)
    return filename


def restore_backup(filename):
    source = backup_dir() / filename
    if not source.exists() or source.suffix != ".db":
        raise FileNotFoundError("Fant ikke valgt backup.")

    target = database_path()
    restore_temp = target.with_suffix(".restore-tmp")
    ensure_database_writable()
    db.session.remove()
    db.engine.dispose()
    shutil.copy2(source, restore_temp)
    _make_writable(restore_temp)
    restore_temp.replace(target)
    _make_writable(target)
    db.engine.dispose()


def _delete_round_rows():
    RoundImage.query.delete()
    ScoreStat.query.delete()
    ScoreEntry.query.delete()
    RoundPlayer.query.delete()
    Round.query.delete()


def clear_rounds(reset_connection=True):
    if reset_connection:
        db.session.remove()
        db.engine.dispose()
        ensure_database_writable()
    _delete_round_rows()
    db.session.commit()


def _delete_round_image_files(rounds):
    filenames = [
        image.filename
        for round_obj in rounds
        for image in round_obj.images
        if image.filename
    ]
    upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
    image_root = Path(upload_folder) / "round-images"
    for filename in filenames:
        path = image_root / filename
        try:
            path.unlink()
        except FileNotFoundError:
            continue


def clear_balletour_rounds(reset_connection=True, commit=True):
    from services.balletour import get_balletour_series

    if reset_connection:
        db.session.remove()
        db.engine.dispose()
        ensure_database_writable()

    series = get_balletour_series()
    if not series:
        raise ValueError("Fant ikke BalleTour-serien.")

    rounds = Round.query.filter_by(course_id=series.course_id).all()
    deleted_count = len(rounds)
    try:
        _delete_round_image_files(rounds)
        for round_obj in rounds:
            db.session.delete(round_obj)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
    except Exception:
        db.session.rollback()
        raise
    return deleted_count


def _choose_rating(tee, player):
    gender = player.gender if player and player.gender else "male"
    for rating in tee.ratings:
        if rating.gender == gender:
            return rating
    return tee.ratings[0] if tee.ratings else None


def _weighted_score(par, player_level, rng):
    roll = rng.random()
    if player_level <= 6:
        offsets = [(-1, 0.12), (0, 0.48), (1, 0.28), (2, 0.10), (3, 0.02)]
    elif player_level <= 14:
        offsets = [(-1, 0.05), (0, 0.34), (1, 0.38), (2, 0.18), (3, 0.05)]
    else:
        offsets = [(0, 0.18), (1, 0.36), (2, 0.28), (3, 0.14), (4, 0.04)]

    cumulative = 0
    for offset, probability in offsets:
        cumulative += probability
        if roll <= cumulative:
            return max(1, par + offset)
    return par + 2


def _drive_distance(score, par, rng):
    base = 235 if score <= par else 220
    if par == 5:
        base += 8
    return max(120, min(310, int(rng.gauss(base, 24))))


def _fairway_result(score, par, rng):
    hit_probability = 0.62 if score <= par else 0.42
    if rng.random() < hit_probability:
        return "hit"
    return "left" if rng.random() < 0.5 else "right"


def _green_result(score, par, rng):
    hit_probability = 0.66 if score <= par else 0.38
    if rng.random() < hit_probability:
        return "hit"
    return rng.choice(["left", "right", "short", "long"])


def _balletour_green_result(score, rng):
    if score <= 2:
        hit_probability = 0.86
        bunker_probability = 0.04
    elif score == 3:
        hit_probability = 0.70
        bunker_probability = 0.08
    elif score == 4:
        hit_probability = 0.42
        bunker_probability = 0.16
    else:
        hit_probability = 0.24
        bunker_probability = 0.24

    roll = rng.random()
    if roll < hit_probability:
        status = "hit"
    elif roll < hit_probability + bunker_probability:
        status = "bunker"
    else:
        status = "miss"

    if status == "hit" and rng.random() < 0.12:
        return "hit:pin"

    directions = []
    if rng.random() < 0.68:
        directions.append(rng.choice(["short", "long"]))
    if rng.random() < 0.72:
        directions.append(rng.choice(["left", "right"]))
    if directions:
        return f"{status}:{','.join(directions)}"
    return status


def _putts(score, par, rng):
    if score <= par - 1:
        choices = [(1, 0.40), (2, 0.57), (3, 0.03)]
    elif score <= par:
        choices = [(1, 0.12), (2, 0.78), (3, 0.10)]
    else:
        choices = [(1, 0.05), (2, 0.58), (3, 0.31), (4, 0.06)]
    roll = rng.random()
    cumulative = 0
    for value, probability in choices:
        cumulative += probability
        if roll <= cumulative:
            return value
    return 2


def _last_putt_distance(putts, rng):
    if not putts:
        return None
    if putts == 1:
        return rng.choice([0.5, 1, 2, 3, 4, 5])
    if putts == 2:
        return rng.choice([0.5, 1, 2, 3])
    return rng.choice([0.5, 1, 2])


def _balletour_putts(score, green_result, rng):
    status = green_result.partition(":")[0]
    if score <= 2:
        return 1 if rng.random() < 0.45 else 2
    if status == "hit":
        choices = [(1, 0.10), (2, 0.80), (3, 0.10)]
    elif status == "bunker":
        choices = [(1, 0.12), (2, 0.60), (3, 0.25), (4, 0.03)]
    else:
        choices = [(1, 0.16), (2, 0.66), (3, 0.16), (4, 0.02)]

    roll = rng.random()
    cumulative = 0
    for value, probability in choices:
        cumulative += probability
        if roll <= cumulative:
            return value
    return 2


def _balletour_score(player, hole_number, rng):
    hcp = player.default_hcp or 12
    skill_adjustment = max(-0.12, min(0.14, (hcp - 12) / 90))
    hole_adjustment = ((hole_number % 3) - 1) * 0.025
    roll = rng.random() + skill_adjustment + hole_adjustment
    if roll < 0.06:
        return 2
    if roll < 0.56:
        return 3
    if roll < 0.86:
        return 4
    if roll < 0.97:
        return 5
    return 6


def _choose_balletour_club(clubs_by_name, hole_number, player, rng):
    club_names_by_hole = {
        1: ["Jern 8", "Jern 9", "Pitching wedge"],
        2: ["Jern 7", "Jern 8", "Jern 9"],
        3: ["Jern 6", "Jern 7", "Jern 8"],
        4: ["Jern 9", "Pitching wedge", "Sand wedge"],
        5: ["Jern 7", "Jern 8", "Jern 6"],
        6: ["Jern 6", "Jern 7", "Jern 8"],
        7: ["Pitching wedge", "Jern 9", "Sand wedge"],
        8: ["Jern 8", "Jern 9", "Jern 7"],
        9: ["Jern 7", "Jern 8", "Jern 6"],
    }
    candidates = [
        clubs_by_name[name]
        for name in club_names_by_hole.get(hole_number, ["Jern 8", "Jern 9"])
        if name in clubs_by_name
    ]
    if not candidates:
        return None
    index = (player.id + hole_number + rng.randint(0, len(candidates) - 1)) % len(candidates)
    return candidates[index]


def _create_test_rounds_for_user(user, courses, rng, now, count):
    player = user.player

    for index in range(count):
        course = rng.choice(courses)
        tees = list(course.tees)
        if not tees:
            continue

        tee = rng.choice(tees)
        rating = _choose_rating(tee, player)
        handicap = max(-2.0, round(player.default_hcp + rng.uniform(-1.4, 1.8), 1))
        started_at = now - timedelta(days=(count - index) * rng.randint(2, 7), hours=rng.randint(7, 16))
        round_obj = Round(
            course_id=course.id,
            status="finished",
            started_at=started_at,
            finished_at=started_at + timedelta(hours=4, minutes=rng.randint(0, 45)),
            stats_user_id=user.id,
        )
        db.session.add(round_obj)
        db.session.flush()

        round_player = RoundPlayer(
            round_id=round_obj.id,
            player_id=player.id,
            selected_tee_id=tee.id,
            player_name_snapshot=player.name,
            hcp_for_round=handicap,
        )
        db.session.add(round_player)
        db.session.flush()

        player_level = handicap
        if rating:
            player_level += max(-3, min(3, (rating.slope - 113) / 10))

        for hole in course.holes:
            score = _weighted_score(hole.par, player_level, rng)
            entry = ScoreEntry(
                round_id=round_obj.id,
                round_player_id=round_player.id,
                hole_number=hole.hole_number,
                strokes=score,
            )
            db.session.add(entry)
            db.session.flush()

            putts = _putts(score, hole.par, rng)
            stat = ScoreStat(
                score_entry_id=entry.id,
                putts=putts,
                last_putt_distance_m=_last_putt_distance(putts, rng),
            )
            if hole.par == 3:
                stat.fairway_result = _green_result(score, hole.par, rng)
            elif hole.par in (4, 5):
                stat.drive_distance_m = _drive_distance(score, hole.par, rng)
                stat.fairway_result = _fairway_result(score, hole.par, rng)
            db.session.add(stat)


def generate_test_rounds(user_id=None, count=50):
    db.session.remove()
    db.engine.dispose()
    ensure_database_writable()
    try:
        users = (
            User.query.filter(User.username.in_(["Kristian", "Erik"]))
            .order_by(User.username.asc())
            .all()
        )
        if not users:
            if user_id is None:
                raise ValueError("Fant ingen testbrukere.")
            user = User.query.get(user_id)
            if not user:
                raise ValueError("Fant ikke bruker.")
            users = [user]

        courses = Course.query.order_by(Course.name.asc()).all()
        if not courses:
            raise ValueError("Du må ha minst én bane før testdata kan lages.")

        _delete_round_rows()

        rng = random.Random()
        now = datetime.utcnow()

        for user in users:
            _create_test_rounds_for_user(user, courses, rng, now, count)

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def generate_balletour_test_rounds(count=20):
    from services.balletour import get_balletour_memberships, get_balletour_series

    db.session.remove()
    db.engine.dispose()
    ensure_database_writable()
    try:
        series = get_balletour_series()
        if not series or not series.course:
            raise ValueError("Fant ikke BalleTour-serien.")

        memberships = get_balletour_memberships()
        players = [membership.player for membership in memberships]
        if not players:
            raise ValueError("Fant ingen BalleTour-spillere.")

        tees = list(series.course.tees)
        if not tees:
            raise ValueError("BalleTour-banen har ingen tees.")
        tee = tees[0]

        clubs = Club.query.order_by(Club.sort_order.asc(), Club.name.asc()).all()
        clubs_by_name = {club.name: club for club in clubs}
        users_by_player_id = {
            user.player_id: user
            for user in User.query.filter(User.player_id.in_([player.id for player in players])).all()
        }

        clear_balletour_rounds(reset_connection=False, commit=False)

        rng = random.Random()
        now = datetime.utcnow()
        holes = list(series.course.holes)

        for index in range(count):
            started_at = now - timedelta(days=(count - index) * 2, hours=rng.randint(8, 16))
            host_player = players[index % len(players)]
            host_user = users_by_player_id.get(host_player.id)
            round_obj = Round(
                course_id=series.course_id,
                status="finished",
                started_at=started_at,
                finished_at=started_at + timedelta(hours=1, minutes=rng.randint(15, 45)),
                stats_user_id=host_user.id if host_user else None,
                legacy_source="balletour_testdata",
            )
            db.session.add(round_obj)
            db.session.flush()

            for player in players:
                round_player = RoundPlayer(
                    round_id=round_obj.id,
                    player_id=player.id,
                    selected_tee_id=tee.id,
                    player_name_snapshot=player.name,
                    hcp_for_round=player.default_hcp,
                )
                db.session.add(round_player)
                db.session.flush()

                for hole in holes:
                    score = _balletour_score(player, hole.hole_number, rng)
                    club = _choose_balletour_club(clubs_by_name, hole.hole_number, player, rng)
                    entry = ScoreEntry(
                        round_id=round_obj.id,
                        round_player_id=round_player.id,
                        hole_number=hole.hole_number,
                        strokes=score,
                        tee_club_id=club.id if club else None,
                    )
                    db.session.add(entry)
                    db.session.flush()

                    green_result = _balletour_green_result(score, rng)
                    putts = _balletour_putts(score, green_result, rng)
                    db.session.add(
                        ScoreStat(
                            score_entry_id=entry.id,
                            fairway_result=green_result,
                            putts=putts,
                            last_putt_distance_m=_last_putt_distance(putts, rng),
                        )
                    )

        db.session.commit()
        return count
    except Exception:
        db.session.rollback()
        raise
