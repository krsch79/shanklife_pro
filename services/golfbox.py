import base64
import html
import json
import os
import re
from datetime import date, datetime, timedelta

import httpx
from flask import current_app
from openai import OpenAI

from extensions import db
from services.golfbox_notifications import send_golfbox_booking_email
from services.secret_store import decrypt_secret, encrypt_secret, is_encrypted_secret
from services.time import server_now


DEFAULT_GOLFBOX_COURSE = "Ballerud"
DEFAULT_TIME_FROM = "06:00"
DEFAULT_TIME_TO = "22:00"
GOLFBOX_REQUIRED_ENV = ("GOLFBOX_USERNAME", "GOLFBOX_PASSWORD")
GOLFBOX_BASE_URL = "https://www.golfbox.no"
BALLERUD_CLUB_GUID = "{FD174477-19BD-4120-BD4F-DF422371C961}"
BALLERUD_RESSOURCE_GUID = "{82966715-948D-41EB-BCAB-3F7458EDB82E}"
GOLFBOX_MY_TIMES_PATH = "/site/my_golfBox/myTimes/myTimes.asp"
OSLO_AREA_COURSES = [
    "Ballerud",
    "Oslo",
    "Haga",
    "Bærum",
    "Grini",
    "Asker",
    "Oppegård",
    "Drøbak",
]
WEEKDAY_NAMES = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]


def _secret_bytes():
    secret_key = current_app.config.get("SECRET_KEY") or "shanklife-pro-local-dev-key"
    return secret_key.encode("utf-8")


def _encode_password(password):
    return encrypt_secret(password or "")


def _decode_password(token):
    if not token:
        return ""
    if is_encrypted_secret(token):
        try:
            return decrypt_secret(token)
        except Exception:
            return ""
    return _decode_legacy_password(token)


