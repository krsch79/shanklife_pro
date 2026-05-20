import base64
import html
import os
import re
from datetime import date, datetime

import httpx
from flask import current_app

from services.time import server_now


DEFAULT_GOLFBOX_COURSE = "Ballerud"
DEFAULT_TIME_FROM = "06:00"
DEFAULT_TIME_TO = "22:00"
GOLFBOX_REQUIRED_ENV = ("GOLFBOX_USERNAME", "GOLFBOX_PASSWORD")
GOLFBOX_BASE_URL = "https://www.golfbox.no"
BALLERUD_CLUB_GUID = "{FD174477-19BD-4120-BD4F-DF422371C961}"
BALLERUD_RESSOURCE_GUID = "{82966715-948D-41EB-BCAB-3F7458EDB82E}"


def _secret_bytes():
    secret_key = current_app.config.get("SECRET_KEY") or "shanklife-pro-local-dev-key"
    return secret_key.encode("utf-8")


def _encode_password(password):
    password_bytes = (password or "").encode("utf-8")
    key = _secret_bytes()
    encoded = bytes(value ^ key[index % len(key)] for index, value in enumerate(password_bytes))
    return base64.urlsafe_b64encode(encoded).decode("ascii")


def _decode_password(token):
    if not token:
        return ""
    try:
        password_bytes = base64.urlsafe_b64decode(token.encode("ascii"))
    except (ValueError, TypeError):
        return ""
    key = _secret_bytes()
    decoded = bytes(value ^ key[index % len(key)] for index, value in enumerate(password_bytes))
    return decoded.decode("utf-8", errors="ignore")


def user_has_golfbox_credentials(user):
    return bool(user and (user.golfbox_username or "").strip() and (user.golfbox_password_token or "").strip())


def golfbox_connection_summary(user):
    if not user_has_golfbox_credentials(user):
        return {
            "connected": False,
            "player_name": None,
            "club_name": None,
            "member_number": None,
            "username": None,
        }
    return {
        "connected": True,
        "player_name": user.golfbox_player_name,
        "club_name": user.golfbox_home_club_name,
        "member_number": user.golfbox_member_number,
        "username": user.golfbox_username,
    }


def _credentials_for_user(user):
    if not user_has_golfbox_credentials(user):
        return None
    return {
        "username": (user.golfbox_username or "").strip(),
        "password": _decode_password(user.golfbox_password_token),
    }


def _credentials_from_env():
    config = _missing_configuration()
    if not config["configured"]:
        return None
    return {
        "username": os.environ["GOLFBOX_USERNAME"],
        "password": os.environ["GOLFBOX_PASSWORD"],
    }


