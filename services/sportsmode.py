"""Personal Sportsmodus read models. No upstream calls or shared/private data mixing."""
import json
from flask import g, request, url_for
from sqlalchemy import or_
from extensions import db
from models import Round, RoundPlayer
from services.balletour import get_balletour_series, is_balletour_player
from services.play_formats import MATCHPLAY, matchplay_status_label, matchplay_status_value, play_format_label
from services.round_length import round_holes, round_length_label
from services.time import format_server_datetime
from services.tour_context import is_balletour_round, series_round_condition
from services.trackman_rounds import row_summary, user_rounds


def product_access(user):
    if not user:
        return {"shanklife": False, "tour": False}
    cache = getattr(g, "sports_access", None)
    if cache is not None:
        return cache
    rows = db.session.execute(db.text("""
        SELECT app_registry.slug FROM app_registry
        JOIN user_app_access ON user_app_access.app_id = app_registry.id
        WHERE user_app_access.user_id = :user_id AND user_app_access.has_access = 1
    """), {"user_id": user.id}).scalars().all()
    slug = "shanklife-app" if request.host.split(":")[0] == "app.shanklife.no" else "shanklife-pro"
    access = {"shanklife": slug in rows, "tour": "balletour" in rows and is_balletour_player(user)}
    g.sports_access = access
    return access


def personal_round_players(user):
    access = product_access(user)
    condition = series_round_condition(get_balletour_series())
    filters = []
    if access["shanklife"]:
        filters.append(~condition)
    if access["tour"]:
        filters.append(condition)
    if not filters or not user.player_id:
        return []
    return (RoundPlayer.query.join(Round).filter(
        RoundPlayer.player_id == user.player_id, or_(*filters)
    ).order_by(Round.started_at.desc(), Round.id.desc()).all())


def local_round_item(rp):
    r = rp.round
    holes = round_holes(r)
    par_by_hole = {h.hole_number: h.par for h in holes}
    entries = [e for e in rp.score_entries if e.hole_number in par_by_hole]
    scored = [e for e in entries if e.strokes is not None]
    total = sum(e.strokes for e in scored) if scored else None
    full = len(scored) == len(holes) and r.status == "finished"
    match = r.play_format == MATCHPLAY
    result = matchplay_status_label(matchplay_status_value([e.hole_result for e in entries])) if match else str(total) if total is not None else "—"
    diff = sum(e.strokes - par_by_hole[e.hole_number] for e in scored) if scored and not match else None
    tour = is_balletour_round(r)
    if r.status == "ongoing":
        target = url_for("rounds.continue_round", round_id=r.id)
    elif tour:
        target = url_for("balletour.round_detail", round_id=r.id)
    else:
        target = url_for("rounds.round_score", round_id=r.id)
    return {
        "id": f"round-{r.id}", "round_id": r.id, "source": "balletour" if tour else "shanklife",
        "course": r.course.name, "environment": "outdoor", "status": r.status,
        "complete": full, "played_holes": len(scored), "holes": len(holes),
        "length_label": round_length_label(r), "tee": rp.selected_tee.name if rp.selected_tee else "—",
        "started_at": r.started_at.isoformat() if r.started_at else "",
        "date_display": format_server_datetime(r.started_at), "format": play_format_label(r.play_format),
        "score": result, "to_par": "E" if diff == 0 else f"{diff:+d}" if diff is not None else "",
        "total": total, "par": sum(par_by_hole.values()), "url": target,
        "is_tour": tour, "is_matchplay": match, "private": False,
        "garmin_synced": r.garmin_sync is not None,
    }


def personal_round_items(user, environment="all", source="all"):
    access = product_access(user)
    rows = [local_round_item(rp) for rp in personal_round_players(user)] if environment != "simulator" else []
    if access["shanklife"] and source in ("all", "trackman"):
        for r in user_rounds(user.id, environment):
            summary = row_summary(r)
            rows.append({
                "id": f"trackman-{r.id}", "round_id": r.id, "source": "trackman", "private": True,
                "course": r.course_name, "environment": r.environment,
                "status": "finished" if r.completed else "ongoing", "complete": bool(r.completed),
                "played_holes": summary["holes"], "holes": r.holes_to_play,
                "length_label": f"{summary['holes']} av {r.holes_to_play or 'ukjent'} hull",
                "tee": summary.get("tee_name") or "—", "started_at": r.started_at.isoformat() if r.started_at else "",
                "date_display": format_server_datetime(r.started_at), "format": "Lagspill" if summary["team"] else "Slagspill",
                "score": str(summary["total"]) if summary["total"] is not None else "—",
                "to_par": "E" if summary["to_par"] == 0 else f"{summary['to_par']:+g}" if summary["to_par"] is not None else "",
                "total": summary["total"], "par": json.loads(r.summary).get("par"), "url": url_for("trackman.round_detail", round_id=r.id),
                "is_tour": False, "is_matchplay": False, "garmin_synced": False,
            })
    if source != "all":
        rows = [row for row in rows if row["source"] == source]
    return sorted(rows, key=lambda row: (row["started_at"], row["id"]), reverse=True)


def dashboard_payload(user):
    access = product_access(user)
    rows = personal_round_items(user)
    active = [r for r in rows if r["status"] == "ongoing" and r["source"] != "trackman"]
    progress = None
    if access["tour"]:
        from routes.balletour import _balletour_leaderboard_rows
        from services.balletour import get_balletour_memberships
        from services.tee_filters import tee_ids_for_key
        series = get_balletour_series()
        board = _balletour_leaderboard_rows(series, get_balletour_memberships(), tee_ids_for_key(series.course, "gul"))
        own = next((r for r in board if r["player"].id == user.player_id), None)
        if own:
            progress = {"name": "BalleTour", "course": series.course.name, "tee": "Gul",
                        "rounds": own["rounds_played"], "required": series.min_qualifying_rounds,
                        "qualified": own["qualified"], "rank": own["rank"],
                        "total_vs_par": own["total_vs_par_display"]}
    return {"name": user.player.name if user.player else user.username,
            "hcp": user.player.default_hcp if user.player else None, "access": access,
            "active_rounds": active, "recent_rounds": rows[:5], "round_count": len(rows), "tour": progress}