def _decode_legacy_password(token):
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
    memberships = _user_memberships(user)
    if not user_has_golfbox_credentials(user):
        return {
            "connected": False,
            "player_name": None,
            "club_name": None,
            "member_number": None,
            "username": None,
            "memberships": [],
        }
    return {
        "connected": True,
        "player_name": user.golfbox_player_name,
        "club_name": user.golfbox_home_club_name,
        "member_number": user.golfbox_member_number,
        "username": user.golfbox_username,
        "memberships": memberships,
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
        memberships = _fetch_memberships(client, frontpage_html)
    identity = _parse_identity(frontpage_html)
    user.golfbox_username = credentials["username"]
    user.golfbox_password_token = _encode_password(credentials["password"])
    user.golfbox_player_name = identity.get("player_name")
    user.golfbox_home_club_name = identity.get("club_name")
    user.golfbox_member_number = identity.get("member_number")
    user.golfbox_memberships_json = json.dumps(memberships, ensure_ascii=False)
    user.golfbox_credentials_updated_at = server_now()
    return identity


def clear_user_golfbox_credentials(user):
    user.golfbox_username = None
    user.golfbox_password_token = None
    user.golfbox_player_name = None
    user.golfbox_home_club_name = None
    user.golfbox_member_number = None
    user.golfbox_memberships_json = None
    user.golfbox_credentials_updated_at = None


def migrate_golfbox_password_tokens():
    from models import User

    changed = False
    users = User.query.filter(User.golfbox_password_token.isnot(None)).all()
    for user in users:
        token = user.golfbox_password_token or ""
        if not token or is_encrypted_secret(token):
            continue
        password = _decode_legacy_password(token)
        if not password:
            continue
        user.golfbox_password_token = _encode_password(password)
        changed = True
    if changed:
        db.session.commit()


def _user_memberships(user):
    if not user or not (getattr(user, "golfbox_memberships_json", None) or "").strip():
        return []
    try:
        memberships = json.loads(user.golfbox_memberships_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(memberships, list):
        return []
    return [
        membership for membership in memberships
        if isinstance(membership, dict) and membership.get("member_number") and membership.get("club_name")
    ]


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
        try:
            return datetime.strptime(raw_value, "%d.%m.%Y").date()
        except ValueError:
            raise ValueError("Dato må være today, i dag, YYYY-MM-DD eller DD.MM.YYYY.") from exc


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


def _parse_execute_at(value):
    raw_value = (value or "").strip()
    if not raw_value:
        return None
    normalized = raw_value.replace("T", " ")
    try:
        parsed = datetime.fromisoformat(raw_value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed.replace(second=0, microsecond=0)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    raise ValueError("Tidspunkt for gjennomføring må være YYYY-MM-DD HH:MM.")


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
        "booking_enabled": True,
    }


def find_golfbox_availability_for_courses(
    courses,
    players=2,
    play_date=None,
    time_from="15:00",
    time_to="17:00",
    user=None,
):
    course_names = courses or [DEFAULT_GOLFBOX_COURSE]
    results = []
    unavailable_messages = []
    for course_name in course_names:
        result = find_golfbox_availability(
            course=course_name,
            players=players,
            play_date=play_date,
            time_from=time_from,
            time_to=time_to,
            user=user,
        )
        if result["status"] == "ok":
            results.append(result)
        else:
            unavailable_messages.append(result.get("message") or f"Fant ikke {course_name}.")

    available_slots = []
    for result in results:
        available_slots.extend(result.get("available_slots", []))
    available_slots = sorted(available_slots, key=lambda slot: (slot["date"], slot["time"], slot["course"]))

    requested_date = _parse_date(play_date)
    start_time = _parse_time(time_from, "time_from")
    end_time = _parse_time(time_to, "time_to")
    return {
        "status": "ok" if results else "unsupported_course",
        "course": ", ".join(course_names),
        "courses": [result["course"] for result in results] or course_names,
        "players": int(players),
        "date": requested_date.isoformat(),
        "time_from": start_time.strftime("%H:%M"),
        "time_to": end_time.strftime("%H:%M"),
        "available_slots": available_slots,
        "booking_enabled": len(results) == 1 and results[0].get("booking_enabled"),
        "message": " ".join(unavailable_messages),
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
    return _parse_grid_slots(
        response.text,
        requested_date,
        start_time,
        end_time,
        player_count,
        course_name,
        club_guid,
        resource_guid,
    )


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


def _parse_grid_slots(html_text, requested_date, start_time, end_time, player_count, course_name, club_guid, resource_guid):
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
                    "club_guid": club_guid,
                    "resource_guid": resource_guid,
                    "date": requested_date.isoformat(),
                    "source": "GolfBox",
                }
            )
    return sorted(slots, key=lambda slot: (slot["date"], slot["time"], slot["course"]))


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


def _fetch_memberships(client, frontpage_html):
    current_identity = _parse_identity(frontpage_html)
    current_club_name = current_identity.get("club_name")
    switch_response = client.get(f"{GOLFBOX_BASE_URL}/site/security/switchClub.asp")
    switch_response.raise_for_status()
    switch_url = str(switch_response.url)
    clubs = _parse_switch_clubs(switch_response.text)
    memberships = []
    original_club_guid = None
    for club in clubs:
        if club["selected"]:
            original_club_guid = club["club_guid"]
        response = client.post(
            switch_url,
            data={
                "command": "switchClub",
                "commandValue": club["club_guid"],
            },
        )
        response.raise_for_status()
        identity = _parse_identity(response.text)
        if identity.get("member_number") and _normalize_name(identity.get("club_name")) == _normalize_name(club["club_name"]):
            memberships.append(
                {
                    "club_name": identity.get("club_name") or club["club_name"],
                    "club_guid": club["club_guid"],
                    "member_number": identity["member_number"],
                    "player_name": identity.get("player_name"),
                }
            )
    if original_club_guid:
        client.post(
            switch_url,
            data={
                "command": "switchClub",
                "commandValue": original_club_guid,
            },
        )
    elif current_club_name:
        for membership in memberships:
            if membership["club_name"] == current_club_name:
                client.post(
                    switch_url,
                    data={
                        "command": "switchClub",
                        "commandValue": membership["club_guid"],
                    },
                )
                break
    return _dedupe_memberships(memberships)


def _switch_club(client, club_guid):
    if not club_guid:
        return {}
    switch_response = client.get(f"{GOLFBOX_BASE_URL}/site/security/switchClub.asp")
    switch_response.raise_for_status()
    response = client.post(
        str(switch_response.url),
        data={
            "command": "switchClub",
            "commandValue": club_guid,
        },
    )
    response.raise_for_status()
    return _parse_identity(response.text)


def _parse_switch_clubs(page_html):
    clubs = []
    for row_match in re.finditer(r"<tr>\s*<td>(?P<row>.*?)</td>\s*</tr>", page_html, re.IGNORECASE | re.DOTALL):
        row = row_match.group("row")
        club_match = re.search(r"<div class=\"flex-grow-1\">\s*(?P<club>.*?)\s*</div>", row, re.IGNORECASE | re.DOTALL)
        button_match = re.search(
            r"_postBack\('switchClub','(?P<guid>\{[^']+\})'\).*?title=\"\s*(?P<title>[^\"]+)",
            row,
            re.IGNORECASE | re.DOTALL,
        )
        if not club_match or not button_match:
            continue
        club_name = " ".join(re.sub(r"<[^>]+>", " ", club_match.group("club")).split())
        clubs.append(
            {
                "club_name": html.unescape(club_name).strip(),
                "club_guid": html.unescape(button_match.group("guid")).strip(),
                "selected": "valgt" in button_match.group("title").lower(),
            }
        )
    return clubs


def _dedupe_memberships(memberships):
    seen = set()
    result = []
    for membership in memberships:
        key = (membership.get("club_name"), membership.get("member_number"))
        if key in seen:
            continue
        seen.add(key)
        result.append(membership)
    return result


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


def _booking_player_memberships(user, interpretation, club_name=None):
    requested_names = interpretation.get("player_names") or []
    memberships = []
    current_membership = _ensure_membership_for_user(user, club_name)
    current_name = (getattr(user, "player", None).name if getattr(user, "player", None) else getattr(user, "username", "")) or ""
    if not requested_names or any(_name_matches(current_name, name) for name in requested_names):
        memberships.append(current_membership or _self_booking_membership(user, club_name))

    for requested_name in requested_names:
        if _name_matches(current_name, requested_name):
            continue
        membership = _membership_for_player_name(requested_name, club_name)
        if membership:
            memberships.append(membership)

    deduped = []
    seen_numbers = set()
    for membership in memberships:
        number = membership.get("member_number")
        if number in seen_numbers:
            continue
        seen_numbers.add(number)
        deduped.append(membership)
    return deduped[:4]


def _ensure_membership_for_user(user, club_name=None):
    membership = _membership_for_user(user, club_name)
    if membership or not user_has_golfbox_credentials(user):
        return membership
    credentials = _credentials_for_user(user)
    try:
        with httpx.Client(follow_redirects=True, timeout=25, headers={"User-Agent": "Mozilla/5.0"}) as client:
            frontpage_html = _login(client, credentials)
            memberships = _fetch_memberships(client, frontpage_html)
    except (ValueError, httpx.HTTPError):
        return None
    if memberships:
        user.golfbox_memberships_json = json.dumps(memberships, ensure_ascii=False)
        identity = _parse_identity(frontpage_html)
        if identity.get("player_name"):
            user.golfbox_player_name = identity.get("player_name")
        if identity.get("club_name"):
            user.golfbox_home_club_name = identity.get("club_name")
        if identity.get("member_number"):
            user.golfbox_member_number = identity.get("member_number")
        user.golfbox_credentials_updated_at = server_now()
        db.session.commit()
    return _membership_for_user(user, club_name)


def _self_booking_membership(user, club_name=None):
    if not user:
        return None
    return {
        "player_name": getattr(user.player, "name", None) or user.golfbox_player_name or user.username,
        "member_number": "",
        "club_name": club_name or user.golfbox_home_club_name or "",
        "is_current_user": True,
    }


def _membership_for_user(user, club_name=None):
    if not user:
        return None
    requested_club_key = _normalize_name(club_name)
    for membership in _user_memberships(user):
        if _club_names_match(requested_club_key, membership.get("club_name")):
            return {
                "player_name": membership.get("player_name") or user.player.name,
                "member_number": membership["member_number"],
                "club_name": membership["club_name"],
            }
    home_club_key = _normalize_name(user.golfbox_home_club_name)
    if user.golfbox_member_number and _club_names_match(requested_club_key, home_club_key):
        return {
            "player_name": user.golfbox_player_name or user.player.name,
            "member_number": user.golfbox_member_number,
            "club_name": user.golfbox_home_club_name,
        }
    return None


def _club_names_match(requested_club_key, membership_club):
    if not requested_club_key:
        return True
    membership_key = _normalize_name(membership_club)
    if not membership_key:
        return False
    if requested_club_key in membership_key or membership_key in requested_club_key:
        return True
    ignored = {"golf", "golfklubb", "gk", "hull", "bane", "bla", "blå", "gul", "rod", "rød"}
    requested_words = {word for word in requested_club_key.split() if len(word) > 2 and word not in ignored}
    membership_words = {word for word in membership_key.split() if len(word) > 2 and word not in ignored}
    return bool(requested_words and membership_words and requested_words.intersection(membership_words))


def _membership_for_player_name(player_name, club_name=None):
    from models import User

    users = User.query.all()
    for user in users:
        candidate_names = [user.username]
        if user.player:
            candidate_names.append(user.player.name)
        if any(_name_matches(candidate, player_name) for candidate in candidate_names):
            membership = _membership_for_user(user, club_name)
            if membership:
                return membership
    return None


def _name_matches(candidate, requested):
    candidate_key = _normalize_name(candidate)
    requested_key = _normalize_name(requested)
    if not candidate_key or not requested_key:
        return False
    return candidate_key == requested_key or requested_key in candidate_key or candidate_key in requested_key


def _book_slot(credentials, user, booking_date, booking_time, player_memberships, club_guid, resource_guid, course_name):
    booking_start = f"{booking_date.strftime('%Y%m%d')}T{booking_time.strftime('%H%M%S')}"
    with httpx.Client(
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        _login(client, credentials)
        first_membership = (player_memberships or [{}])[0]
        switch_club_guid = first_membership.get("club_guid") or club_guid
        selected_identity = _switch_club(client, switch_club_guid)
        window_response = client.get(
            f"{GOLFBOX_BASE_URL}/site/my_golfbox/ressources/booking/window.asp",
            params={
                "Ressource_GUID": resource_guid,
                "Booking_Start": booking_start,
                "club_GUID": club_guid,
            },
        )
        window_response.raise_for_status()
        validation = _validate_booking_window(window_response.text, user, player_memberships, course_name, selected_identity)
        if validation["status"] != "ok":
            _cleanup_booking_lock(client, booking_start, resource_guid)
            return validation

        form_data = _form_inputs(window_response.text)
        for index, membership in enumerate((player_memberships or [])[1:], start=1):
            form_data[f"txt_MemberClubID_{index}"] = membership["member_number"]
            form_data[f"chk_IsGuest_{index}"] = "0"
            form_data[f"GBDropDown_SelectedOption_ddlUnion_{index}"] = "NO"
        form_data["command"] = "next"
        form_data["commandValue"] = ""
        submit_response = client.post(
            str(window_response.url),
            data=form_data,
        )
        submit_response.raise_for_status()
        if _booking_response_requires_payment(submit_response.text):
            _cleanup_booking_lock(client, booking_start, resource_guid)
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
        "course": course_name,
        "date": booking_date.isoformat(),
        "time": booking_time.strftime("%H:%M"),
        "players": len(player_memberships or []) or 1,
        "message": f"Bookingen er sendt til GolfBox for {course_name} {booking_date.isoformat()} kl. {booking_time.strftime('%H:%M')}.",
        "available_slots": [],
    }


def _book_ballerud_slot(credentials, user, booking_date, booking_time, player_memberships):
    return _book_slot(
        credentials,
        user,
        booking_date,
        booking_time,
        player_memberships,
        BALLERUD_CLUB_GUID,
        BALLERUD_RESSOURCE_GUID,
        DEFAULT_GOLFBOX_COURSE,
    )


def _validate_booking_window(page_html, user, player_memberships, course_name, selected_identity=None):
    page_text = " ".join(re.sub(r"<[^>]+>", " ", page_html).split())
    if "Tiden er låst" in page_text:
        return {
            "intent": "create_booking",
            "status": "booking_failed",
            "message": "Starttiden er låst i GolfBox akkurat nå. Prøv igjen om litt.",
            "available_slots": [],
        }
    first_membership = (player_memberships or [{}])[0]
    member_number = (first_membership.get("member_number") or "").strip()
    expected_club = first_membership.get("club_name") or (selected_identity or {}).get("club_name")
    if expected_club and not _club_names_match(_normalize_name(course_name), expected_club):
        return {
            "intent": "create_booking",
            "status": "wrong_club",
            "message": f"GolfBox står i {expected_club}, men bookingen gjelder {course_name}. Jeg stoppet bookingen.",
            "available_slots": [],
        }
    if member_number and f"Medlemsnummer: {member_number}" not in page_text and f'value="{member_number}"' not in page_html:
        return {
            "intent": "create_booking",
            "status": "wrong_membership",
            "message": f"GolfBox viser ikke riktig medlemsnummer for {course_name}. Jeg stoppet bookingen.",
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


def _cleanup_booking_lock(client, booking_start, resource_guid=BALLERUD_RESSOURCE_GUID):
    try:
        client.post(
            f"{GOLFBOX_BASE_URL}/site/ressources/booking/cleanup.asp",
            data={
                "Ressource_GUID": resource_guid,
                "Booking_Start": booking_start,
            },
        )
    except httpx.HTTPError:
        return


def process_golfbox_prompt(prompt, user=None, pending_booking=None, pending_cancel=None):
    cleaned_prompt = " ".join((prompt or "").strip().split())
    if not cleaned_prompt:
        raise ValueError("Skriv hva du vil sjekke i GolfBox.")

    prompt_lower = cleaned_prompt.lower()
    if pending_booking and _is_confirmation_prompt(prompt_lower):
        return confirm_golfbox_booking(pending_booking, user=user)
    if pending_cancel and _is_confirmation_prompt(prompt_lower):
        return cancel_golfbox_booking(
            user,
            pending_cancel.get("booking_guid"),
            booking_start=pending_cancel.get("booking_start"),
            resource_guid=pending_cancel.get("resource_guid"),
        )
    profile_result = _profile_info_result(prompt_lower, user)
    if profile_result:
        profile_result["prompt"] = cleaned_prompt
        return profile_result

    interpretation = _interpret_prompt_with_openai(cleaned_prompt, user)
    intent = interpretation["intent"]
    if intent == "cancel_booking":
        return _cancel_booking_result(interpretation, cleaned_prompt, user)

    players = interpretation["players"]
    play_date = interpretation["date"]
    time_from = interpretation["time_from"]
    time_to = interpretation["time_to"]
    courses = interpretation["courses"]
    if intent == "create_booking" and interpretation.get("execute_at"):
        return _scheduled_booking_result(interpretation, cleaned_prompt, user)

    result = find_golfbox_availability_for_courses(
        courses=courses,
        players=players,
        play_date=play_date,
        time_from=time_from,
        time_to=time_to,
        user=user,
    )
    result["intent"] = intent
    result["prompt"] = cleaned_prompt
    result["interpretation"] = interpretation
    if intent == "create_booking":
        result = _booking_confirmation_result(result, interpretation, user)
    return result


def _interpret_prompt_with_openai(prompt, user):
    if not os.environ.get("OPENAI_API_KEY"):
        _load_env_file()
    if not os.environ.get("OPENAI_API_KEY"):
        return _fallback_prompt_interpretation(prompt)

    today = server_now().date().isoformat()
    prompt_text = (
        f"I dag er {today}. Tolk golfmelding til JSON: "
        '{"intent":"find_availability|create_booking|cancel_booking|unknown",'
        '"courses":[],"area":"","players":2,"player_names":[],'
        '"date":"YYYY-MM-DD","time_from":"HH:MM","time_to":"HH:MM",'
        '"execute_at":"","recurrence":{"frequency":"","weekday":"","execute_time":""}}. '
        "Regler: book/bestill/reserver=create_booking, ledig=find_availability, "
        "avbestill/kanseller=cancel_booking. Oslo-området: area=oslo og courses=[]. "
        "Flere baner listes i courses. Kjente korte banenavn: Ballerud, Oslo, Haga, "
        "Bærum, Grini, Asker, Oppegård, Drøbak. Mangler dato: i dag. "
        "Mangler tidsrom: 06:00-22:00. Enkelt klokkeslett: time_from=klokkeslett "
        "og time_to=30 minutter senere. Mangler spillere: 2. "
        "Hvis brukeren ber om fast/repeterende booking, sett recurrence.frequency=weekly, "
        "recurrence.weekday til engelsk ukedag og recurrence.execute_time til klokkeslettet jobben skal kjøre. "
        "Hvis brukeren ber om at bookingen skal gjennomføres senere, sett execute_at "
        "til lokal ISO-dato og tid for selve gjennomføringen, ikke spilletiden. Bare JSON. "
        f"Melding: {prompt}"
    )
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.responses.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4.1"),
        input=[{
            "role": "user",
            "content": [{"type": "input_text", "text": prompt_text}],
        }],
    )
    try:
        data = _extract_json(response.output_text)
    except (ValueError, json.JSONDecodeError):
        return _fallback_prompt_interpretation(prompt)
    try:
        return _normalize_interpretation(data, prompt, user)
    except ValueError:
        return _fallback_prompt_interpretation(prompt)


def _extract_json(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Fant ikke JSON i AI-respons.")
    return json.loads(text[start:end + 1])


def _normalize_interpretation(data, prompt, user=None):
    fallback = _fallback_prompt_interpretation(prompt)
    prompt_lower = prompt.lower()
    intent = str(data.get("intent") or fallback["intent"]).strip()
    if intent not in {"find_availability", "create_booking", "cancel_booking", "unknown"}:
        intent = fallback["intent"]

    courses = data.get("courses")
    if not isinstance(courses, list):
        courses = fallback["courses"]
    courses = [str(course).strip() for course in courses if str(course).strip()]
    area = str(data.get("area") or "").strip().lower()
    if not courses and area == "oslo":
        courses = list(OSLO_AREA_COURSES)
    if not courses:
        courses = fallback["courses"]

    player_names = data.get("player_names")
    if not isinstance(player_names, list):
        player_names = []
    player_names = _clean_player_names(player_names, user)

    try:
        players = int(data.get("players") or fallback["players"])
    except (TypeError, ValueError):
        players = fallback["players"]
    players = max(1, min(4, players))
    if _solo_booking_prompt(prompt_lower):
        players = 1
        player_names = []
    elif _prompt_references_current_user(prompt_lower) and not _prompt_has_explicit_player_count(prompt_lower):
        players = min(4, max(1, len(player_names) + 1))

    play_date = str(data.get("date") or fallback["date"]).strip()
    time_from = str(data.get("time_from") or fallback["time_from"]).strip()
    time_to = str(data.get("time_to") or fallback["time_to"]).strip()
    execute_at = str(data.get("execute_at") or fallback.get("execute_at") or "").strip()
    recurrence = _normalize_recurrence(data.get("recurrence") or fallback.get("recurrence") or {}, prompt_lower)
    _parse_date(play_date)
    parsed_from = _parse_time(time_from, "time_from")
    parsed_to = _parse_time(time_to, "time_to")
    if parsed_to <= parsed_from:
        time_to = _time_after(parsed_from, minutes=30)
    if execute_at:
        _parse_execute_at(execute_at)
    if recurrence:
        execute_at = _next_weekday_run(recurrence["execute_weekday"], recurrence["execute_time"]).strftime("%Y-%m-%d %H:%M")

    return {
        "intent": intent if intent != "unknown" else "find_availability",
        "courses": courses,
        "area": area,
        "players": players,
        "player_names": player_names,
        "date": play_date,
        "time_from": time_from,
        "time_to": time_to,
        "execute_at": execute_at,
        "recurrence": recurrence,
    }


def _fallback_prompt_interpretation(prompt):
    prompt_lower = prompt.lower()
    if any(word in prompt_lower for word in ("avbestill", "avbook", "kanseller")):
        intent = "cancel_booking"
    elif any(word in prompt_lower for word in ("bestill", "book", "reserver")):
        intent = "create_booking"
    else:
        intent = "find_availability"
    courses = _courses_from_prompt(prompt)
    time_from, time_to = _time_window_from_prompt(prompt_lower)
    players = _players_from_prompt(prompt_lower)
    if _prompt_references_current_user(prompt_lower) and not _prompt_has_explicit_player_count(prompt_lower):
        players = 1
    return {
        "intent": intent,
        "courses": courses,
        "area": "oslo" if "oslo-området" in prompt_lower or "osloområdet" in prompt_lower else "",
        "players": players,
        "player_names": [],
        "date": _date_from_prompt(prompt_lower),
        "time_from": time_from,
        "time_to": time_to,
        "execute_at": _execute_at_from_prompt(prompt_lower),
        "recurrence": _recurrence_from_prompt(prompt_lower),
    }


def _profile_info_result(prompt_lower, user):
    membership_words = ("medlemsnummer", "medlems nr", "medlemskap", "golfbox")
    own_words = ("mitt", "min", "meg", "jeg")
    if not any(word in prompt_lower for word in membership_words) or not any(word in prompt_lower for word in own_words):
        return None
    summary = golfbox_connection_summary(user)
    if not summary["connected"]:
        return {
            "intent": "profile_info",
            "status": "profile_info",
            "message": "Jeg har ikke GolfBox-innlogging lagret på brukeren din ennå. Legg den inn på Min side først.",
            "available_slots": [],
        }
    memberships = summary.get("memberships") or []
    if memberships:
        membership_text = ", ".join(f"{item['club_name']}: {item['member_number']}" for item in memberships)
    elif summary.get("member_number"):
        membership_text = f"{summary.get('club_name')}: {summary.get('member_number')}"
    else:
        membership_text = "Jeg har GolfBox-innloggingen din, men fant ikke medlemsnummer på profilen."
    return {
        "intent": "profile_info",
        "status": "profile_info",
        "message": f"Ja. Du er koblet til som {summary.get('player_name') or summary.get('username')}. Lagret medlemskap: {membership_text}.",
        "available_slots": [],
    }


def upcoming_golfbox_bookings(user):
    credentials = _credentials_for_user(user)
    if not credentials:
        return {
            "status": "configuration_required",
            "message": "GolfBox-innlogging mangler.",
            "bookings": [],
        }
    try:
        with httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as client:
            _login(client, credentials)
            response = client.get(f"{GOLFBOX_BASE_URL}{GOLFBOX_MY_TIMES_PATH}")
            response.raise_for_status()
            return {
                "status": "ok",
                "message": "",
                "bookings": _parse_my_times(response.text),
            }
    except (ValueError, httpx.HTTPError) as exc:
        return {
            "status": "error",
            "message": f"Kunne ikke hente kommende GolfBox-bookinger: {exc}",
            "bookings": [],
        }


def cancel_golfbox_booking(user, booking_guid, booking_start=None, resource_guid=None):
    credentials = _credentials_for_user(user)
    if not credentials:
        raise ValueError("GolfBox-innlogging mangler.")
    booking_guid = (booking_guid or "").strip()
    booking_start = (booking_start or "").strip()
    resource_guid = (resource_guid or "").strip()
    if not booking_guid:
        raise ValueError("Mangler GolfBox-booking.")

    with httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as client:
        _login(client, credentials)
        my_times = client.get(f"{GOLFBOX_BASE_URL}{GOLFBOX_MY_TIMES_PATH}")
        my_times.raise_for_status()
        bookings = _parse_my_times(my_times.text)
        selected = next(
            (
                booking for booking in bookings
                if booking.get("can_cancel")
                and booking.get("booking_guid") == booking_guid
                and (not booking_start or booking.get("booking_start") == booking_start)
                and (not resource_guid or booking.get("resource_guid") == resource_guid)
            ),
            None,
        )
        if not selected:
            raise ValueError("Fant ikke en avbestillbar GolfBox-booking som matcher valget.")
        response = client.get(
            f"{GOLFBOX_BASE_URL}/site/ressources/booking/deletePlayer.asp",
            params={
                "booking_guid": booking_guid,
                "rUrl": GOLFBOX_MY_TIMES_PATH,
            },
        )
        response.raise_for_status()
    return {
        "intent": "cancel_booking",
        "status": "booking_cancelled",
        "message": (
            f"Bookingen på {selected.get('course')} {selected.get('date')} "
            f"kl. {selected.get('time')} er avbestilt i GolfBox."
        ),
        "booking": selected,
        "available_slots": [],
    }


def _parse_my_times(page_html):
    current_member_guid = _current_member_guid_from_my_times(page_html)
    bookings = []
    for raw_block in page_html.split('<div class="border border-success bg-selected rounded')[1:]:
        block = '<div class="border border-success bg-selected rounded' + raw_block
        table_end = block.find("</table>")
        if table_end == -1:
            continue
        block = block[:table_end + len("</table>")]
        header_html = block.split("<table", 1)[0]
        date_text = _first_match(r"(\d{2}\.\d{2}\.\d{4})", header_html)
        time_text = _first_match(r"\b(\d{1,2}:\d{2})\b", _plain_text(header_html))
        if not date_text or not time_text:
            continue
        resource_guid = _first_match(r"Ressource_GUID=(\{[^}&]+\})", block)
        booking_start = _first_match(r"Booking_Start=(\d{8}T\d{6})", block)
        players = _parse_my_times_players(block, current_member_guid)
        own_row = next((player for player in players if player.get("is_current_user") and player.get("booking_guid")), None)
        bookings.append(
            {
                "source": "golfbox",
                "source_label": "GolfBox",
                "club": _icon_text(header_html, "home_icon"),
                "course": _icon_text(header_html, "golfcourse_icon"),
                "date": _norwegian_date_to_iso(date_text),
                "display_date": date_text,
                "time": time_text,
                "players": [player["name"] for player in players if player.get("name")],
                "player_rows": players,
                "resource_guid": resource_guid,
                "booking_start": booking_start,
                "booking_guid": own_row.get("booking_guid") if own_row else None,
                "can_cancel": bool(own_row),
            }
        )
    return bookings


def _current_member_guid_from_my_times(page_html):
    return _first_match(r"if\('(\{[^']+\})'\s*==\s*member_guid\)", page_html)


def _parse_my_times_players(block, current_member_guid):
    players = []
    for row_match in re.finditer(r"<tr>(?P<row>.*?)</tr>", block, re.IGNORECASE | re.DOTALL):
        row = row_match.group("row")
        name = _first_match(r'<div class="fw-bold">\s*(.*?)\s*</div>', row)
        if not name:
            continue
        delete_match = re.search(
            r"deletePlayer\('(?P<member_guid>\{[^']+\})','(?P<booking_guid>\{[^']+\})'\)",
            row,
            re.IGNORECASE,
        )
        member_guid = delete_match.group("member_guid") if delete_match else None
        players.append(
            {
                "name": _plain_text(name),
                "member_number": _first_match(r"(\d{1,5}-\d{1,8})", row),
                "club": _plain_cells(row)[3] if len(_plain_cells(row)) > 3 else "",
                "status": _plain_cells(row)[5] if len(_plain_cells(row)) > 5 else "",
                "member_guid": member_guid,
                "booking_guid": delete_match.group("booking_guid") if delete_match else None,
                "is_current_user": bool(current_member_guid and member_guid == current_member_guid),
            }
        )
    return players


def _icon_text(html_text, icon_id):
    match = re.search(
        rf'{re.escape(icon_id)}.*?</svg>\s*</div>\s*(?P<value>.*?)\s*</div>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    return _plain_text(match.group("value")) if match else ""


def _plain_cells(row_html):
    cells = []
    for cell_match in re.finditer(r"<td\b[^>]*>(?P<cell>.*?)</td>", row_html, re.IGNORECASE | re.DOTALL):
        cells.append(_plain_text(cell_match.group("cell")))
    return cells


def _plain_text(html_text):
    return html.unescape(" ".join(re.sub(r"<[^>]+>", " ", html_text or "").split())).strip()


def _first_match(pattern, text):
    match = re.search(pattern, text or "", re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return html.unescape(match.group(1)).strip()


def _norwegian_date_to_iso(value):
    try:
        return datetime.strptime(value, "%d.%m.%Y").date().isoformat()
    except ValueError:
        return value


def _cancel_booking_result(interpretation, prompt, user):
    upcoming = upcoming_golfbox_bookings(user)
    if upcoming["status"] != "ok":
        return {
            "intent": "cancel_booking",
            "status": upcoming["status"],
            "message": upcoming["message"],
            "available_slots": [],
            "bookings": [],
        }
    bookings = [booking for booking in upcoming["bookings"] if booking.get("can_cancel")]
    matches = _matching_cancel_bookings(bookings, interpretation, prompt)
    if not matches:
        return {
            "intent": "cancel_booking",
            "status": "booking_cancel_not_found",
            "message": "Jeg fant ingen kommende GolfBox-bookinger som matcher avbestillingen.",
            "available_slots": [],
            "bookings": bookings,
        }
    if len(matches) == 1:
        booking = matches[0]
        return {
            "intent": "cancel_booking",
            "status": "cancel_confirmation_required",
            "message": (
                f"Jeg kan avbestille {booking.get('course')} {booking.get('date')} "
                f"kl. {booking.get('time')} i GolfBox. Bekreft før jeg fjerner deg fra starttiden."
            ),
            "pending_cancel": _cancel_payload(booking),
            "bookings": matches,
            "available_slots": [],
        }
    return {
        "intent": "cancel_booking",
        "status": "cancel_booking_choices",
        "message": "Jeg fant flere mulige bookinger. Velg hvilken som skal avbestilles.",
        "bookings": matches,
        "available_slots": [],
    }


def _matching_cancel_bookings(bookings, interpretation, prompt):
    prompt_lower = prompt.lower()
    matches = list(bookings)
    requested_courses = interpretation.get("courses") or []
    if requested_courses and requested_courses != [DEFAULT_GOLFBOX_COURSE] or any(
        _normalize_name(course) in _normalize_name(prompt) for course in requested_courses
    ):
        matches = [
            booking for booking in matches
            if any(
                _club_names_match(_normalize_name(course), booking.get("course"))
                or _club_names_match(_normalize_name(course), booking.get("club"))
                for course in requested_courses
            )
        ]
    if _prompt_has_date(prompt_lower):
        requested_date = _parse_date(interpretation.get("date")).isoformat()
        matches = [booking for booking in matches if booking.get("date") == requested_date]
    if _prompt_has_time(prompt_lower):
        requested_time = _parse_time(interpretation.get("time_from"), "time_from").strftime("%H:%M")
        matches = [booking for booking in matches if booking.get("time") == requested_time]
    return matches


def _prompt_has_date(prompt_lower):
    return bool(
        re.search(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\.\d{1,2}\.\d{4}\b", prompt_lower)
        or any(value in prompt_lower for value in ("i dag", "idag", "i morgen", "imorgen"))
    )


def _prompt_has_time(prompt_lower):
    return bool(re.search(r"(?:kl\.?|rundt|mellom|fra|etter|før|til)\s*\d{1,2}(?::?\d{2})?", prompt_lower))


def _cancel_payload(booking):
    return {
        "booking_guid": booking.get("booking_guid"),
        "booking_start": booking.get("booking_start"),
        "resource_guid": booking.get("resource_guid"),
        "course": booking.get("course"),
        "date": booking.get("date"),
        "time": booking.get("time"),
    }


def _normalize_recurrence(value, prompt_lower):
    if not isinstance(value, dict):
        value = {}
    frequency = str(value.get("frequency") or "").strip().lower()
    weekday_value = str(value.get("weekday") or "").strip().lower()
    execute_time = str(value.get("execute_time") or "").strip()
    fallback = _recurrence_from_prompt(prompt_lower)
    if frequency not in {"weekly", "hver_uke", "ukentlig"}:
        return fallback
    execute_weekday = _weekday_number(weekday_value)
    if execute_weekday is None:
        return fallback
    if not execute_time:
        return fallback
    parsed_time = _parse_time(execute_time, "execute_time")
    return {
        "frequency": "weekly",
        "execute_weekday": execute_weekday,
        "execute_time": parsed_time.strftime("%H:%M"),
    }


def _recurrence_from_prompt(prompt_lower):
    if not any(word in prompt_lower for word in ("hver", "ukentlig", "fast", "repeter")):
        return {}
    weekday_pattern = "|".join(WEEKDAY_NAMES)
    match = re.search(
        rf"(?:hver|ukentlig|fast)[^,.;]*?({weekday_pattern})[^,.;]*?(?:kl\.?\s*)?(\d{{1,2}})(?::?(\d{{2}}))?",
        prompt_lower,
    )
    if not match:
        return {}
    weekday_text, hour, minute = match.groups()
    return {
        "frequency": "weekly",
        "execute_weekday": _weekday_number(weekday_text),
        "execute_time": _format_prompt_time(hour, minute),
    }


def _weekday_number(value):
    normalized = _normalize_name(value)
    english = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    if normalized in english:
        return english[normalized]
    for index, weekday in enumerate(WEEKDAY_NAMES):
        if normalized == weekday:
            return index
    return None


def _next_weekday_run(weekday, time_value, from_dt=None):
    now = from_dt or server_now()
    parsed_time = _parse_time(time_value, "execute_time")
    days_ahead = (weekday - now.weekday()) % 7
    candidate = datetime.combine(now.date() + timedelta(days=days_ahead), parsed_time)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def _prompt_references_current_user(prompt_lower):
    return bool(re.search(r"\b(jeg|meg|mitt|min)\b", prompt_lower))


def _solo_booking_prompt(prompt_lower):
    solo_patterns = (
        r"\b(book|booke|booker|bestill|reserver)[^,.;]*(meg|inn meg)\b",
        r"\bkun\s+meg\b",
        r"\bbare\s+meg\b",
        r"\bingen\s+flere\s+enn\s+meg\b",
        r"\bikke\s+booke\s+inn\s+noen\s+flere\s+enn\s+meg\b",
        r"\bikke\s+noen\s+flere\s+enn\s+meg\b",
    )
    return any(re.search(pattern, prompt_lower) for pattern in solo_patterns)


def _prompt_has_explicit_player_count(prompt_lower):
    return bool(re.search(r"\b\d+\s*(person|personer|spiller|spillere)\b", prompt_lower))


def _clean_player_names(player_names, user=None):
    ignored = {"jeg", "meg", "mitt", "min", "myself", "me"}
    current_names = []
    if user:
        current_names.append(getattr(user, "username", ""))
        if getattr(user, "player", None):
            current_names.append(user.player.name)
    cleaned = []
    for name in player_names:
        value = str(name).strip()
        if not value or _normalize_name(value) in ignored:
            continue
        if any(_name_matches(current_name, value) for current_name in current_names if current_name):
            continue
        cleaned.append(value)
    return cleaned


def _is_confirmation_prompt(prompt_lower):
    return prompt_lower in {"ja", "ja takk", "bekreft", "book", "bestill", "ok", "kjør"} or "bekreft booking" in prompt_lower


def _booking_confirmation_result(availability_result, interpretation, user):
    if availability_result["status"] != "ok":
        return availability_result
    if not availability_result.get("booking_enabled"):
        availability_result["status"] = "booking_unsupported_course"
        availability_result["message"] = "Jeg kan bare booke når prompten peker på én konkret bane."
        return availability_result
    if not availability_result.get("available_slots"):
        return availability_result
    selected_slot = availability_result["available_slots"][0]
    player_memberships = _booking_player_memberships(user, interpretation, selected_slot["course"])
    if len(player_memberships) != availability_result["players"]:
        availability_result["status"] = "needs_player_details"
        if availability_result["players"] == 1:
            availability_result["message"] = (
                f"Jeg fant ikke GolfBox-medlemskapet ditt for {selected_slot['course']}. "
                "Åpne Min side og lagre GolfBox-innloggingen på nytt, så henter jeg klubbmedlemskapene dine på nytt."
            )
        else:
            availability_result["message"] = (
                "Jeg trenger navn på medspillerne, og de må ha lagret GolfBox-medlemskap for denne klubben på Min side. "
                f"Skriv for eksempel: Book {selected_slot['course']} for Kristian og Erik i morgen mellom 15 og 17."
            )
        return availability_result
    pending = {
        "course": selected_slot["course"],
        "date": selected_slot["date"],
        "time": selected_slot["time"],
        "players": availability_result["players"],
        "player_memberships": player_memberships,
        "club_guid": selected_slot["club_guid"],
        "resource_guid": selected_slot["resource_guid"],
    }
    availability_result["status"] = "confirmation_required"
    availability_result["message"] = (
        f"Jeg kan booke {selected_slot['course']} {selected_slot['date']} kl. {selected_slot['time']} "
        f"for {', '.join(player['player_name'] for player in player_memberships)}. "
        "Bekreft før jeg sender bookingen til GolfBox."
    )
    availability_result["pending_booking"] = pending
    return availability_result


def _scheduled_booking_result(interpretation, prompt, user):
    if not _credentials_for_user(user):
        return {
            "intent": "create_booking",
            "status": "configuration_required",
            "message": "Legg GolfBox-innlogging inn på Min side før du planlegger booking.",
            "available_slots": [],
        }
    courses = interpretation.get("courses") or [DEFAULT_GOLFBOX_COURSE]
    if len(courses) != 1:
        return {
            "intent": "create_booking",
            "status": "booking_unsupported_course",
            "message": "Planlagt booking må peke på én konkret bane.",
            "available_slots": [],
        }
    course_name = courses[0]
    player_memberships = _booking_player_memberships(user, interpretation, course_name)
    if len(player_memberships) != interpretation["players"]:
        if interpretation["players"] == 1:
            return {
                "intent": "create_booking",
                "status": "needs_player_details",
                "message": (
                    f"Jeg fant ikke GolfBox-medlemskapet ditt for {course_name}. "
                    "Åpne Min side og lagre GolfBox-innloggingen på nytt, så henter jeg klubbmedlemskapene dine på nytt."
                ),
                "available_slots": [],
            }
        return {
            "intent": "create_booking",
            "status": "needs_player_details",
            "message": (
                "Jeg trenger navn på medspillerne, og de må ha lagret GolfBox-medlemskap for denne klubben på Min side "
                "før jeg kan planlegge en booking."
            ),
            "available_slots": [],
        }
    if interpretation.get("recurrence"):
        return _recurring_booking_result(interpretation, prompt, user, course_name, player_memberships)
    execute_at = _parse_execute_at(interpretation.get("execute_at"))
    if not execute_at or execute_at <= server_now():
        return {
            "intent": "create_booking",
            "status": "booking_failed",
            "message": "Tidspunktet for gjennomføring må være frem i tid.",
            "available_slots": [],
        }
    play_date = _parse_date(interpretation["date"])
    play_time = _parse_time(interpretation["time_from"], "time_from")

    from models import GolfBoxScheduledBooking

    scheduled = GolfBoxScheduledBooking(
        created_by_user_id=user.id,
        status="scheduled",
        course=course_name,
        play_date=play_date,
        play_time=play_time.strftime("%H:%M"),
        execute_at=execute_at,
        players_json=json.dumps(player_memberships, ensure_ascii=False),
        requested_prompt=prompt,
    )
    db.session.add(scheduled)
    db.session.commit()
    player_text = ", ".join(player["player_name"] for player in player_memberships)
    execute_text = scheduled.execute_at.strftime("%Y-%m-%d %H:%M")
    send_golfbox_booking_email(user, "scheduled", {
        "course": scheduled.course,
        "date": scheduled.play_date.isoformat(),
        "time": scheduled.play_time,
        "execute_at": execute_text,
        "player_memberships": player_memberships,
    })
    return {
        "intent": "create_booking",
        "status": "scheduled_booking_created",
        "scheduled_booking_id": scheduled.id,
        "course": scheduled.course,
        "date": scheduled.play_date.isoformat(),
        "time": scheduled.play_time,
        "execute_at": execute_text,
        "players": len(player_memberships),
        "player_names": [player["player_name"] for player in player_memberships],
        "message": (
            f"Jeg har lagt inn en planlagt booking: {scheduled.course} {scheduled.play_date.isoformat()} "
            f"kl. {scheduled.play_time} for {player_text}. Den gjennomføres {execute_text} "
            "uten ny bekreftelse."
        ),
        "available_slots": [],
    }


def _recurring_booking_result(interpretation, prompt, user, course_name, player_memberships):
    recurrence = interpretation.get("recurrence") or {}
    if recurrence.get("frequency") != "weekly":
        return {
            "intent": "create_booking",
            "status": "booking_failed",
            "message": "Jeg støtter foreløpig ukentlige repeterende bookinger.",
            "available_slots": [],
        }

    from models import GolfBoxRecurringBooking

    execute_weekday = int(recurrence["execute_weekday"])
    execute_time = recurrence["execute_time"]
    next_run_at = _next_weekday_run(execute_weekday, execute_time)
    recurring = GolfBoxRecurringBooking(
        created_by_user_id=user.id,
        status="active",
        course=course_name,
        play_weekday=execute_weekday,
        time_from=interpretation["time_from"],
        time_to=interpretation["time_to"],
        execute_weekday=execute_weekday,
        execute_time=execute_time,
        next_run_at=next_run_at,
        players_json=json.dumps(player_memberships, ensure_ascii=False),
        requested_prompt=prompt,
    )
    db.session.add(recurring)
    db.session.commit()
    player_text = ", ".join(player["player_name"] for player in player_memberships)
    return {
        "intent": "create_booking",
        "status": "recurring_booking_created",
        "recurring_booking_id": recurring.id,
        "course": recurring.course,
        "time_from": recurring.time_from,
        "time_to": recurring.time_to,
        "execute_at": recurring.next_run_at.strftime("%Y-%m-%d %H:%M"),
        "players": len(player_memberships),
        "player_names": [player["player_name"] for player in player_memberships],
        "message": (
            f"Jeg har lagt inn fast ukentlig booking: {recurring.course} hver "
            f"{WEEKDAY_NAMES[execute_weekday]} mellom {recurring.time_from} og {recurring.time_to} "
            f"for {player_text}. Første forsøk kjøres {recurring.next_run_at:%Y-%m-%d %H:%M}."
        ),
        "available_slots": [],
    }


def confirm_golfbox_booking(pending_booking, user=None, notification_event="confirmed"):
    credentials = _credentials_for_user(user)
    if not credentials:
        return {
            "intent": "create_booking",
            "status": "configuration_required",
            "message": "Legg GolfBox-innlogging inn på Min side før du booker.",
            "available_slots": [],
        }
    booking_date = date.fromisoformat(pending_booking["date"])
    booking_time = _parse_time(pending_booking["time"], "booking_time")
    course_name = pending_booking.get("course") or DEFAULT_GOLFBOX_COURSE
    club_guid = pending_booking.get("club_guid")
    resource_guid = pending_booking.get("resource_guid")
    if "ballerud" in course_name.lower() and (not club_guid or not resource_guid):
        club_guid = BALLERUD_CLUB_GUID
        resource_guid = BALLERUD_RESSOURCE_GUID
        course_name = DEFAULT_GOLFBOX_COURSE
    if not club_guid or not resource_guid:
        resolved = _resolve_course(credentials, course_name)
        if not resolved:
            return {
                "intent": "create_booking",
                "status": "unsupported_course",
                "message": f"Jeg fant ikke {course_name} i GolfBox-listen.",
                "available_slots": [],
            }
        club_guid = resolved["club_guid"]
        resource_guid = resolved["resource_guid"]
        course_name = resolved["course"]
    result = _book_slot(
        credentials,
        user,
        booking_date,
        booking_time,
        pending_booking.get("player_memberships", []),
        club_guid,
        resource_guid,
        course_name,
    )
    if result.get("status") == "booking_created":
        send_golfbox_booking_email(user, notification_event, {
            "course": pending_booking.get("course") or result.get("course") or DEFAULT_GOLFBOX_COURSE,
            "date": result.get("date") or pending_booking.get("date"),
            "time": result.get("time") or pending_booking.get("time"),
            "player_memberships": pending_booking.get("player_memberships", []),
        })
    return result


def upcoming_golfbox_scheduled_bookings(user):
    from models import GolfBoxRecurringBooking, GolfBoxScheduledBooking

    bookings = (
        GolfBoxScheduledBooking.query
        .filter_by(created_by_user_id=user.id)
        .filter(GolfBoxScheduledBooking.status == "scheduled")
        .order_by(GolfBoxScheduledBooking.execute_at.asc(), GolfBoxScheduledBooking.play_date.asc(), GolfBoxScheduledBooking.play_time.asc())
        .all()
    )
    recurring_bookings = (
        GolfBoxRecurringBooking.query
        .filter_by(created_by_user_id=user.id)
        .filter(GolfBoxRecurringBooking.status == "active")
        .order_by(GolfBoxRecurringBooking.next_run_at.asc(), GolfBoxRecurringBooking.course.asc())
        .all()
    )
    return (
        [_scheduled_booking_view(booking) for booking in bookings]
        + [_recurring_booking_view(booking) for booking in recurring_bookings]
    )


def cancel_golfbox_scheduled_booking(booking_id, user, booking_type="scheduled"):
    from models import GolfBoxRecurringBooking, GolfBoxScheduledBooking

    if booking_type == "recurring":
        recurring = GolfBoxRecurringBooking.query.filter_by(id=booking_id, created_by_user_id=user.id).first()
        if not recurring:
            raise ValueError("Fant ikke den faste bookingen.")
        if recurring.status != "active":
            raise ValueError("Denne bookingen kan ikke kanselleres lenger.")
        recurring.status = "cancelled"
        recurring.cancelled_at = server_now()
        db.session.commit()
        return recurring

    booking = GolfBoxScheduledBooking.query.filter_by(id=booking_id, created_by_user_id=user.id).first()
    if not booking:
        raise ValueError("Fant ikke den planlagte bookingen.")
    if booking.status != "scheduled":
        raise ValueError("Denne bookingen kan ikke kanselleres lenger.")
    if server_now() >= booking.execute_at - timedelta(minutes=1):
        raise ValueError("Bookingen kan bare kanselleres frem til ett minutt før gjennomføring.")
    booking.status = "cancelled"
    booking.cancelled_at = server_now()
    db.session.commit()
    return booking


def run_due_golfbox_scheduled_bookings(limit=10):
    from models import GolfBoxRecurringBooking, GolfBoxScheduledBooking

    due_bookings = (
        GolfBoxScheduledBooking.query
        .filter(GolfBoxScheduledBooking.status == "scheduled")
        .filter(GolfBoxScheduledBooking.execute_at <= server_now())
        .order_by(GolfBoxScheduledBooking.execute_at.asc())
        .limit(limit)
        .all()
    )
    results = []
    for booking in due_bookings:
        booking.status = "running"
        booking.updated_at = server_now()
        db.session.commit()
        try:
            player_memberships = json.loads(booking.players_json or "[]")
            pending_booking = {
                "course": booking.course,
                "date": booking.play_date.isoformat(),
                "time": booking.play_time,
                "players": len(player_memberships),
                "player_memberships": player_memberships,
                "club_guid": BALLERUD_CLUB_GUID,
                "resource_guid": BALLERUD_RESSOURCE_GUID,
            }
            result = confirm_golfbox_booking(
                pending_booking,
                user=booking.created_by_user,
                notification_event="scheduled_executed",
            )
            booking.executed_at = server_now()
            booking.result_message = result.get("message")
            booking.error_message = None if result.get("status") == "booking_created" else result.get("message")
            booking.status = "completed" if result.get("status") == "booking_created" else "failed"
            results.append({"id": booking.id, "status": booking.status, "message": result.get("message")})
        except Exception as exc:
            booking.executed_at = server_now()
            booking.status = "failed"
            booking.error_message = str(exc)
            results.append({"id": booking.id, "status": "failed", "message": str(exc)})
        db.session.commit()
    remaining = max(0, limit - len(results))
    if remaining:
        recurring_bookings = (
            GolfBoxRecurringBooking.query
            .filter(GolfBoxRecurringBooking.status == "active")
            .filter(GolfBoxRecurringBooking.next_run_at <= server_now())
            .order_by(GolfBoxRecurringBooking.next_run_at.asc())
            .limit(remaining)
            .all()
        )
        for booking in recurring_bookings:
            results.append(_run_recurring_golfbox_booking(booking))
    return results


def _run_recurring_golfbox_booking(booking):
    try:
        player_memberships = json.loads(booking.players_json or "[]")
        play_date = _next_play_date_for_recurring(booking)
        availability = find_golfbox_availability(
            course=booking.course,
            players=len(player_memberships) or 1,
            play_date=play_date.isoformat(),
            time_from=booking.time_from,
            time_to=booking.time_to,
            user=booking.created_by_user,
        )
        if availability.get("status") != "ok" or not availability.get("available_slots"):
            message = availability.get("message") or "Ingen ledige tider funnet for fast booking."
            status = "no_slot"
        else:
            selected_slot = availability["available_slots"][0]
            pending_booking = {
                "course": selected_slot["course"],
                "date": selected_slot["date"],
                "time": selected_slot["time"],
                "players": len(player_memberships) or 1,
                "player_memberships": player_memberships,
                "club_guid": selected_slot["club_guid"],
                "resource_guid": selected_slot["resource_guid"],
            }
            result = confirm_golfbox_booking(
                pending_booking,
                user=booking.created_by_user,
                notification_event="scheduled_executed",
            )
            message = result.get("message")
            status = result.get("status")
        booking.last_run_at = server_now()
        booking.last_result_message = message
        booking.last_error_message = None if status == "booking_created" else message
        booking.next_run_at = _next_weekday_run(booking.execute_weekday, booking.execute_time, from_dt=server_now() + timedelta(minutes=1))
        booking.updated_at = server_now()
        db.session.commit()
        return {"id": booking.id, "type": "recurring", "status": status, "message": message}
    except Exception as exc:
        booking.last_run_at = server_now()
        booking.last_error_message = str(exc)
        booking.next_run_at = _next_weekday_run(booking.execute_weekday, booking.execute_time, from_dt=server_now() + timedelta(minutes=1))
        booking.updated_at = server_now()
        db.session.commit()
        return {"id": booking.id, "type": "recurring", "status": "failed", "message": str(exc)}


def _next_play_date_for_recurring(booking):
    base = booking.next_run_at.date()
    days_ahead = (booking.play_weekday - base.weekday()) % 7
    return base + timedelta(days=days_ahead)


def _scheduled_booking_view(booking):
    try:
        players = json.loads(booking.players_json or "[]")
    except json.JSONDecodeError:
        players = []
    return {
        "id": booking.id,
        "type": "scheduled",
        "status": booking.status,
        "course": booking.course,
        "play_date": booking.play_date.isoformat(),
        "play_time": booking.play_time,
        "execute_at": booking.execute_at.strftime("%Y-%m-%d %H:%M"),
        "players": [player.get("player_name") or player.get("member_number") for player in players],
        "can_cancel": booking.status == "scheduled" and server_now() < booking.execute_at - timedelta(minutes=1),
    }


def _recurring_booking_view(booking):
    try:
        players = json.loads(booking.players_json or "[]")
    except json.JSONDecodeError:
        players = []
    return {
        "id": booking.id,
        "type": "recurring",
        "status": booking.status,
        "course": booking.course,
        "play_date": f"Hver {WEEKDAY_NAMES[booking.play_weekday]}",
        "play_time": f"{booking.time_from}-{booking.time_to}",
        "execute_at": booking.next_run_at.strftime("%Y-%m-%d %H:%M"),
        "players": [player.get("player_name") or player.get("member_number") for player in players],
        "can_cancel": booking.status == "active",
    }


def _players_from_prompt(prompt_lower):
    match = re.search(r"(\d+)\s*(person|personer|spiller|spillere)", prompt_lower)
    if match:
        return int(match.group(1))
    return 2


def _date_from_prompt(prompt_lower):
    if "i morgen" in prompt_lower or "imorgen" in prompt_lower:
        return "tomorrow"
    norwegian_match = re.search(r"\b(\d{1,2}\.\d{1,2}\.\d{4})\b", prompt_lower)
    if norwegian_match:
        return norwegian_match.group(1)
    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", prompt_lower)
    if iso_match:
        return iso_match.group(1)
    return "today"


def _execute_at_from_prompt(prompt_lower):
    if not any(word in prompt_lower for word in ("gjennomfør", "gjennomfoer", "utfør", "utfor", "senere", "når bookingen", "nar bookingen")):
        return ""
    schedule_match = re.search(
        r"(?:gjennomfør|gjennomfoer|utfør|utfor|senere|når bookingen|nar bookingen)[^,.;]*?"
        r"(?:(\d{4}-\d{2}-\d{2})|(i morgen|imorgen|i dag|idag))[^,.;]*?"
        r"(?:kl\.?\s*)?(\d{1,2})(?::?(\d{2}))?",
        prompt_lower,
    )
    if not schedule_match:
        return ""
    iso_date, relative_date, hour, minute = schedule_match.groups()
    if iso_date:
        execute_date = iso_date
    else:
        execute_date = _parse_date(relative_date).isoformat()
    return f"{execute_date} {_format_prompt_time(hour, minute)}"


def _time_window_from_prompt(prompt_lower):
    between_match = re.search(
        r"(?:mellom|fra)\s+(?:kl\.?\s*)?(\d{1,2})(?::?(\d{2}))?\s*(?:og|til|-)\s*(?:kl\.?\s*)?(\d{1,2})(?::?(\d{2}))?",
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
        parsed_time = datetime.strptime(_format_prompt_time(hour, minute), "%H:%M").time()
        return parsed_time.strftime("%H:%M"), _time_after(parsed_time, minutes=30)

    return DEFAULT_TIME_FROM, DEFAULT_TIME_TO


def _format_prompt_time(hour, minute=None):
    return f"{int(hour):02d}:{int(minute or 0):02d}"


def _time_after(value, minutes=30):
    dt = datetime.combine(server_now().date(), value) + timedelta(minutes=minutes)
    return dt.time().strftime("%H:%M")


def _courses_from_prompt(prompt):
    prompt_lower = prompt.lower()
    if "oslo-området" in prompt_lower or "osloområdet" in prompt_lower or "baner i oslo" in prompt_lower:
        return list(OSLO_AREA_COURSES)
    known_courses = {
        "ballerud": "Ballerud",
        "oslo": "Oslo",
        "haga": "Haga",
        "bærum": "Bærum",
        "baerum": "Bærum",
        "grini": "Grini",
        "asker": "Asker",
        "oppegård": "Oppegård",
        "oppegard": "Oppegård",
        "drøbak": "Drøbak",
        "drobak": "Drøbak",
    }
    courses = []
    for key, course in known_courses.items():
        if key in prompt_lower and course not in courses:
            courses.append(course)
    if courses:
        return courses
    match = re.search(r"\bp[åa]\s+([A-ZÆØÅa-zæøå][A-ZÆØÅa-zæøå -]+?)(?:\s+for|\s+i dag|\s+mellom|\s+fra|$)", prompt)
    if match:
        return [match.group(1).strip()]
    return [DEFAULT_GOLFBOX_COURSE]
