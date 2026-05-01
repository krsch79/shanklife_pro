from collections import defaultdict

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func

from models import (
    Club,
    CourseHole,
    CourseTee,
    CourseTeeLength,
    Player,
    PlayerHoleDefaultClub,
    Round,
    RoundImage,
    RoundPlayer,
    ScoreEntry,
    Series,
    SeriesPlayer,
)
from routes.auth import login_required
from extensions import db
from services.balletour import BALLETOUR_SERIES_NAME

series_bp = Blueprint("series", __name__, url_prefix="/series")


def _series_or_404(series_id):
    series = Series.query.get_or_404(series_id)
    if not series.course:
        abort(404)
    return series


def _score_vs_par(total, par):
    diff = total - par
    if diff == 0:
        return "E"
    return f"+{diff}" if diff > 0 else str(diff)


def _completed_round_players(series, tee_name=None):
    rows = (
        RoundPlayer.query.join(Round)
        .filter(Round.course_id == series.course_id)
        .filter(Round.status == "finished")
        .all()
    )
    if tee_name:
        rows = [
            rp for rp in rows
            if rp.selected_tee and rp.selected_tee.name.lower() == tee_name.lower()
        ]
    return rows


def _round_player_total(round_player, hole_count):
    entries = [entry for entry in round_player.score_entries if entry.strokes is not None]
    if len(entries) != hole_count:
        return None
    return sum(entry.strokes for entry in entries)


def _leaderboard_rows(series, tee_name=None):
    course_par = sum(hole.par for hole in series.course.holes)
    by_player = defaultdict(list)

    for round_player in _completed_round_players(series, tee_name):
        total = _round_player_total(round_player, series.course.hole_count)
        if total is not None:
            by_player[round_player.player_id].append(total)

    players = {
        player.id: player
        for player in Player.query.filter(Player.id.in_(by_player.keys())).all()
    } if by_player else {}

    rows = []
    for player_id, totals in by_player.items():
        total_strokes = sum(totals)
        rounds_played = len(totals)
        total_par = rounds_played * course_par
        rows.append({
            "player": players[player_id],
            "rounds_played": rounds_played,
            "total_strokes": total_strokes,
            "total_vs_par": total_strokes - total_par,
            "avg_round": round(total_strokes / rounds_played, 2),
            "best_round": min(totals),
            "qualified": rounds_played >= series.min_qualifying_rounds,
        })

    rows.sort(key=lambda row: (row["total_vs_par"], row["avg_round"], row["player"].name))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
        row["total_vs_par_display"] = _score_vs_par(
            row["total_strokes"],
            row["rounds_played"] * course_par,
        )
    return rows


@series_bp.route("/")
@login_required
def index():
    series_rows = (
        Series.query.filter(func.lower(Series.name) != BALLETOUR_SERIES_NAME.lower())
        .order_by(Series.name.asc())
        .all()
    )
    if len(series_rows) == 1:
        return overview(series_rows[0].id)
    return render_template("series_index.html", series_rows=series_rows)


@series_bp.route("/<int:series_id>")
@login_required
def overview(series_id):
    series = _series_or_404(series_id)
    if series.name.lower() == BALLETOUR_SERIES_NAME.lower():
        return redirect(url_for("balletour.index"))

    tee_name = request.args.get("tee", "").strip() or None
    tees = CourseTee.query.filter_by(course_id=series.course_id).order_by(CourseTee.display_order).all()
    leaderboard_rows = _leaderboard_rows(series, tee_name)
    round_count = Round.query.filter_by(course_id=series.course_id).count()
    image_count = (
        RoundImage.query.join(Round)
        .filter(Round.course_id == series.course_id)
        .count()
    )
    return render_template(
        "series_overview.html",
        series=series,
        tees=tees,
        selected_tee=tee_name,
        leaderboard_rows=leaderboard_rows,
        round_count=round_count,
        image_count=image_count,
    )


@series_bp.route("/<int:series_id>/players")
@login_required
def players(series_id):
    series = _series_or_404(series_id)
    memberships = (
        SeriesPlayer.query.filter_by(series_id=series.id)
        .join(Player)
        .order_by(SeriesPlayer.display_order.asc(), Player.name.asc())
        .all()
    )
    return render_template("series_players.html", series=series, memberships=memberships)