def save_user_golfbox_credentials(user, username, password):
    credentials = {
        "username": (username or "").strip(),
        "password": password or "",
    }
    if not credentials["username"] or not credentials["password"]:
        raise ValueError("Legg inn både GolfBox-brukernavn og passord.")
    with httpx.Client(
        follow_redirects=True,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        frontpage_html = _login(client, credentials)
    identity = _parse_identity(frontpage_html)
    user.golfbox_username = credentials["username"]
    user.golfbox_password_token = _encode_password(credentials["password"])
    user.golfbox_player_name = identity.get("player_name")
    user.golfbox_home_club_name = identity.get("club_name")
    user.golfbox_member_number = identity.get("member_number")
    user.golfbox_credentials_updated_at = server_now()
    return identity


def clear_user_golfbox_credentials(user):
    user.golfbox_username = None
    user.golfbox_password_token = None
    user.golfbox_player_name = None
    user.golfbox_home_club_name = None
    user.golfbox_member_number = None
    user.golfbox_credentials_updated_at = None


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
    user=None,
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

    credentials = _credentials_for_user(user) or _credentials_from_env()
    if not credentials:
        return {
            "status": "configuration_required",
            "course": course or DEFAULT_GOLFBOX_COURSE,
            "players": player_count,
            "date": requested_date.isoformat(),
            "time_from": start_time.strftime("%H:%M"),
            "time_to": end_time.strftime("%H:%M"),
            "available_slots": [],
            "next_step": (
                "Legg GolfBox-innlogging inn på Min side, og kjør samme prompt igjen."
            ),
            "configured": False,
            "missing_env": list(GOLFBOX_REQUIRED_ENV),
            "message": "GolfBox-innlogging mangler for brukeren.",
        }

    course_name = course or DEFAULT_GOLFBOX_COURSE
    club_guid = BALLERUD_CLUB_GUID
    resource_guid = BALLERUD_RESSOURCE_GUID
    resolved_course_name = DEFAULT_GOLFBOX_COURSE
    booking_enabled = True
    if "ballerud" not in course_name.lower():
        resolved = _resolve_course(credentials, course_name)
        if not resolved:
            return {
                "status": "unsupported_course",
                "course": course_name,
                "players": player_count,
                "date": requested_date.isoformat(),
                "time_from": start_time.strftime("%H:%M"),
                "time_to": end_time.strftime("%H:%M"),
                "available_slots": [],
                "message": f"Jeg fant ikke {course_name} i GolfBox-listen.",
            }
        club_guid = resolved["club_guid"]
        resource_guid = resolved["resource_guid"]
        resolved_course_name = resolved["course"]
        booking_enabled = False

    available_slots = _fetch_slots(
        credentials=credentials,
        club_guid=club_guid,
        resource_guid=resource_guid,
        course_name=resolved_course_name,
        requested_date=requested_date,
        start_time=start_time,
        end_time=end_time,
        player_count=player_count,
    )
    return {
        "status": "ok",
        "course": resolved_course_name,
        "players": player_count,
        "date": requested_date.isoformat(),
        "time_from": start_time.strftime("%H:%M"),
        "time_to": end_time.strftime("%H:%M"),
        "available_slots": available_slots,
        "booking_enabled": booking_enabled,
    }


def _fetch_slots(credentials, club_guid, resource_guid, course_name, requested_date, start_time, end_time, player_count):
    booking_start = f"{requested_date.strftime('%Y%m%d')}T{start_time.strftime('%H%M%S')}"
    with httpx.Client(
        follow_redirects=True,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        _login(client, credentials)
        response = client.get(
            f"{GOLFBOX_BASE_URL}/site/ressources/booking/grid.asp",
            params={
                "Ressource_GUID": resource_guid,
                "Club_GUID": club_guid,
                "Booking_Start": booking_start,
            },
        )
        response.raise_for_status()
    return _parse_grid_slots(response.text, requested_date, start_time, end_time, player_count, course_name)


def _login(client, credentials):
    response = client.post(
        f"{GOLFBOX_BASE_URL}/login.asp",
        data={
            "loginform.submitted": "true",
            "redirect": "https://ballerud.no",
            "command": "login",
            "loginform.username": credentials["username"],
            "loginform.password": credentials["password"],
            "B2": "Login",
        },
    )
    response.raise_for_status()
    if "myFrontPage.asp" not in str(response.url) and "GolfBox Player" not in response.text:
        raise ValueError("GolfBox-innlogging feilet eller ga uventet svar.")
    return response.text


def _parse_grid_slots(html_text, requested_date, start_time, end_time, player_count, course_name):
    slots = []
    slot_pattern = re.compile(
        r"<div[^>]+onclick=\"click_show\([^']+'(?P<stamp>\d{8}T\d{6})'[^>]+class=\"(?P<class>[^\"]+)\"[^>]*>"
        r".*?<div class=\"time\">(?P<label>\d{1,2}:\d{2})</div>"
        r".*?<div class=\"item\">(?P<items>.*?)</div>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in slot_pattern.finditer(html_text):
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
                    "course": course_name,
                    "date": requested_date.isoformat(),
                    "source": "GolfBox",
                }
            )
    return slots


def _parse_identity(frontpage_html):
    text = " ".join(re.sub(r"<[^>]+>", " ", frontpage_html).split())
    identity_matches = re.findall(
        r"(?P<name>[A-ZÆØÅ][A-Za-zÆØÅæøå.'-]+(?:\s+[A-ZÆØÅ][A-Za-zÆØÅæøå.'-]+){1,4})\s*\|\s*(?P<club>[^|]{2,80}?)\s*\|\s*(?P<member>\d{1,5}-\d{1,8})\s*\|\s*HCP",
        text,
    )
    if not identity_matches:
        return {
            "player_name": None,
            "club_name": None,
            "member_number": None,
        }
    name, club, member_number = identity_matches[-1]
    return {
        "player_name": html.unescape(name).strip(),
        "club_name": html.unescape(club).strip(),
        "member_number": member_number.strip(),
    }


def _select_options(page_html, select_name):
    select_match = re.search(
        rf"<select[^>]+name=[\"']{re.escape(select_name)}[\"'][^>]*>(?P<body>.*?)</select>",
        page_html,
        re.IGNORECASE | re.DOTALL,
    )
    if not select_match:
        return []
    options = []
    for option_match in re.finditer(
        r"<option[^>]+value=[\"'](?P<value>[^\"']*)[\"'][^>]*>(?P<label>.*?)</option>",
        select_match.group("body"),
        re.IGNORECASE | re.DOTALL,
    ):
        value = html.unescape(option_match.group("value")).strip()
        label = " ".join(re.sub(r"<[^>]+>", " ", option_match.group("label")).split())
        if value and label:
            options.append({"value": value, "label": html.unescape(label).strip()})
    return options


def _resolve_course(credentials, course_name):
    requested = (course_name or "").strip().lower()
    if not requested:
        return None
    with httpx.Client(
        follow_redirects=True,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        _login(client, credentials)
        choose_response = client.get(f"{GOLFBOX_BASE_URL}/site/ressources/booking/chooseclub.asp")
        choose_response.raise_for_status()
        clubs = _select_options(choose_response.text, "ddlClub")
        selected_club = _best_option_match(clubs, requested)
        if not selected_club:
            return None
        resource_response = client.post(
            f"{GOLFBOX_BASE_URL}/site/ressources/booking/chooseclub.asp",
            data={
                "command": "getClub",
                "commandValue": "",
                "ddlClub": selected_club["value"],
            },
        )
        resource_response.raise_for_status()
        resources = _select_options(resource_response.text, "ddlRessoruce")
        selected_resource = resources[0] if resources else None
        if not selected_resource:
            return None
        return {
            "club_guid": selected_club["value"],
            "resource_guid": selected_resource["value"],
            "course": selected_resource["label"],
        }


def _best_option_match(options, requested):
    normalized_requested = _normalize_name(requested)
    for option in options:
        if normalized_requested == _normalize_name(option["label"]):
            return option
    for option in options:
        if normalized_requested in _normalize_name(option["label"]):
            return option
    requested_words = {word for word in normalized_requested.split() if len(word) > 2 and word != "golfklubb"}
    if not requested_words:
        return None
    for option in options:
        option_words = set(_normalize_name(option["label"]).split())
        if requested_words.issubset(option_words):
            return option
    return None


def _normalize_name(value):
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-zæøå]+", " ", (value or "").lower())).strip()


def _book_ballerud_slot(credentials, user, booking_date, booking_time):
    booking_start = f"{booking_date.strftime('%Y%m%d')}T{booking_time.strftime('%H%M%S')}"
    with httpx.Client(
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        _login(client, credentials)
        window_response = client.get(
            f"{GOLFBOX_BASE_URL}/site/my_golfbox/ressources/booking/window.asp",
            params={
                "Ressource_GUID": BALLERUD_RESSOURCE_GUID,
                "Booking_Start": booking_start,
                "club_GUID": BALLERUD_CLUB_GUID,
            },
        )
        window_response.raise_for_status()
        validation = _validate_ballerud_booking_window(window_response.text, user)
        if validation["status"] != "ok":
            _cleanup_booking_lock(client, booking_start)
            return validation

        form_data = _form_inputs(window_response.text)
        form_data["command"] = "next"
        form_data["commandValue"] = ""
        submit_response = client.post(
            str(window_response.url),
            data=form_data,
        )
        submit_response.raise_for_status()
        if _booking_response_requires_payment(submit_response.text):
            _cleanup_booking_lock(client, booking_start)
            return {
                "intent": "create_booking",
                "status": "payment_required",
                "message": "GolfBox ber om betaling. Jeg stoppet før bookingen ble fullført.",
                "available_slots": [],
            }
        if "Tiden er låst" in submit_response.text or "låst" in submit_response.text.lower():
            return {
                "intent": "create_booking",
                "status": "booking_failed",
                "message": "Starttiden er låst i GolfBox akkurat nå. Prøv igjen om litt.",
                "available_slots": [],
            }
    return {
        "intent": "create_booking",
        "status": "booking_created",
        "course": DEFAULT_GOLFBOX_COURSE,
        "date": booking_date.isoformat(),
        "time": booking_time.strftime("%H:%M"),
        "players": 1,
        "message": f"Bookingen er sendt til GolfBox for {DEFAULT_GOLFBOX_COURSE} {booking_date.isoformat()} kl. {booking_time.strftime('%H:%M')}.",
        "available_slots": [],
    }


def _validate_ballerud_booking_window(page_html, user):
    page_text = " ".join(re.sub(r"<[^>]+>", " ", page_html).split())
    if "Tiden er låst" in page_text:
        return {
            "intent": "create_booking",
            "status": "booking_failed",
            "message": "Starttiden er låst i GolfBox akkurat nå. Prøv igjen om litt.",
            "available_slots": [],
        }
    if "Ballerud Golfklubb" not in page_text:
        return {
            "intent": "create_booking",
            "status": "wrong_club",
            "message": "GolfBox viser ikke Ballerud som valgt klubb. Jeg stoppet bookingen.",
            "available_slots": [],
        }
    member_number = (getattr(user, "golfbox_member_number", "") or "").strip()
    if member_number and f"Medlemsnummer: {member_number}" not in page_text and f'value="{member_number}"' not in page_html:
        return {
            "intent": "create_booking",
            "status": "wrong_membership",
            "message": "GolfBox viser ikke det lagrede Ballerud-medlemsnummeret. Jeg stoppet bookingen.",
            "available_slots": [],
        }
    prices = [
        int(value)
        for value in re.findall(r'name="hidden_BookingPrice_\d+(?:_9Hole)?" value="(\d+)"', page_html)
    ]
    if any(price > 0 for price in prices):
        return {
            "intent": "create_booking",
            "status": "payment_required",
            "message": "GolfBox viser en pris på bookingen. Jeg stoppet før betaling/booking.",
            "available_slots": [],
        }
    return {"status": "ok"}


def _booking_response_requires_payment(page_html):
    page_text = " ".join(re.sub(r"<[^>]+>", " ", page_html).split()).lower()
    payment_words = ("registrer betalingsmåte", "betaling", "payandconfirm", "greenfee")
    return any(word in page_text for word in payment_words)


def _form_inputs(page_html):
    form_data = {}
    for input_match in re.finditer(r"<input\b(?P<attrs>[^>]*)>", page_html, re.IGNORECASE | re.DOTALL):
        attrs = input_match.group("attrs")
        name = _attr_value(attrs, "name")
        if not name:
            continue
        input_type = (_attr_value(attrs, "type") or "text").lower()
        if input_type in {"button", "submit", "image", "file"}:
            continue
        if input_type in {"checkbox", "radio"} and "checked" not in attrs.lower():
            continue
        form_data[name] = _attr_value(attrs, "value")
    return form_data


def _attr_value(attrs, attr_name):
    attr_match = re.search(rf"{re.escape(attr_name)}=[\"'](?P<value>[^\"']*)[\"']", attrs, re.IGNORECASE)
    if not attr_match:
        return ""
    return html.unescape(attr_match.group("value"))


def _cleanup_booking_lock(client, booking_start):
    try:
        client.post(
            f"{GOLFBOX_BASE_URL}/site/ressources/booking/cleanup.asp",
            data={
                "Ressource_GUID": BALLERUD_RESSOURCE_GUID,
                "Booking_Start": booking_start,
            },
        )
    except httpx.HTTPError:
        return


def process_golfbox_prompt(prompt, user=None, pending_booking=None):
    cleaned_prompt = " ".join((prompt or "").strip().split())
    if not cleaned_prompt:
        raise ValueError("Skriv hva du vil sjekke i GolfBox.")

    prompt_lower = cleaned_prompt.lower()
    if pending_booking and _is_confirmation_prompt(prompt_lower):
        return confirm_golfbox_booking(pending_booking, user=user)

    if any(word in prompt_lower for word in ("avbestill", "avbook", "kanseller")):
        return {
            "intent": "cancel_booking",
            "status": "not_enabled",
            "message": "Avbestilling via AI er ikke aktivert ennå. Første versjon støtter bare ledighetssjekk.",
        }
    booking_requested = any(word in prompt_lower for word in ("bestill", "book"))

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
        user=user,
    )
    result["intent"] = "create_booking" if booking_requested else "find_availability"
    result["prompt"] = cleaned_prompt
    if booking_requested:
        result = _booking_confirmation_result(result)
    return result


def _is_confirmation_prompt(prompt_lower):
    return prompt_lower in {"ja", "ja takk", "bekreft", "book", "bestill", "ok", "kjør"} or "bekreft booking" in prompt_lower


def _booking_confirmation_result(availability_result):
    if availability_result["status"] != "ok":
        return availability_result
    if not availability_result.get("booking_enabled"):
        availability_result["status"] = "booking_unsupported_course"
        availability_result["message"] = "Booking er foreløpig bare aktivert for Ballerud. Jeg kan sjekke ledighet på denne banen."
        return availability_result
    if availability_result["players"] != 1:
        availability_result["status"] = "needs_player_details"
        availability_result["message"] = (
            "Jeg kan klargjøre Ballerud-booking for én innlogget bruker nå. "
            "For flere spillere trenger jeg en trygg spiller-/medlemsnummerflyt før jeg legger dem til i GolfBox."
        )
        return availability_result
    if not availability_result.get("available_slots"):
        return availability_result
    selected_slot = availability_result["available_slots"][0]
    pending = {
        "course": DEFAULT_GOLFBOX_COURSE,
        "date": selected_slot["date"],
        "time": selected_slot["time"],
        "players": availability_result["players"],
        "club_guid": BALLERUD_CLUB_GUID,
        "resource_guid": BALLERUD_RESSOURCE_GUID,
    }
    availability_result["status"] = "confirmation_required"
    availability_result["message"] = (
        f"Jeg kan booke {DEFAULT_GOLFBOX_COURSE} {selected_slot['date']} kl. {selected_slot['time']} "
        "for deg. Bekreft før jeg sender bookingen til GolfBox."
    )
    availability_result["pending_booking"] = pending
    return availability_result


def confirm_golfbox_booking(pending_booking, user=None):
    credentials = _credentials_for_user(user)
    if not credentials:
        return {
            "intent": "create_booking",
            "status": "configuration_required",
            "message": "Legg GolfBox-innlogging inn på Min side før du booker.",
            "available_slots": [],
        }
    if (pending_booking or {}).get("course") != DEFAULT_GOLFBOX_COURSE:
        return {
            "intent": "create_booking",
            "status": "booking_unsupported_course",
            "message": "Booking er foreløpig bare aktivert for Ballerud.",
            "available_slots": [],
        }
    booking_date = date.fromisoformat(pending_booking["date"])
    booking_time = _parse_time(pending_booking["time"], "booking_time")
    return _book_ballerud_slot(credentials, user, booking_date, booking_time)


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
        r"(?:mellom|fra)\s+(\d{1,2})(?::?(\d{2}))?\s*(?:og|til|-)\s*(\d{1,2})(?::?(\d{2}))?",
        prompt_lower,
    )
    if between_match:
        start_hour, start_minute, end_hour, end_minute = between_match.groups()
        return (
            _format_prompt_time(start_hour, start_minute),
            _format_prompt_time(end_hour, end_minute),
        )

    after_match = re.search(r"(?:etter|fra)\s+(?:kl\.?\s*)?(\d{1,2})(?::?(\d{2}))?", prompt_lower)
    if after_match:
        hour, minute = after_match.groups()
        return _format_prompt_time(hour, minute), DEFAULT_TIME_TO

    before_match = re.search(r"(?:før|til)\s+(?:kl\.?\s*)?(\d{1,2})(?::?(\d{2}))?", prompt_lower)
    if before_match:
        hour, minute = before_match.groups()
        return DEFAULT_TIME_FROM, _format_prompt_time(hour, minute)

    at_match = re.search(r"(?:kl\.?|rundt)\s*(\d{1,2})(?::?(\d{2}))?", prompt_lower)
    if at_match:
        hour, minute = at_match.groups()
        start_hour = max(0, int(hour) - 1)
        end_hour = min(23, int(hour) + 1)
        return _format_prompt_time(start_hour, minute), _format_prompt_time(end_hour, minute)

    return DEFAULT_TIME_FROM, DEFAULT_TIME_TO


def _format_prompt_time(hour, minute=None):
    return f"{int(hour):02d}:{int(minute or 0):02d}"


def _course_from_prompt(prompt):
    match = re.search(r"\bp[åa]\s+([A-ZÆØÅa-zæøå][A-ZÆØÅa-zæøå -]+?)(?:\s+for|\s+i dag|\s+mellom|\s+fra|$)", prompt)
    if match:
        return match.group(1).strip()
    if "ballerud" in prompt.lower():
        return DEFAULT_GOLFBOX_COURSE
    return DEFAULT_GOLFBOX_COURSE
