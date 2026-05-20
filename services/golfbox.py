import os
import re
from datetime import date, datetime

import httpx

from services.time import server_now


DEFAULT_GOLFBOX_COURSE = "Ballerud"
GOLFBOX_REQUIRED_ENV = ("GOLFBOX_USERNAME", "GOLFBOX_PASSWORD")
GOLFBOX_BASE_URL = "https://www.golfbox.no"
BALLERUD_CLUB_GUID = "{FD174477-19BD-4120-BD4F-DF422371C961}"
BALLERUD_RESSOURCE_GUID = "{82966715-948D-41EB-BCAB-3F7458EDB82E}"


def _load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


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
    _load_env_file()
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

    course_name = course or DEFAULT_GOLFBOX_COURSE
    if "ballerud" not in course_name.lower():
        return {
            "status": "unsupported_course",
            "course": course_name,
            "players": player_count,
            "date": requested_date.isoformat(),
            "time_from": start_time.strftime("%H:%M"),
            "time_to": end_time.strftime("%H:%M"),
            "available_slots": [],
            "message": "GolfBox-leseren støtter foreløpig bare Ballerud.",
        }

    available_slots = _fetch_ballerud_slots(
        requested_date=requested_date,
        start_time=start_time,
        end_time=end_time,
        player_count=player_count,
    )
    return {
        "status": "ok",
        "course": DEFAULT_GOLFBOX_COURSE,
        "players": player_count,
        "date": requested_date.isoformat(),
        "time_from": start_time.strftime("%H:%M"),
        "time_to": end_time.strftime("%H:%M"),
        "available_slots": available_slots,
    }


def _fetch_ballerud_slots(requested_date, start_time, end_time, player_count):
    booking_start = f"{requested_date.strftime('%Y%m%d')}T{start_time.strftime('%H%M%S')}"
    with httpx.Client(
        follow_redirects=True,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        _login(client)
        response = client.get(
            f"{GOLFBOX_BASE_URL}/site/ressources/booking/grid.asp",
            params={
                "Ressource_GUID": BALLERUD_RESSOURCE_GUID,
                "Club_GUID": BALLERUD_CLUB_GUID,
                "Booking_Start": booking_start,
            },
        )
        response.raise_for_status()
    return _parse_grid_slots(response.text, requested_date, start_time, end_time, player_count)


def _login(client):
    response = client.post(
        f"{GOLFBOX_BASE_URL}/login.asp",
        data={
            "loginform.submitted": "true",
            "redirect": "https://ballerud.no",
            "command": "login",
            "loginform.username": os.environ["GOLFBOX_USERNAME"],
            "loginform.password": os.environ["GOLFBOX_PASSWORD"],
            "B2": "Login",
        },
    )
    response.raise_for_status()
    if "myFrontPage.asp" not in str(response.url) and "GolfBox Player" not in response.text:
        raise ValueError("GolfBox-innlogging feilet eller ga uventet svar.")


def _parse_grid_slots(html, requested_date, start_time, end_time, player_count):
    slots = []
    slot_pattern = re.compile(
        r"<div[^>]+onclick=\"click_show\([^']+'(?P<stamp>\d{8}T\d{6})'[^>]+class=\"(?P<class>[^\"]+)\"[^>]*>"
        r".*?<div class=\"time\">(?P<label>\d{1,2}:\d{2})</div>"
        r".*?<div class=\"item\">(?P<items>.*?)</div>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in slot_pattern.finditer(html):
        stamp = match.group("stamp")
        slot_date = date(
            int(stamp[0:4]),
            int(stamp[4:6]),
            int(stamp[6:8]),
        )
        if slot_date != requested_date:
            continue

        slot_time = datetime.strptime(match.group("label"), "%H:%M").time()
        if slot_time < start_time or slot_time >= end_time:
            continue

        css_class = match.group("class")
        if "blocking" in css_class or "full" in css_class:
            available_spots = 0
        else:
            occupied_spots = match.group("items").lower().count("<img")
            available_spots = max(0, 4 - occupied_spots)

        if available_spots >= player_count:
            slots.append(
                {
                    "time": match.group("label"),
                    "available_spots": available_spots,
                    "course": DEFAULT_GOLFBOX_COURSE,
                    "date": requested_date.isoformat(),
                    "source": "GolfBox",
                }
            )
    return slots


def process_golfbox_prompt(prompt):
    cleaned_prompt = " ".join((prompt or "").strip().split())
    if not cleaned_prompt:
        raise ValueError("Skriv hva du vil sjekke i GolfBox.")

    prompt_lower = cleaned_prompt.lower()
    if any(word in prompt_lower for word in ("avbestill", "avbook", "kanseller")):
        return {
            "intent": "cancel_booking",
            "status": "not_enabled",
            "message": "Avbestilling via AI er ikke aktivert ennå. Første versjon støtter bare ledighetssjekk.",
        }
    if any(word in prompt_lower for word in ("bestill", "book")) and not any(
        word in prompt_lower for word in ("ledig", "tilgjengelig")
    ):
        return {
            "intent": "create_booking",
            "status": "not_enabled",
            "message": "Booking via AI er ikke aktivert ennå. Første versjon støtter bare ledighetssjekk.",
        }

    players = _players_from_prompt(prompt_lower)
    play_date = _date_from_prompt(prompt_lower)
    time_from, time_to = _time_window_from_prompt(prompt_lower)
    course = _course_from_prompt(cleaned_prompt)
    result = find_golfbox_availability(
        course=course,
        players=players,
        play_date=play_date,
        time_from=time_from,
        time_to=time_to,
    )
    result["intent"] = "find_availability"
    result["prompt"] = cleaned_prompt
    return result


def _players_from_prompt(prompt_lower):
    match = re.search(r"(\d+)\s*(person|personer|spiller|spillere)", prompt_lower)
    if match:
        return int(match.group(1))
    return 2


def _date_from_prompt(prompt_lower):
    if "i morgen" in prompt_lower or "imorgen" in prompt_lower:
        return "tomorrow"
    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", prompt_lower)
    if iso_match:
        return iso_match.group(1)
    return "today"


def _time_window_from_prompt(prompt_lower):
    between_match = re.search(
        r"(?:mellom|fra)\s+(\d{1,2})(?::?(\d{2}))?\s+(?:og|til|-)\s+(\d{1,2})(?::?(\d{2}))?",
        prompt_lower,
    )
    if between_match:
        start_hour, start_minute, end_hour, end_minute = between_match.groups()
        return (
            _format_prompt_time(start_hour, start_minute),
            _format_prompt_time(end_hour, end_minute),
        )
    return "15:00", "17:00"


def _format_prompt_time(hour, minute=None):
    return f"{int(hour):02d}:{int(minute or 0):02d}"


def _course_from_prompt(prompt):
    match = re.search(r"\bp[åa]\s+([A-ZÆØÅa-zæøå][A-ZÆØÅa-zæøå -]+?)(?:\s+for|\s+i dag|\s+mellom|\s+fra|$)", prompt)
    if match:
        return match.group(1).strip()
    if "ballerud" in prompt.lower():
        return DEFAULT_GOLFBOX_COURSE
    return DEFAULT_GOLFBOX_COURSE