@series_bp.route("/<int:series_id>/players/<int:player_id>")
@login_required
def player_profile(series_id, player_id):
    series = _series_or_404(series_id)
    player = Player.query.get_or_404(player_id)
    round_players = (
        RoundPlayer.query.join(Round)
        .filter(Round.course_id == series.course_id)
        .filter(RoundPlayer.player_id == player.id)
        .order_by(Round.started_at.desc())
        .all()
    )

    course_par = sum(hole.par for hole in series.course.holes)
    completed = []
    for rp in round_players:
        total = _round_player_total(rp, series.course.hole_count)
        if total is not None:
            completed.append({"round_player": rp, "total": total})

    # Keep the calculation simple and explicit for SQLite compatibility.
    entries = (
        ScoreEntry.query.join(RoundPlayer)
        .join(Round)
        .join(
            CourseHole,
            (CourseHole.course_id == Round.course_id)
            & (CourseHole.hole_number == ScoreEntry.hole_number),
        )
        .filter(Round.course_id == series.course_id)
        .filter(RoundPlayer.player_id == player.id)
        .filter(ScoreEntry.strokes.isnot(None))
        .with_entities(ScoreEntry.strokes, CourseHole.par)
        .all()
    )
    birdies = sum(1 for strokes, par in entries if strokes == par - 1)
    pars = sum(1 for strokes, par in entries if strokes == par)
    bogeys = sum(1 for strokes, par in entries if strokes == par + 1)

    images = (
        RoundImage.query.join(Round)
        .filter(Round.course_id == series.course_id)
        .filter(RoundImage.tagged_player_id == player.id)
        .order_by(RoundImage.uploaded_at.desc())
        .all()
    )

    summary = {
        "round_count": len(completed),
        "avg_round": round(sum(row["total"] for row in completed) / len(completed), 2) if completed else None,
        "best_round": min((row["total"] for row in completed), default=None),
        "worst_round": max((row["total"] for row in completed), default=None),
        "course_par": course_par,
        "birdies": birdies,
        "pars": pars,
        "bogeys": bogeys,
    }
    return render_template(
        "series_player_profile.html",
        series=series,
        player=player,
        completed=completed,
        summary=summary,
        images=images,
    )


@series_bp.route("/<int:series_id>/club-stats")
@login_required
def club_stats(series_id):
    series = _series_or_404(series_id)
    tee_name = request.args.get("tee", "").strip() or None
    selected_player_id_raw = request.args.get("player_id", "").strip()
    tees = CourseTee.query.filter_by(course_id=series.course_id).order_by(CourseTee.display_order).all()
    tee_length_rows = CourseTeeLength.query.join(CourseTee).filter(
        CourseTee.course_id == series.course_id
    )
    if tee_name:
        tee_length_rows = tee_length_rows.filter(func.lower(CourseTee.name) == tee_name.lower())
    tee_lengths_by_hole = defaultdict(list)
    for length in tee_length_rows.order_by(CourseTee.display_order.asc(), CourseTeeLength.hole_number.asc()).all():
        tee_lengths_by_hole[length.hole_number].append({
            "tee_name": length.tee.name,
            "length_meters": length.length_meters,
        })

    rows = (
        ScoreEntry.query.join(RoundPlayer)
        .join(Round)
        .join(Club, ScoreEntry.tee_club_id == Club.id)
        .filter(Round.course_id == series.course_id)
        .filter(ScoreEntry.strokes.isnot(None))
        .with_entities(
            RoundPlayer.player_id,
            ScoreEntry.hole_number,
            Club.id,
            Club.name,
            Club.sort_order,
            func.count(ScoreEntry.id),
            func.avg(ScoreEntry.strokes),
        )
        .group_by(RoundPlayer.player_id, ScoreEntry.hole_number, Club.id, Club.name, Club.sort_order)
        .order_by(RoundPlayer.player_id, ScoreEntry.hole_number, Club.sort_order)
        .all()
    )

    if tee_name:
        tee_ids = [tee.id for tee in tees if tee.name.lower() == tee_name.lower()]
        rows = (
            ScoreEntry.query.join(RoundPlayer)
            .join(Round)
            .join(Club, ScoreEntry.tee_club_id == Club.id)
            .filter(Round.course_id == series.course_id)
            .filter(RoundPlayer.selected_tee_id.in_(tee_ids))
            .filter(ScoreEntry.strokes.isnot(None))
            .with_entities(
                RoundPlayer.player_id,
                ScoreEntry.hole_number,
                Club.id,
                Club.name,
                Club.sort_order,
                func.count(ScoreEntry.id),
                func.avg(ScoreEntry.strokes),
            )
            .group_by(RoundPlayer.player_id, ScoreEntry.hole_number, Club.id, Club.name, Club.sort_order)
            .order_by(RoundPlayer.player_id, ScoreEntry.hole_number, Club.sort_order)
            .all()
        )

    memberships = (
        SeriesPlayer.query.filter_by(series_id=series.id)
        .join(Player)
        .order_by(SeriesPlayer.display_order.asc(), Player.name.asc())
        .all()
    )
    players = [membership.player for membership in memberships]
    if not players:
        player_ids = sorted({row[0] for row in rows})
        players = (
            Player.query.filter(Player.id.in_(player_ids)).order_by(Player.name.asc()).all()
            if player_ids else []
        )

    player_by_id = {player.id: player for player in players}
    selected_player = None
    if selected_player_id_raw:
        try:
            selected_player_id = int(selected_player_id_raw)
        except ValueError:
            selected_player_id = None
        selected_player = player_by_id.get(selected_player_id)

    if not selected_player and g.get("current_user"):
        selected_player = player_by_id.get(g.current_user.player_id)

    if not selected_player and players:
        selected_player = players[0]

    stats_by_player_hole_club = {}
    used_club_ids = set()
    for player_id, hole_number, club_id, club_name, sort_order, shot_count, avg_strokes in rows:
        if selected_player and player_id != selected_player.id:
            continue
        used_club_ids.add(club_id)
        stats_by_player_hole_club[(player_id, hole_number, club_id)] = {
            "shot_count": shot_count,
            "avg_strokes": round(avg_strokes, 2),
        }

    clubs = (
        Club.query.filter(Club.id.in_(used_club_ids))
        .order_by(Club.sort_order.asc(), Club.name.asc())
        .all()
        if used_club_ids else []
    )
    all_clubs = Club.query.order_by(Club.sort_order.asc(), Club.name.asc()).all()
    default_clubs = {}
    if selected_player:
        default_rows = PlayerHoleDefaultClub.query.filter_by(
            player_id=selected_player.id,
            course_id=series.course_id,
        ).all()
        default_clubs = {row.hole_number: row.club_id for row in default_rows}

    player_tables = []
    for player in ([selected_player] if selected_player else []):
        hole_rows = []
        for hole in series.course.holes:
            row_cells = []
            averages = []
            for club in clubs:
                cell = stats_by_player_hole_club.get((player.id, hole.hole_number, club.id))
                if cell:
                    averages.append(cell["avg_strokes"])
                row_cells.append({
                    "club_id": club.id,
                    "avg_strokes": cell["avg_strokes"] if cell else None,
                    "shot_count": cell["shot_count"] if cell else 0,
                    "class_name": "",
                })

            best_avg = min(averages) if averages else None
            worst_avg = max(averages) if averages else None
            for cell in row_cells:
                if cell["avg_strokes"] is None or best_avg == worst_avg:
                    continue
                if cell["avg_strokes"] == best_avg:
                    cell["class_name"] = "club-stat-best"
                elif cell["avg_strokes"] == worst_avg:
                    cell["class_name"] = "club-stat-worst"

            hole_rows.append({
                "hole_number": hole.hole_number,
                "par": hole.par,
                "lengths": tee_lengths_by_hole.get(hole.hole_number, []),
                "cells": row_cells,
            })

        player_tables.append({
            "player": player,
            "hole_rows": hole_rows,
        })

    return render_template(
        "series_club_stats.html",
        series=series,
        tees=tees,
        selected_tee=tee_name,
        clubs=clubs,
        all_clubs=all_clubs,
        players=players,
        selected_player=selected_player,
        default_clubs=default_clubs,
        show_default_club_editor=request.args.get("edit_defaults") == "1",
        player_tables=player_tables,
    )


