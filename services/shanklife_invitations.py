"""One-use Shanklife invitations, valid for seven days, with default app access."""
import hashlib
import re
import secrets
from datetime import timedelta

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from extensions import db
from models import Player, ShanklifeInvitation, User
from routes.admin import admin_required
from services.mailer import send_mail
from services.time import server_now

invitation_bp = Blueprint("shanklife_invitations", __name__)


def _existing_user(email):
    return User.query.filter(db.or_(db.func.lower(User.username) == email, db.func.lower(User.email) == email)).first()


@invitation_bp.route("/admin/shanklife-invitations", methods=["POST"])
@admin_required
def invite():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    if not name or len(name) > 120 or len(email) > 255 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        flash("Fyll inn navn og en gyldig e-postadresse.", "error")
    elif _existing_user(email):
        flash("Denne e-postadressen har allerede en bruker. Administrer tilgangen for eksisterende bruker.", "error")
    elif Player.query.filter(db.func.lower(Player.name) == name.lower()).first():
        flash("Det finnes allerede en spiller med dette navnet. Bruk et navn som skiller spillerne.", "error")
    else:
        token = secrets.token_urlsafe(32)
        invitation = ShanklifeInvitation.query.filter_by(email=email, accepted_at=None).first()
        if invitation is None:
            invitation = ShanklifeInvitation(email=email)
            db.session.add(invitation)
        invitation.name = name
        invitation.token_hash = hashlib.sha256(token.encode()).hexdigest()
        invitation.invited_by_user_id = g.current_user.id
        invitation.created_at = server_now()
        link = 'https://pro.shanklife.no' + url_for('auth.accept_shanklife_invitation', token=token)
        db.session.flush()
        if send_mail("Du er invitert til Shanklife Pro", f"Hei {name}!\n\nDu er invitert til Shanklife Pro. Velg passord via lenken under. Du får automatisk tilgang til Shanklife Pro og Shanklife-appen.\n\n{link}\n\nLenken kan brukes én gang og er gyldig i 7 dager.\n", recipient=email):
            db.session.commit()
            flash(f"Invitasjon sendt til {name} på {email}.", "success")
        else:
            db.session.rollback()
            flash("Invitasjonen ble ikke sendt. Prøv igjen eller sjekk e-postoppsettet.", "error")
    return redirect(url_for("admin.admin_home"))


def accept(token):
    invitation = ShanklifeInvitation.query.filter_by(token_hash=hashlib.sha256(token.encode()).hexdigest()).first()
    if not invitation or invitation.accepted_at or invitation.created_at < server_now() - timedelta(days=7):
        flash("Invitasjonslenken er ugyldig, utløpt eller allerede brukt. Be administrator om en ny invitasjon.", "error")
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        password = request.form.get("password", "")
        if len(password) < 8 or password != request.form.get("confirm_password", ""):
            flash("Passordet må være minst 8 tegn, og bekreftelsen må være lik.", "error")
        elif _existing_user(invitation.email) or Player.query.filter(db.func.lower(Player.name) == invitation.name.lower()).first():
            flash("Brukeren eller spillernavnet finnes allerede. Kontakt administrator.", "error")
        else:
            app_ids = db.session.execute(text("SELECT id FROM app_registry WHERE slug IN ('shanklife-pro', 'shanklife-app')")).scalars().all()
            if len(app_ids) != 2:
                flash("Tilgangsoppsettet mangler. Kontakt administrator.", "error")
                return render_template("accept_shanklife_invitation.html", invitation=invitation)
            claimed = ShanklifeInvitation.query.filter_by(
                id=invitation.id, token_hash=hashlib.sha256(token.encode()).hexdigest(), accepted_at=None
            ).filter(ShanklifeInvitation.created_at >= server_now() - timedelta(days=7)).update({"accepted_at": server_now()})
            if not claimed:
                db.session.rollback()
                return redirect(url_for("auth.login"))
            player = Player(name=invitation.name, default_hcp=0.0, gender="male")
            db.session.add(player)
            db.session.flush()
            user = User(username=invitation.email, email=invitation.email, player_id=player.id, is_admin=False, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.flush()
            for app_id in app_ids:
                db.session.execute(text("INSERT INTO user_app_access (user_id, app_id, has_access, is_app_admin) VALUES (:user, :app, 1, 0)"), {"user": user.id, "app": app_id})
            invitation.accepted_user_id = user.id
            db.session.commit()
            session.clear()
            session.permanent = True
            session["user_id"] = user.id
            flash("Velkommen til Shanklife Pro! Du er logget inn.", "success")
            return redirect(url_for("main.index"))
    return render_template("accept_shanklife_invitation.html", invitation=invitation)
