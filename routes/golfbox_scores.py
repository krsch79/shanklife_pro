from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from extensions import db
from models import GolfBoxScoreSubmission, Round, RoundPlayer
from routes.auth import login_required
from services.balletour import get_balletour_series, is_balletour_player
from services.golfbox import golfbox_connection_summary
from services.golfbox_scores import round_player_score_payload, score_course_suggestions, search_marker, submit_score
from services.play_formats import is_matchplay_round
from services.time import server_now


golfbox_scores_bp = Blueprint("golfbox_scores", __name__)


def _round_player_for_current_user(round_obj):
    player_id = g.current_user.player_id
    return next((rp for rp in round_obj.round_players if rp.player_id == player_id), None)


def _is_balletour_round(round_obj):
    series = get_balletour_series()
    return bool(series and round_obj.course_id == series.course_id)


def _return_endpoint(round_obj):
    return "rounds.balletour_round_scorecard" if _is_balletour_round(round_obj) else "rounds.round_score"


def _get_or_create_submission(round_player):
    if round_player.golfbox_submission:
        return round_player.golfbox_submission
    submission = GolfBoxScoreSubmission(
        round_player_id=round_player.id,
        submitted_by_user_id=g.current_user.id,
        status="draft",
    )
    db.session.add(submission)
    db.session.flush()
    return submission


@golfbox_scores_bp.route("/rounds/<int:round_id>/golfbox", methods=["GET", "POST"])
@login_required
def prepare(round_id):
    round_obj = Round.query.get_or_404(round_id)
    round_player = _round_player_for_current_user(round_obj)
    if not round_player:
        flash("Du kan bare sende din egen score til GolfBox.", "error")
        return redirect(url_for(_return_endpoint(round_obj), round_id=round_obj.id))
    if round_obj.status != "finished":
        flash("Runden må være fullført før den kan sendes til GolfBox.", "error")
        return redirect(url_for(_return_endpoint(round_obj), round_id=round_obj.id))
    if is_matchplay_round(round_obj):
        flash("Matchplay-runder kan ikke sendes til GolfBox som slagspillscore.", "error")
        return redirect(url_for(_return_endpoint(round_obj), round_id=round_obj.id))

    payload = round_player_score_payload(round_player)
    submission = _get_or_create_submission(round_player)
    marker_results = []
    selected_marker = None
    course_suggestions = []
    course_lookup_error = None
    try:
        course_suggestions = score_course_suggestions(g.current_user, round_player) if payload["complete"] else []
    except Exception as exc:
        course_lookup_error = str(exc)

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        if action == "cancel":
            return redirect(url_for(_return_endpoint(round_obj), round_id=round_obj.id))
        if action == "search_marker":
            marker_query = request.form.get("marker_query", "").strip()
            try:
                marker_results = search_marker(g.current_user, marker_query)
            except Exception as exc:
                flash(str(exc), "error")
            if len(marker_results) == 1:
                selected_marker = marker_results[0]
        elif action == "submit":
            marker_guid = request.form.get("marker_guid", "").strip()
            marker_name = request.form.get("marker_name", "").strip()
            marker_club = request.form.get("marker_club", "").strip()
            course_selection = {
                "club_guid": request.form.get("golfbox_club_guid", "").strip(),
                "course_guid": request.form.get("golfbox_course_guid", "").strip(),
                "tee_guid": request.form.get("golfbox_tee_guid", "").strip(),
            }
            try:
                if not all(course_selection.values()):
                    raise ValueError("Velg og bekreft GolfBox-klubb, bane og tee før innsending.")
                result = submit_score(round_player, g.current_user, marker_guid, marker_name, marker_club, course_selection=course_selection)
            except Exception as exc:
                submission.status = "error"
                submission.message = str(exc)
                submission.response_excerpt = None
                db.session.commit()
                flash(str(exc), "error")
            else:
                submission.status = result["status"]
                submission.marker_guid = result["marker_guid"]
                submission.marker_name = result["marker_name"]
                submission.marker_club = result["marker_club"]
                submission.golfbox_course_name = result["course_name"]
                submission.golfbox_tee_name = result["tee_name"]
                submission.message = result["message"]
                submission.response_excerpt = result["response_excerpt"]
                submission.submitted_at = server_now() if result["status"] == "submitted" else None
                db.session.commit()
                flash(result["message"], "success" if result["status"] == "submitted" else "error")
                return redirect(url_for(_return_endpoint(round_obj), round_id=round_obj.id))
        else:
            flash("Ukjent GolfBox-handling.", "error")

    db.session.commit()
    return render_template(
        "golfbox_score_submit.html",
        round=round_obj,
        round_player=round_player,
        payload=payload,
        submission=submission,
        marker_results=marker_results,
        selected_marker=selected_marker,
        course_suggestions=course_suggestions,
        course_lookup_error=course_lookup_error,
        selected_course_key=request.form.get("golfbox_course_key", ""),
        golfbox_connection=golfbox_connection_summary(g.current_user),
        is_balletour_context=_is_balletour_round(round_obj),
        current_user_is_balletour_player=is_balletour_player(g.current_user),
    )
