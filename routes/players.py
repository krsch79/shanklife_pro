from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func

from extensions import db
from models import Player, RoundPlayer

players_bp = Blueprint("players", __name__)


@players_bp.route("/players")
def players():
    all_players = Player.query.order_by(Player.name.asc()).all()
    return render_template("players.html", players=all_players)


@players_bp.route("/players/new", methods=["GET", "POST"])
def new_player():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        gender = request.form.get("gender", "male").strip()
        default_hcp_raw = request.form.get("default_hcp", "").strip()

        if gender not in ("male", "female"):
            gender = "male"

        if not name:
            flash("Spillernavn må fylles ut.", "error")
            return render_template("player_form.html", player=None)

        existing = Player.query.filter(func.lower(Player.name) == name.lower()).first()
        if existing:
            flash("Det finnes allerede en spiller med dette navnet.", "error")
            return render_template("player_form.html", player=None)

        try:
            default_hcp = float(default_hcp_raw.replace(",", "."))
        except ValueError:
            flash("HCP må være et gyldig tall.", "error")
            return render_template("player_form.html", player=None)

        player = Player(name=name, gender=gender, default_hcp=default_hcp)
        db.session.add(player)
        db.session.commit()

        flash("Spiller opprettet.", "success")
        return redirect(url_for("players.players"))

    return render_template("player_form.html", player=None)


@players_bp.route("/players/<int:player_id>/edit", methods=["GET", "POST"])
def edit_player(player_id):
    player = Player.query.get_or_404(player_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        gender = request.form.get("gender", "male").strip()
        default_hcp_raw = request.form.get("default_hcp", "").strip()

        if gender not in ("male", "female"):
            gender = "male"

        if not name:
            flash("Spillernavn må fylles ut.", "error")
            return render_template("player_form.html", player=player)

        duplicate = Player.query.filter(
            func.lower(Player.name) == name.lower(),
            Player.id != player.id,
        ).first()
        if duplicate:
            flash("Det finnes allerede en annen spiller med dette navnet.", "error")
            return render_template("player_form.html", player=player)

        try:
            default_hcp = float(default_hcp_raw.replace(",", "."))
        except ValueError:
            flash("HCP må være et gyldig tall.", "error")
            return render_template("player_form.html", player=player)

        player.name = name
        player.gender = gender
        player.default_hcp = default_hcp
        db.session.commit()

        flash("Spiller oppdatert.", "success")
        return redirect(url_for("players.players"))

    return render_template("player_form.html", player=player)


@players_bp.route("/players/<int:player_id>/delete", methods=["POST"])
def delete_player(player_id):
    player = Player.query.get_or_404(player_id)

    is_in_use = RoundPlayer.query.filter_by(player_id=player.id).first() is not None
    if is_in_use:
        flash("Kan ikke slette spiller som allerede er brukt i en eller flere runder.", "error")
        return redirect(url_for("players.players"))

    db.session.delete(player)
    db.session.commit()
    flash("Spiller slettet.", "success")
    return redirect(url_for("players.players"))
