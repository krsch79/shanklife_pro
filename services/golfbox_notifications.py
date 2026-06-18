from datetime import datetime

from services.mailer import send_mail
from services.weather import fetch_bekkestua_weather, summarize_weather_payload


def send_golfbox_booking_email(user, event, booking):
    recipient = _booking_recipient(user)
    if not recipient:
        return False

    subject = {
        "confirmed": "GolfBox-booking bekreftet",
        "scheduled": "GolfBox-booking planlagt",
        "scheduled_executed": "Planlagt GolfBox-booking gjennomført",
        "scheduled_failed": "Planlagt GolfBox-booking mislyktes",
        "no_availability": "Ingen ledig GolfBox-tid funnet",
        "watch_expired": "GolfBox-søk utløpt uten booking",
    }.get(event, "GolfBox-booking")
    return send_mail(subject, _booking_body(event, booking), recipient=recipient)


def _booking_recipient(user):
    if not user:
        return None
    email = (getattr(user, "email", "") or "").strip()
    if email:
        return email
    username = (getattr(user, "username", "") or "").strip()
    if "@" in username:
        return username
    return None


def _booking_body(event, booking):
    intro = {
        "confirmed": "Bookingen er gjennomført og bekreftet i GolfBox.",
        "scheduled": "En fremtidig GolfBox-booking er lagt inn.",
        "scheduled_executed": "Den planlagte GolfBox-bookingen er gjennomført og bekreftet i GolfBox.",
        "scheduled_failed": "Den planlagte GolfBox-bookingen kunne ikke gjennomføres.",
        "no_availability": "Den planlagte kjøringen fant ingen ledig starttid.",
        "watch_expired": "Overvåkingen utløp uten at det ble funnet og booket en ledig starttid.",
    }.get(event, "GolfBox-booking oppdatert.")

    play_datetime = _booking_datetime(booking)
    weather_text = _weather_text(play_datetime)
    lines = [
        intro,
        "",
        f"Bane: {booking.get('course') or 'Ballerud'}",
        f"Dato: {booking.get('date') or '-'}",
        f"Tid: {_time_text(booking)}",
        f"Spillere: {_players_text(booking.get('player_memberships') or booking.get('players'))}",
    ]
    if booking.get("message"):
        lines.append(f"Resultat: {booking['message']}")
    if booking.get("execute_at"):
        lines.append(f"Gjennomføres: {booking['execute_at']}")
    lines.extend([
        f"Forventet vær: {weather_text}",
        "",
        "Denne e-posten er sendt fra BalleTour GolfBox AI.",
    ])
    return "\n".join(lines)


def _booking_datetime(booking):
    date_value = booking.get("date")
    time_value = booking.get("time")
    if not date_value or not time_value:
        return None
    try:
        return datetime.fromisoformat(f"{date_value} {time_value}")
    except ValueError:
        return None


def _time_text(booking):
    time_from = booking.get("time") or booking.get("time_from")
    time_to = booking.get("time_to")
    if time_from and time_to and time_to != time_from:
        return f"{time_from}-{time_to}"
    return time_from or "-"


def _weather_text(play_datetime):
    if not play_datetime:
        return "Vær ikke tilgjengelig"
    try:
        payload = fetch_bekkestua_weather(play_datetime)
    except Exception:
        return "Vær ikke tilgjengelig"
    summary = summarize_weather_payload(payload)
    forecast_time = (payload or {}).get("forecast_time")
    if forecast_time:
        return f"{summary} (varsel for {forecast_time})"
    return summary


def _players_text(players):
    if not players:
        return "-"
    names = []
    for player in players:
        if isinstance(player, dict):
            names.append(player.get("player_name") or player.get("member_number") or "")
        else:
            names.append(str(player))
    names = [name for name in names if name]
    return ", ".join(names) if names else "-"
