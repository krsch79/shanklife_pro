from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import User

auth_bp = Blueprint("auth", __name__)


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
        return redirect(url_for("profile.me"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash("Feil brukernavn eller passord.", "error")
            return render_template("login.html", username=username)

        session.clear()
        session["user_id"] = user.id
        flash("Du er logget inn.", "success")
        return redirect(request.args.get("next") or url_for("profile.me"))

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