@series_bp.route("/<int:series_id>/club-defaults", methods=["POST"])
@login_required
def save_club_defaults(series_id):
    series = _series_or_404(series_id)
    player_id_raw = request.form.get("player_id", "").strip()
    try:
        player_id = int(player_id_raw)
    except ValueError:
        flash("Ugyldig spiller.", "error")
        return redirect(url_for("series.club_stats", series_id=series.id))

    membership = SeriesPlayer.query.filter_by(series_id=series.id, player_id=player_id).first()
    if not membership:
        flash("Spilleren er ikke registrert i denne serien.", "error")
        return redirect(url_for("series.club_stats", series_id=series.id))

    club_ids = {club.id for club in Club.query.all()}
    for hole in series.course.holes:
        field_name = f"default_club_{hole.hole_number}"
        club_id_raw = request.form.get(field_name, "").strip()
        existing = PlayerHoleDefaultClub.query.filter_by(
            player_id=player_id,
            course_id=series.course_id,
            hole_number=hole.hole_number,
        ).first()

        if not club_id_raw:
            if existing:
                db.session.delete(existing)
            continue

        try:
            club_id = int(club_id_raw)
        except ValueError:
            flash(f"Ugyldig køllevalg på hull {hole.hole_number}.", "error")
            return redirect(url_for("series.club_stats", series_id=series.id, player_id=player_id, edit_defaults=1))

        if club_id not in club_ids:
            flash(f"Valgt kølle finnes ikke på hull {hole.hole_number}.", "error")
            return redirect(url_for("series.club_stats", series_id=series.id, player_id=player_id, edit_defaults=1))

        if existing:
            existing.club_id = club_id
        else:
            db.session.add(
                PlayerHoleDefaultClub(
                    player_id=player_id,
                    course_id=series.course_id,
                    hole_number=hole.hole_number,
                    club_id=club_id,
                )
            )

    db.session.commit()
    flash("Default-køller er lagret.", "success")
    return redirect(url_for("series.club_stats", series_id=series.id, player_id=player_id))


@series_bp.route("/<int:series_id>/gallery")
@login_required
def gallery(series_id):
    series = _series_or_404(series_id)
    images = (
        RoundImage.query.join(Round)
        .filter(Round.course_id == series.course_id)
        .order_by(RoundImage.uploaded_at.desc())
        .all()
    )
    return render_template("series_gallery.html", series=series, images=images)
