import random
import sqlite3
from contextlib import contextmanager, nullcontext
from datetime import timedelta
from pathlib import Path

from flask import g, session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from extensions import db
from models import Club, Round, RoundImage, RoundPlayer, ScoreEntry, ScoreStat, Series, User
from services.admin_tools import (
    _balletour_green_result,
    _balletour_putts,
    _balletour_score,
    _choose_balletour_club,
    _last_putt_distance,
    database_path,
)
from services.balletour import BALLETOUR_SERIES_NAME
from services.time import server_now


TEST_DATABASE_VIEW_SESSION_KEY = "balletour_database_view"
TEST_DATABASE_VIEW = "test"
PROD_DATABASE_VIEW = "prod"
TEST_DATABASE_ROUNDS_PER_PLAYER = 25


def test_database_path():
    return database_path().with_name("shanklife_pro_balletour_test.db")


def test_database_exists():
    return test_database_path().exists()


def current_balletour_database_view():
    user = g.get("current_user")
    if not user or not user.is_admin:
        return PROD_DATABASE_VIEW
    if session.get(TEST_DATABASE_VIEW_SESSION_KEY) == TEST_DATABASE_VIEW and test_database_exists():
        return TEST_DATABASE_VIEW
    return PROD_DATABASE_VIEW


def set_balletour_database_view(value):
    if value == TEST_DATABASE_VIEW and test_database_exists():
        session[TEST_DATABASE_VIEW_SESSION_KEY] = TEST_DATABASE_VIEW
    else:
        session[TEST_DATABASE_VIEW_SESSION_KEY] = PROD_DATABASE_VIEW


def _test_engine():
    return create_engine(f"sqlite:///{test_database_path()}")


@contextmanager
def use_balletour_test_database():
    engine = _test_engine()
    test_session = scoped_session(sessionmaker(bind=engine))
    original_session = db.session
    db.session = test_session
    try:
        yield
    finally:
        test_session.remove()
        engine.dispose()
        db.session = original_session


def balletour_data_context():
    if current_balletour_database_view() == TEST_DATABASE_VIEW:
        return use_balletour_test_database()
    return nullcontext()


def _copy_prod_to_test_database():
    source = database_path()
    target = test_database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    with sqlite3.connect(source) as src_conn:
        with sqlite3.connect(target) as dst_conn:
            src_conn.backup(dst_conn)
    target.chmod(target.stat().st_mode | 0o600)


def _clear_rounds(test_session):
    test_session.query(RoundImage).delete()
    test_session.query(ScoreStat).delete()
    test_session.query(ScoreEntry).delete()
    test_session.query(RoundPlayer).delete()
    test_session.query(Round).delete()


def reset_balletour_test_database(rounds_per_player=TEST_DATABASE_ROUNDS_PER_PLAYER):
    _copy_prod_to_test_database()
    engine = _test_engine()
    TestSession = sessionmaker(bind=engine)
    test_session = TestSession()
    try:
        _clear_rounds(test_session)

        series = test_session.query(Series).filter_by(name=BALLETOUR_SERIES_NAME).first()
        if not series or not series.course:
            raise ValueError("Fant ikke BalleTour-serien i testdatabasen.")

        players = [membership.player for membership in series.players]
        if not players:
            raise ValueError("Fant ingen BalleTour-spillere i testdatabasen.")

        tees = list(series.course.tees)
        if not tees:
            raise ValueError("BalleTour-banen har ingen tees i testdatabasen.")
        yellow_tee = next((tee for tee in tees if "gul" in tee.name.lower()), None)
        tee = yellow_tee or tees[0]

        clubs = test_session.query(Club).order_by(Club.sort_order.asc(), Club.name.asc()).all()
        clubs_by_name = {club.name: club for club in clubs}
        users_by_player_id = {
            user.player_id: user
            for user in test_session.query(User).filter(User.player_id.in_([player.id for player in players])).all()
        }

        rng = random.Random()
        now = server_now()
        holes = list(series.course.holes)

        for index in range(rounds_per_player):
            started_at = now - timedelta(days=(rounds_per_player - index) * 2, hours=rng.randint(8, 16))
            host_player = players[index % len(players)]
            host_user = users_by_player_id.get(host_player.id)
            round_obj = Round(
                course_id=series.course_id,
                status="finished",
                started_at=started_at,
                finished_at=started_at + timedelta(hours=1, minutes=rng.randint(15, 45)),
                stats_user_id=host_user.id if host_user else None,
                legacy_source="balletour_test_database",
            )
            test_session.add(round_obj)
            test_session.flush()

            for player in players:
                round_player = RoundPlayer(
                    round_id=round_obj.id,
                    player_id=player.id,
                    selected_tee_id=tee.id,
                    player_name_snapshot=player.name,
                    hcp_for_round=player.default_hcp,
                )
                test_session.add(round_player)
                test_session.flush()

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
                    test_session.add(entry)
                    test_session.flush()

                    green_result = _balletour_green_result(score, rng)
                    putts = _balletour_putts(score, green_result, rng)
                    test_session.add(
                        ScoreStat(
                            score_entry_id=entry.id,
                            fairway_result=green_result,
                            putts=putts,
                            last_putt_distance_m=_last_putt_distance(putts, rng),
                        )
                    )

        test_session.commit()
        return {
            "rounds": rounds_per_player,
            "players": len(players),
            "path": str(test_database_path()),
        }
    except Exception:
        test_session.rollback()
        raise
    finally:
        test_session.close()
        engine.dispose()


def delete_balletour_test_database():
    path = test_database_path()
    if path.exists():
        path.unlink()
        return True
    return False
