import os
from datetime import date, datetime

from services.time import server_now


DEFAULT_GOLFBOX_COURSE = "Ballerud"
GOLFBOX_REQUIRED_ENV = ("GOLFBOX_USERNAME", "GOLFBOX_PASSWORD")


def _parse_date(value):
    raw_value = (value or "").strip().lower()
    if not raw_value or raw_value in {"today", "i dag", "idag"}:
        return server_now().date()
    if raw_value in {"tomorrow", "i morgen", "imorgen"}:
        return date.fromordinal(server_now().date().toordinal() + 1)
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError("Dato må være today, i dag eller YYYY-MM-DD.") from exc


def _parse_time(value, field_name):
    raw_value = (value or "").strip()
    if not raw_value:
        raise ValueError(f"{field_name} mangler.")
    for fmt in ("%H:%M", "%H"):
        try:
            return datetime.strptime(raw_value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"{field_name} må være HH:MM eller HH.")


def _missing_configuration():
    missing = [name for name in GOLFBOX_REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        return {
            "configured": False,
            "missing_env": missing,
            "message": (
                "GolfBox-oppslag er ikke koblet til ennå. Legg GolfBox-bruker og passord "
                "inn som miljøvariabler på Raspberry Pi, ikke i repoet."
            ),
        }
    return {"configured": True, "missing_env": [], "message": ""}


def find_golfbox_availability(
    course=DEFAULT_GOLFBOX_COURSE,
    players=2,
    play_date=None,
    time_from="15:00",
    time_to="17:00",
):
    requested_date = _parse_date(play_date)
    start_time = _parse_time(time_from, "time_from")
    end_time = _parse_time(time_to, "time_to")
    if end_time <= start_time:
        raise ValueError("time_to må være etter time_from.")

    try:
        player_count = int(players)
    except (TypeError, ValueError) as exc:
        raise ValueError("players må være et heltall.") from exc
    if player_count < 1 or player_count > 4:
        raise ValueError("players må være mellom 1 og 4.")

    config = _missing_configuration()
    if not config["configured"]:
        return {
            "status": "configuration_required",
            "course": course or DEFAULT_GOLFBOX_COURSE,
            "players": player_count,
            "date": requested_date.isoformat(),
            "time_from": start_time.strftime("%H:%M"),
            "time_to": end_time.strftime("%H:%M"),
            "available_slots": [],
            "next_step": (
                "Sett GOLFBOX_USERNAME og GOLFBOX_PASSWORD på Pi-en, restart/deploy appen, "
                "og kjør samme prompt igjen. Selve MCP-toolen er klar."
            ),
            **config,
        }

    return {
        "status": "provider_not_implemented",
        "course": course or DEFAULT_GOLFBOX_COURSE,
        "players": player_count,
        "date": requested_date.isoformat(),
        "time_from": start_time.strftime("%H:%M"),
        "time_to": end_time.strftime("%H:%M"),
        "available_slots": [],
        "message": (
            "GolfBox-credentials er konfigurert, men den konkrete GolfBox-ledighetsleseren "
            "må kobles mot riktig GolfBox-side/API før live tider kan hentes."
        ),
    }
