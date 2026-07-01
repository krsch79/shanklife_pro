from functools import wraps
import hashlib

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import BalleTourInvitation, Player, SeriesPlayer, User
from services.balletour import get_balletour_series, is_balletour_player
from services.golfbox import sync_user_golfbox_handicap
from services.time import server_now

auth_bp = Blueprint("auth", __name__)


def _hash_invitation_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not g.get("current_user"):
            flash("Du må logge inn først.", "error")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("current_user"):
        if is_balletour_player(g.current_user):
            return redirect(url_for("balletour.me"))
        return redirect(url_for("profile.me"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash("Feil brukernavn eller passord.", "error")
            return render_template("login.html", username=username)

        try:
            sync_user_golfbox_handicap(user)
        except ValueError as exc:
            db.session.rollback()
            current_app.logger.warning("GolfBox handicap-sync feilet for bruker %s: %s", user.id, exc)

        session.clear()
        session["user_id"] = user.id
        flash("Du er logget inn.", "success")
        default_next = url_for("balletour.me") if is_balletour_player(user) else url_for("profile.me")
        return redirect(request.args.get("next") or default_next)

    return render_template("login.html", username="")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Du er logget ut.", "success")
    return redirect(url_for("main.index"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(g.current_user.password_hash, current_password):
            flash("Nåværende passord er feil.", "error")
            return render_template("change_password.html")

        if len(new_password) < 4:
            flash("Nytt passord må være minst 4 tegn.", "error")
            return render_template("change_password.html")

        if new_password != confirm_password:
            flash("Nytt passord og bekreftelse er ikke like.", "error")
            return render_template("change_password.html")

        g.current_user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash("Passordet er endret.", "success")
        return redirect(url_for("profile.me"))

    return render_template("change_password.html")


@auth_bp.route("/balletour-invitation/<token>", methods=["GET", "POST"])
def accept_balletour_invitation(token):
    token_hash = _hash_invitation_token(token)
    invitation = BalleTourInvitation.query.filter_by(token_hash=token_hash).first()
    if not invitation or invitation.accepted_at:
        flash("Invitasjonslenken er ugyldig eller allerede brukt.", "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(password) < 4:
            flash("Passordet må være minst 4 tegn.", "error")
            return render_template("accept_balletour_invitation.html", invitation=invitation)
        if password != confirm_password:
            flash("Passord og bekreftelse er ikke like.", "error")
            return render_template("accept_balletour_invitation.html", invitation=invitation)

        if User.query.filter(db.func.lower(User.username) == invitation.email.lower()).first():
            flash("Det finnes allerede en bruker med denne e-postadressen.", "error")
            return redirect(url_for("auth.login"))
        if Player.query.filter(db.func.lower(Player.name) == invitation.name.lower()).first():
            flash("Det finnes allerede en spiller med dette navnet. Be en administrator sende ny invitasjon.", "error")
            return redirect(url_for("auth.login"))

        series = get_balletour_series()
        if not series:
            flash("Fant ikke BalleTour-serien. Be en administrator sjekke oppsettet.", "error")
            return redirect(url_for("auth.login"))

        player = Player(name=invitation.name, default_hcp=0.0, gender="male")
        db.session.add(player)
        db.session.flush()

        user = User(
            username=invitation.email,
            password_hash=generate_password_hash(password),
            player_id=player.id,
            is_admin=False,
            email=invitation.email,
        )
        db.session.add(user)
        db.session.flush()

        max_display_order = (
            db.session.query(db.func.max(SeriesPlayer.display_order))
            .filter_by(series_id=series.id)
            .scalar()
            or 0
        )
        db.session.add(SeriesPlayer(
            series_id=series.id,
            player_id=player.id,
            display_order=max_display_order + 1,
        ))
        invitation.accepted_user_id = user.id
        invitation.accepted_at = server_now()
        db.session.commit()

        session.clear()
        session["user_id"] = user.id
        flash("Velkommen til BalleTour. Passordet er satt, og du er logget inn.", "success")
        return redirect(url_for("balletour.index"))

    return render_template("accept_balletour_invitation.html", invitation=invitation)
