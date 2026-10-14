"""Explicit tour identity, with a conservative compatibility path for legacy rows."""
from sqlalchemy import and_, or_, false
from extensions import db
from models import Round
from services.balletour import BALLETOUR_SERIES_NAME, get_balletour_series


def series_round_condition(series):
    if series is None:
        return false()
    if series.name.lower() != BALLETOUR_SERIES_NAME.lower():
        # Other legacy series still calculate over their configured course.
        return Round.course_id == series.course_id
    return or_(
        and_(Round.series_id.isnot(None), Round.series_id == series.id),
        and_(Round.tour_context_set.is_(False), Round.course_id == series.course_id),
    )


def is_series_round(round_obj, series):
    if not series:
        return False
    if series.name.lower() != BALLETOUR_SERIES_NAME.lower():
        return round_obj.course_id == series.course_id
    if getattr(round_obj, "tour_context_set", False):
        return round_obj.series_id == series.id
    return round_obj.course_id == series.course_id


def is_balletour_round(round_obj):
    return is_series_round(round_obj, get_balletour_series())


def exclude_balletour(query):
    return query.filter(~series_round_condition(get_balletour_series()))


def migrate_legacy_tour_context():
    """Run after schema preflight; preserve the former course-based classification.

    No scores/archives are rewritten. A marked private round remains private on
    every later startup, including after tour configuration changes.
    """
    series = get_balletour_series()
    if series is not None:
        Round.query.filter(Round.tour_context_set.is_(False), Round.course_id == series.course_id).update(
            {Round.series_id: series.id, Round.tour_context_set: True}, synchronize_session=False
        )
    Round.query.filter(Round.tour_context_set.is_(False)).update(
        {Round.tour_context_set: True}, synchronize_session=False
    )
    db.session.commit()
