from sqlalchemy import func

from models import Player, Series, SeriesPlayer

BALLETOUR_SERIES_NAME = "Balletour"
BALLETOUR_MENU_LABEL = "BalleTour2026"


def get_balletour_series():
    return Series.query.filter(
        func.lower(Series.name) == BALLETOUR_SERIES_NAME.lower()
    ).first()


def get_balletour_memberships():
    series = get_balletour_series()
    if not series:
        return []

    return (
        SeriesPlayer.query.filter_by(series_id=series.id)
        .join(Player)
        .order_by(SeriesPlayer.display_order.asc(), Player.name.asc())
        .all()
    )


def get_balletour_players():
    return [membership.player for membership in get_balletour_memberships()]


def is_balletour_player(user):
    if not user or not user.player_id:
        return False

    series = get_balletour_series()
    if not series:
        return False

    return (
        SeriesPlayer.query.filter_by(
            series_id=series.id,
            player_id=user.player_id,
        ).first()
        is not None
    )
