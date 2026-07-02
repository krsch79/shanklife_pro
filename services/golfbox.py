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
GOLFBOX_FAVORITES_PATH = "/site/playergroups/listGroups.asp?selected={F91B77FE-0055-4656-97C4-61D8923962B6}"
GOLFBOX_MEMBER_LOOKUP_PATH = "/site/my_golfbox/score/whs/_searchMember.asp"
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
    hcp = round(float(user.player.default_hcp), 1) if user and getattr(user, "player", None) else None
    if not user_has_golfbox_credentials(user):
        return {
            "connected": False,
            "player_name": None,
            "club_name": None,
            "member_number": None,
            "hcp": hcp,
            "username": None,
            "memberships": [],
        }
    return {
        "connected": True,
        "player_name": user.golfbox_player_name,
        "club_name": user.golfbox_home_club_name,
        "member_number": user.golfbox_member_number,
        "hcp": hcp,
        "username": user.golfbox_username,
        "memberships": memberships,
    }


def golfbox_favorites_summary(user):
    if not user:
        return []
    from models import GolfBoxFavorite

    return [
        {
            "name": favorite.name,
            "member_number": favorite.member_number,
            "club_name": favorite.club_name,
            "hcp": favorite.hcp,
        }
        for favorite in GolfBoxFavorite.query
        .filter_by(user_id=user.id)
        .order_by(GolfBoxFavorite.name.asc(), GolfBoxFavorite.club_name.asc())
        .all()
    ]


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
        try:
            favorites = _fetch_favorites(client)
        except httpx.HTTPError:
            favorites = []
    identity = _parse_identity(frontpage_html)
    user.golfbox_username = credentials["username"]
    user.golfbox_password_token = _encode_password(credentials["password"])
    user.golfbox_player_name = identity.get("player_name")
    user.golfbox_home_club_name = identity.get("club_name")
    user.golfbox_member_number = identity.get("member_number")
    user.golfbox_memberships_json = json.dumps(memberships, ensure_ascii=False)
    user.golfbox_credentials_updated_at = server_now()
    _apply_golfbox_hcp_to_player(user, identity.get("hcp"))
    _replace_golfbox_favorites(user, favorites)
    return identity


def sync_user_golfbox_handicap(user):
    credentials = _credentials_for_user(user)
    if not credentials:
        return {
            "status": "skipped",
            "message": "GolfBox-innlogging mangler.",
            "hcp": None,
            "updated": False,
        }

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            frontpage_html = _login(client, credentials)
    except httpx.HTTPError as exc:
        raise ValueError(f"Kunne ikke hente handicap fra GolfBox: {exc}") from exc

    identity = _parse_identity(frontpage_html)
    if identity.get("player_name"):
        user.golfbox_player_name = identity.get("player_name")
    if identity.get("club_name"):
        user.golfbox_home_club_name = identity.get("club_name")
    if identity.get("member_number"):
        user.golfbox_member_number = identity.get("member_number")
    user.golfbox_credentials_updated_at = server_now()
    updated = _apply_golfbox_hcp_to_player(user, identity.get("hcp"))
    db.session.commit()
    current_app.logger.info(
        "GolfBox handicap-sync fullført for bruker %s: klubb=%s medlemsnummer=%s hcp=%s oppdatert=%s",
        user.id,
        identity.get("club_name"),
        identity.get("member_number"),
        identity.get("hcp"),
        updated,
    )
    return {
        "status": "ok",
        "message": "",
        "hcp": identity.get("hcp"),
        "updated": updated,
    }


def clear_user_golfbox_credentials(user):
    user.golfbox_username = None
    user.golfbox_password_token = None
    user.golfbox_player_name = None
    user.golfbox_home_club_name = None
    user.golfbox_member_number = None
    user.golfbox_memberships_json = None
    user.golfbox_credentials_updated_at = None
    if getattr(user, "golfbox_favorites", None):
        for favorite in list(user.golfbox_favorites):
            db.session.delete(favorite)


def sync_golfbox_favorites(user):
    credentials = _credentials_for_user(user)
    if not credentials:
        raise ValueError("GolfBox-innlogging mangler.")
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            _login(client, credentials)
            favorites = _fetch_favorites(client)
    except httpx.HTTPError as exc:
        raise ValueError(f"Kunne ikke hente GolfBox-favoritter: {exc}") from exc
    _replace_golfbox_favorites(user, favorites)
    db.session.commit()
    return favorites


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
    text = html.unescape(" ".join(re.sub(r"<[^>]+>", " ", frontpage_html).split()))
    identity_matches = re.findall(
        r"(?P<name>[A-ZÆØÅ][A-Za-zÆØÅæøå.'-]+(?:\s+[A-ZÆØÅ][A-Za-zÆØÅæøå.'-]+){1,4})\s*\|\s*(?P<club>[^|]{2,80}?)\s*\|\s*(?P<member>\d{1,5}-\d{1,8})\s*\|\s*HCP\s*:?\s*(?P<hcp>[+-]?\d{1,3}(?:[,.]\d{1,2})?)?",
        text,
    )
    if not identity_matches:
        return {
            "player_name": None,
            "club_name": None,
            "member_number": None,
            "hcp": None,
        }
    name, club, member_number, hcp_raw = identity_matches[-1]
    hcp = _parse_golfbox_hcp(hcp_raw)
    if hcp is None:
        hcp = _parse_golfbox_hcp_from_text(text, member_number)
    return {
        "player_name": html.unescape(name).strip(),
        "club_name": html.unescape(club).strip(),
        "member_number": member_number.strip(),
        "hcp": hcp,
    }


def _parse_golfbox_hcp(raw_value):
    raw_value = (raw_value or "").strip().replace(",", ".")
    if not raw_value:
        return None
    try:
        value = float(raw_value)
    except ValueError:
        return None
    if value < -20 or value > 60:
        return None
    return round(value, 1)


def _parse_golfbox_hcp_from_text(text, member_number):
    if not text or not member_number:
        return None
    escaped_member = re.escape(member_number)
    match = re.search(
        rf"{escaped_member}\s*\|\s*HCP\s*:?\s*(?P<hcp>[+-]?\d{{1,3}}(?:[,.]\d{{1,2}})?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"\bHCP\s*:?\s*(?P<hcp>[+-]?\d{1,3}(?:[,.]\d{1,2})?)",
            text,
            re.IGNORECASE,
        )
    return _parse_golfbox_hcp(match.group("hcp")) if match else None


def _apply_golfbox_hcp_to_player(user, hcp):
    if hcp is None or not user or not getattr(user, "player", None):
        return False
    if round(float(user.player.default_hcp or 0), 1) == round(float(hcp), 1):
        return False
    user.player.default_hcp = round(float(hcp), 1)
    return True


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
                    "hcp": identity.get("hcp"),
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


def _fetch_favorites(client):
    response = client.get(f"{GOLFBOX_BASE_URL}{GOLFBOX_FAVORITES_PATH}")
    response.raise_for_status()
    return _parse_favorites(response.text)


def _parse_favorites(page_html):
    favorites = []
    for row_match in re.finditer(r"<tr\b[^>]*>(?P<row>.*?)</tr>", page_html or "", re.IGNORECASE | re.DOTALL):
        cells = _plain_cells(row_match.group("row"))
        if len(cells) < 4:
            continue
        name, member_number, hcp, club_name = (cell.strip() for cell in cells[:4])
        if not name or not re.fullmatch(r"\d{1,5}-\d{1,8}", member_number or "") or not club_name:
            continue
        favorites.append(
            {
                "name": name,
                "member_number": member_number,
                "hcp": hcp,
                "club_name": club_name,
            }
        )
    return _dedupe_favorites(favorites)


def _dedupe_favorites(favorites):
    seen = set()
    result = []
    for favorite in favorites:
        key = (favorite.get("member_number"), _normalize_name(favorite.get("club_name")))
        if key in seen:
            continue
        seen.add(key)
        result.append(favorite)
    return result


def _replace_golfbox_favorites(user, favorites):
    from models import GolfBoxFavorite

    GolfBoxFavorite.query.filter_by(user_id=user.id).delete()
    for favorite in favorites:
        db.session.add(
            GolfBoxFavorite(
                user_id=user.id,
                name=favorite["name"],
                member_number=favorite["member_number"],
                club_name=favorite["club_name"],
                hcp=favorite.get("hcp"),
            )
        )


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
    requested_member_numbers = interpretation.get("member_numbers") or []
    member_number_names = interpretation.get("member_number_names") or {}
    include_current_user = interpretation.get("include_current_user")
    memberships = []
    current_membership = _ensure_membership_for_user(user, club_name)
    current_name = (getattr(user, "player", None).name if getattr(user, "player", None) else getattr(user, "username", "")) or ""
    if include_current_user or not requested_names or any(_name_matches(current_name, name) for name in requested_names):
        memberships.append(current_membership or _self_booking_membership(user, club_name))

    for member_number in requested_member_numbers:
        favorite = _favorite_for_member_number(user, member_number, club_name)
        memberships.append({
            "player_name": (
                member_number_names.get(member_number)
                or (favorite.name if favorite else "")
                or f"Medlemsnummer {member_number}"
            ),
            "member_number": member_number,
            "club_name": (favorite.club_name if favorite else "") or club_name or "",
        })

    for requested_name in requested_names:
        if _name_matches(current_name, requested_name):
            continue
        membership = _membership_for_player_name(requested_name, club_name, requester=user)
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


def _resolve_requested_member_memberships(user, interpretation, memberships):
    requested_numbers = [
        str(number).strip()
        for number in (interpretation.get("member_numbers") or [])
        if str(number).strip()
    ]
    if not requested_numbers:
        return memberships, None

    try:
        resolved_members = _lookup_golfbox_members_by_number(user, requested_numbers)
    except (ValueError, httpx.HTTPError):
        return memberships, (
            "GolfBox-medlemsnumrene kunne ikke kontrolleres akkurat nå. "
            "Ingen planlagt booking ble lagret. Prøv igjen senere."
        )

    missing_numbers = [number for number in requested_numbers if number not in resolved_members]
    if missing_numbers:
        return memberships, (
            "Jeg fant ikke medlemsnummer "
            f"{', '.join(missing_numbers)} i GolfBox. Ingen planlagt booking ble lagret."
        )

    for membership in memberships:
        member_number = str(membership.get("member_number") or "").strip()
        resolved = resolved_members.get(member_number)
        if resolved:
            membership.update(resolved)
    return memberships, None


def _lookup_golfbox_members_by_number(user, member_numbers):
    credentials = _credentials_for_user(user)
    if not credentials:
        raise ValueError("GolfBox-innlogging mangler.")

    resolved = {}
    with httpx.Client(
        follow_redirects=True,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        _login(client, credentials)
        for member_number in member_numbers:
            response = client.get(
                f"{GOLFBOX_BASE_URL}{GOLFBOX_MEMBER_LOOKUP_PATH}",
                params={"id": member_number, "country": "NO"},
            )
            response.raise_for_status()
            member = _parse_member_number_lookup(response.text, member_number)
            if member:
                resolved[member_number] = member
    return resolved


def _parse_member_number_lookup(response_text, member_number):
    parts = [html.unescape(part).strip() for part in (response_text or "").split("|")]
    if len(parts) < 3 or not parts[0] or not parts[1] or not parts[2]:
        return None
    return {
        "player_name": parts[1],
        "member_number": str(member_number).strip(),
        "club_name": parts[2],
        "golfbox_player_guid": parts[0],
        "source": "golfbox_member_lookup",
    }


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


def _membership_for_player_name(player_name, club_name=None, requester=None):
    membership = _membership_for_favorite_name(requester, player_name, club_name)
    if membership:
        return membership

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


def _membership_for_favorite_name(user, player_name, club_name=None):
    if not user:
        return None
    from models import GolfBoxFavorite

    favorites = GolfBoxFavorite.query.filter_by(user_id=user.id).all()
    name_matches = [
        favorite
        for favorite in favorites
        if _name_matches(favorite.name, player_name)
    ]
    if not name_matches:
        return None

    requested_club_key = _normalize_name(club_name)
    if requested_club_key:
        club_matches = [
            favorite
            for favorite in name_matches
            if _club_names_match(requested_club_key, favorite.club_name)
        ]
        if club_matches:
            name_matches = club_matches

    favorite = sorted(name_matches, key=lambda item: (item.club_name or "", item.member_number or ""))[0]
    return {
        "player_name": favorite.name,
        "member_number": favorite.member_number,
        "club_name": favorite.club_name,
        "source": "favorite",
    }


def _favorite_for_member_number(user, member_number, club_name=None):
    if not user or not member_number:
        return None
    from models import GolfBoxFavorite

    favorites = (
        GolfBoxFavorite.query
        .filter_by(user_id=user.id, member_number=str(member_number).strip())
        .all()
    )
    if not favorites:
        return None

    requested_club_key = _normalize_name(club_name)
    if requested_club_key:
        club_matches = [
            favorite
            for favorite in favorites
            if _club_names_match(requested_club_key, favorite.club_name)
        ]
        if club_matches:
            favorites = club_matches

    return sorted(favorites, key=lambda item: (item.club_name or "", item.name or ""))[0]


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
        return _attach_interpretation_method(
            confirm_golfbox_booking(pending_booking, user=user),
            source="local_confirmation",
            detail="Brukeren bekreftet en allerede tolket booking.",
        )
    if pending_cancel and _is_confirmation_prompt(prompt_lower):
        return _attach_interpretation_method(
            cancel_golfbox_booking(
                user,
                pending_cancel.get("booking_guid"),
                booking_start=pending_cancel.get("booking_start"),
                resource_guid=pending_cancel.get("resource_guid"),
            ),
            source="local_confirmation",
            detail="Brukeren bekreftet en allerede tolket avbestilling.",
        )
    if not _booking_or_cancel_prompt(prompt_lower):
        profile_result = _profile_info_result(prompt_lower, user)
        if profile_result:
            profile_result["prompt"] = cleaned_prompt
            return _attach_interpretation_method(
                profile_result,
                source="local_rules",
                detail="Dette ble besvart med en lokal profilsjekk uten OpenAI.",
            )

    interpretation = _interpret_prompt_with_openai(cleaned_prompt, user)
    intent = interpretation["intent"]
    if intent == "cancel_booking":
        return _attach_interpretation_method(
            _cancel_booking_result(interpretation, cleaned_prompt, user),
            interpretation=interpretation,
        )

    players = interpretation["players"]
    play_date = interpretation["date"]
    time_from = interpretation["time_from"]
    time_to = interpretation["time_to"]
    courses = interpretation["courses"]
    if intent == "create_booking" and interpretation.get("watch"):
        return _attach_interpretation_method(
            _watch_booking_result(interpretation, cleaned_prompt, user),
            interpretation=interpretation,
        )
    if intent == "create_booking" and interpretation.get("execute_at"):
        return _attach_interpretation_method(
            _scheduled_booking_result(interpretation, cleaned_prompt, user),
            interpretation=interpretation,
        )

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
    return _attach_interpretation_method(result, interpretation=interpretation)


def _attach_interpretation_method(result, interpretation=None, source=None, detail=None):
    if not isinstance(result, dict):
        return result
    source = source or (interpretation or {}).get("_interpretation_source") or "local_rules"
    if source == "openai":
        label = "OpenAI + lokale regler"
        detail = detail or "OpenAI tolket meldingen, og Shanklife validerte dato, spillere og medlemsnummer med lokale regler."
    elif source == "local_confirmation":
        label = "Lokal bekreftelse"
        detail = detail or "Dette var en bekreftelse av en handling som allerede var tolket."
    else:
        label = "Lokale regler"
        detail = detail or (interpretation or {}).get("_interpretation_detail") or "Meldingen ble tolket med lokale regler uten OpenAI."
    result["interpretation_method"] = {
        "source": source,
        "label": label,
        "detail": detail,
    }
    return result


def _interpret_prompt_with_openai(prompt, user):
    if not os.environ.get("OPENAI_API_KEY"):
        _load_env_file()
    if not os.environ.get("OPENAI_API_KEY"):
        return _fallback_prompt_interpretation(prompt, user=user, detail="OpenAI-nøkkel mangler på serveren.")

    today = server_now().date().isoformat()
    user_context = _prompt_user_context(user)
    prompt_text = (
        f"I dag er {today}. Innlogget bruker og lagrede GolfBox-medlemskap: {user_context}. "
        "Tolk golfmelding til JSON: "
        '{"intent":"find_availability|create_booking|cancel_booking|unknown",'
        '"courses":[],"area":"","players":1,"include_current_user":false,'
        '"player_names":[],"member_numbers":[],"member_number_names":{},"watch":false,'
        '"date":"YYYY-MM-DD","time_from":"HH:MM","time_to":"HH:MM",'
        '"execute_at":"","recurrence":{"frequency":"","weekday":"","execute_time":"","play_weekday":"","play_weeks_ahead":0}}. '
        "Regler: book/bestill/reserver=create_booking, ledig=find_availability, "
        "avbestill/kanseller=cancel_booking. Oslo-området: area=oslo og courses=[]. "
        "Flere baner listes i courses. Kjente korte banenavn: Ballerud, Oslo, Haga, "
        "Bærum, Grini, Asker, Oppegård, Drøbak. Mangler dato: i dag. "
        "Mangler tidsrom: 06:00-22:00. Enkelt klokkeslett: time_from=klokkeslett "
        "og time_to=30 minutter senere. Mangler spillere ved ledighetssøk: 1. "
        "Mangler spillere ved booking uten medspillere: innlogget bruker. "
        "Hvis brukeren skriver jeg/meg/Kristian om seg selv, sett include_current_user=true, "
        "men ikke legg innlogget bruker i member_numbers. "
        "Medlemsnummer som 65-2560 legges i member_numbers og tilhører medspilleren, ikke innlogget bruker. "
        "Hvis medlemsnummer har navn i parentes, for eksempel 65-2560 (Øyvind), sett member_number_names={\"65-2560\":\"Øyvind\"}. "
        "Hvis teksten sier meg og medlemsnummer 65-2560, er det to spillere: innlogget bruker + spilleren med medlemsnummeret. "
        "Hvis brukeren ber deg sjekke jevnlig, følge med, prøve igjen eller booke hvis noe blir ledig, sett watch=true. "
        "Hvis brukeren ber om fast/repeterende booking, sett recurrence.frequency=weekly, "
        "recurrence.weekday til engelsk ukedag og recurrence.execute_time til klokkeslettet jobben skal kjøre. "
        "Sett recurrence.play_weekday til ukedagen starttiden skal spilles dersom den nevnes. "
        "Hvis brukeren sier neste/påfølgende mandag om spilletid når jobben også kjører mandag, sett play_weeks_ahead=1. "
        "Hvis brukeren ber om at bookingen skal gjennomføres senere, sett execute_at "
        "til lokal ISO-dato og tid for selve gjennomføringen, ikke spilletiden. Bare JSON. "
        f"Melding: {prompt}"
    )
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.responses.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-5.2"),
        input=[{
            "role": "user",
            "content": [{"type": "input_text", "text": prompt_text}],
        }],
    )
    try:
        data = _extract_json(response.output_text)
    except (ValueError, json.JSONDecodeError):
        return _fallback_prompt_interpretation(prompt, user=user, detail="OpenAI svarte ikke med gyldig JSON, så lokale regler tok over.")
    try:
        return _normalize_interpretation(data, prompt, user)
    except ValueError:
        return _fallback_prompt_interpretation(prompt, user=user, detail="OpenAI-tolkingen ga ugyldige datoer eller tider, så lokale regler tok over.")


def _extract_json(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Fant ikke JSON i AI-respons.")
    return json.loads(text[start:end + 1])


def _normalize_interpretation(data, prompt, user=None):
    fallback = _fallback_prompt_interpretation(prompt, user=user)
    prompt_lower = prompt.lower()
    prompt_member_numbers = _member_numbers_from_prompt(prompt_lower)
    prompt_member_number_names = _member_number_names_from_prompt(prompt)
    prompt_include_current_user = _prompt_references_current_user(prompt_lower)
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
    player_names = _merge_unique(player_names, _favorite_names_from_prompt(user, prompt))
    member_numbers = data.get("member_numbers")
    if not isinstance(member_numbers, list):
        member_numbers = []
    member_numbers = _merge_unique(_clean_member_numbers(member_numbers), prompt_member_numbers, fallback.get("member_numbers", []))
    member_number_names = data.get("member_number_names")
    if not isinstance(member_number_names, dict):
        member_number_names = {}
    member_number_names = {
        number: str(name).strip()
        for number, name in member_number_names.items()
        if number in member_numbers and str(name).strip()
    }
    member_number_names.update(prompt_member_number_names)

    include_current_user = bool(data.get("include_current_user") or fallback.get("include_current_user") or prompt_include_current_user)

    try:
        players = int(data.get("players") or fallback["players"])
    except (TypeError, ValueError):
        players = fallback["players"]
    players = max(1, min(4, players))
    min_players_from_text = len(player_names) + len(member_numbers) + (1 if include_current_user else 0)
    if (
        intent == "find_availability"
        and not _prompt_has_explicit_player_count(prompt_lower)
        and not min_players_from_text
    ):
        players = 1
    if _prompt_has_explicit_player_count(prompt_lower):
        players = max(players, fallback["players"])
    if _solo_booking_prompt(prompt_lower) and min_players_from_text <= 1:
        players = 1
        player_names = []
    elif include_current_user and not _prompt_has_explicit_player_count(prompt_lower):
        players = min(4, max(1, len(player_names) + len(member_numbers) + 1))
    if min_players_from_text:
        players = min(4, max(players, min_players_from_text))

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
        "member_numbers": member_numbers,
        "member_number_names": member_number_names,
        "include_current_user": include_current_user,
        "date": play_date,
        "time_from": time_from,
        "time_to": time_to,
        "execute_at": execute_at,
        "recurrence": recurrence,
        "watch": bool(data.get("watch") or fallback.get("watch") or _watch_prompt(prompt_lower)),
        "_interpretation_source": "openai",
    }


def _fallback_prompt_interpretation(prompt, user=None, detail=None):
    prompt_lower = prompt.lower()
    if any(word in prompt_lower for word in ("avbestill", "avbook", "kanseller")):
        intent = "cancel_booking"
    elif any(word in prompt_lower for word in ("bestill", "book", "reserver")):
        intent = "create_booking"
    else:
        intent = "find_availability"
    courses = _courses_from_prompt(prompt)
    time_from, time_to = _time_window_from_prompt(prompt_lower)
    players = _players_from_prompt(prompt_lower, default=1 if intent == "find_availability" else 2)
    if _prompt_references_current_user(prompt_lower) and not _prompt_has_explicit_player_count(prompt_lower):
        players = 1 + len(_member_numbers_from_prompt(prompt_lower))
    return {
        "intent": intent,
        "courses": courses,
        "area": "oslo" if "oslo-området" in prompt_lower or "osloområdet" in prompt_lower else "",
        "players": players,
        "player_names": _favorite_names_from_prompt(user, prompt),
        "member_numbers": _member_numbers_from_prompt(prompt_lower),
        "member_number_names": _member_number_names_from_prompt(prompt),
        "include_current_user": _prompt_references_current_user(prompt_lower),
        "date": _date_from_prompt(prompt_lower),
        "time_from": time_from,
        "time_to": time_to,
        "execute_at": _execute_at_from_prompt(prompt_lower),
        "recurrence": _recurrence_from_prompt(prompt_lower),
        "watch": _watch_prompt(prompt_lower),
        "_interpretation_source": "local_rules",
        "_interpretation_detail": detail or "OpenAI ble ikke brukt for denne tolkingen.",
    }


def _favorite_names_from_prompt(user, prompt):
    if not user:
        return []
    favorites = golfbox_favorites_summary(user)
    prompt_key = _normalize_name(prompt)
    if not prompt_key:
        return []

    names_by_key = {}
    first_names = {}
    for favorite in favorites:
        name = favorite.get("name") or ""
        name_key = _normalize_name(name)
        if not name_key:
            continue
        names_by_key[name_key] = name
        first_name = name_key.split()[0]
        first_names.setdefault(first_name, set()).add(name)

    found = []
    for name_key, name in names_by_key.items():
        if re.search(rf"\b{re.escape(name_key)}\b", prompt_key):
            found.append(name)

    for first_name, names in first_names.items():
        if len(names) != 1:
            continue
        if re.search(rf"\b{re.escape(first_name)}\b", prompt_key):
            found.extend(names)

    return _merge_unique(found)


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
    play_weekday_value = str(value.get("play_weekday") or "").strip().lower()
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
    play_weekday = _weekday_number(play_weekday_value)
    if play_weekday is None:
        play_weekday = fallback.get("play_weekday", execute_weekday)
    play_weeks_ahead = _normalize_play_weeks_ahead(value.get("play_weeks_ahead"), prompt_lower, execute_weekday, play_weekday)
    return {
        "frequency": "weekly",
        "execute_weekday": execute_weekday,
        "execute_time": parsed_time.strftime("%H:%M"),
        "play_weekday": play_weekday,
        "play_weeks_ahead": play_weeks_ahead,
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
    execute_weekday = _weekday_number(weekday_text)
    play_weekday = _play_weekday_from_prompt(prompt_lower, execute_weekday)
    return {
        "frequency": "weekly",
        "execute_weekday": execute_weekday,
        "execute_time": _format_prompt_time(hour, minute),
        "play_weekday": play_weekday,
        "play_weeks_ahead": _play_weeks_ahead_from_prompt(prompt_lower, execute_weekday, play_weekday),
    }


def _play_weekday_from_prompt(prompt_lower, execute_weekday):
    weekday_pattern = "|".join(WEEKDAY_NAMES)
    explicit_match = re.search(
        rf"(?:neste|påfølgende)\s+({weekday_pattern})",
        prompt_lower,
    )
    if explicit_match:
        return _weekday_number(explicit_match.group(1))
    booking_match = re.search(
        rf"(?:book|bestill|reserver)[^,.;]*?\b({weekday_pattern})\b",
        prompt_lower,
    )
    if booking_match:
        return _weekday_number(booking_match.group(1))
    return execute_weekday


def _play_weeks_ahead_from_prompt(prompt_lower, execute_weekday, play_weekday):
    if execute_weekday == play_weekday and re.search(rf"\b(?:neste|påfølgende)\s+{WEEKDAY_NAMES[play_weekday]}\b", prompt_lower):
        return 1
    return 0


def _normalize_play_weeks_ahead(raw_value, prompt_lower, execute_weekday, play_weekday):
    try:
        value = int(raw_value or 0)
    except (TypeError, ValueError):
        value = 0
    value = max(0, min(4, value))
    fallback_value = _play_weeks_ahead_from_prompt(prompt_lower, execute_weekday, play_weekday)
    return max(value, fallback_value)


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


def _prompt_user_context(user):
    if not user:
        return "Ingen innlogget bruker."
    names = [getattr(user, "username", "")]
    if getattr(user, "player", None):
        names.append(user.player.name)
    if user.golfbox_player_name:
        names.append(user.golfbox_player_name)
    memberships = _user_memberships(user)
    if memberships:
        membership_text = ", ".join(
            f"{item.get('club_name')}: {item.get('member_number')}"
            for item in memberships
            if item.get("club_name") and item.get("member_number")
        )
    elif user.golfbox_member_number:
        membership_text = f"{user.golfbox_home_club_name}: {user.golfbox_member_number}"
    else:
        membership_text = "ingen lagrede medlemskap"
    favorites = golfbox_favorites_summary(user)
    if favorites:
        favorite_groups = {}
        for favorite in favorites[:40]:
            favorite_groups.setdefault(favorite["name"], []).append(
                f"{favorite['club_name']}: {favorite['member_number']}"
            )
        favorite_text = "; ".join(
            f"{name} ({', '.join(memberships)})"
            for name, memberships in favorite_groups.items()
        )
    else:
        favorite_text = "ingen lagrede favoritter"
    return (
        f"Navn: {', '.join(name for name in names if name)}. "
        f"Medlemskap: {membership_text}. "
        f"GolfBox-favoritter: {favorite_text}"
    )


def _merge_unique(*groups):
    merged = []
    for group in groups:
        for value in group or []:
            value = str(value).strip()
            if value and value not in merged:
                merged.append(value)
    return merged


def _clean_member_numbers(member_numbers):
    cleaned = []
    for value in member_numbers:
        match = re.search(r"\b(\d{1,5}-\d{1,8})\b", str(value))
        if match and match.group(1) not in cleaned:
            cleaned.append(match.group(1))
    return cleaned


def _member_numbers_from_prompt(prompt_lower):
    return _clean_member_numbers(re.findall(r"\b\d{1,5}-\d{1,8}\b", prompt_lower))


def _member_number_names_from_prompt(prompt):
    names = {}
    for match in re.finditer(
        r"\b(?P<number>\d{1,5}-\d{1,8})\s*\((?P<name>[^)]+)\)",
        prompt or "",
        re.IGNORECASE,
    ):
        name = match.group("name").strip()
        if name and _normalize_name(name) not in {"jeg", "meg", "kristian"}:
            names[match.group("number")] = name
    return names


def _watch_prompt(prompt_lower):
    watch_phrases = (
        "sjekk jevnlig",
        "jevne mellomrom",
        "følg med",
        "folg med",
        "prøv igjen",
        "prov igjen",
        "hvis det ikke er noe ledig",
        "hvis det ikke er ledig",
        "hvis du finner ledig",
        "blir noe ledig",
        "blir ledig",
    )
    return any(phrase in prompt_lower for phrase in watch_phrases)


def _booking_or_cancel_prompt(prompt_lower):
    booking_words = (
        "book",
        "booke",
        "booker",
        "booking",
        "bestill",
        "reserver",
        "avbestill",
        "avbook",
        "kanseller",
        "sjekk med jevne",
        "følg med",
        "folg med",
    )
    return any(word in prompt_lower for word in booking_words)


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
    expected_players = max(int(availability_result["players"]), len(player_memberships))
    if len(player_memberships) < expected_players:
        availability_result["status"] = "needs_player_details"
        if expected_players == 1:
            availability_result["message"] = (
                f"Jeg fant ikke GolfBox-medlemskapet ditt for {selected_slot['course']}. "
                "Åpne Min side og lagre GolfBox-innloggingen på nytt, så henter jeg klubbmedlemskapene dine på nytt."
            )
        else:
            availability_result["message"] = (
                f"Jeg fant {len(player_memberships)} av {expected_players} spillere. "
                "Skriv navn på medspillere som har lagret GolfBox-medlemskap, eller oppgi medlemsnummer. "
                f"Skriv for eksempel: Book {selected_slot['course']} for Kristian og Erik i morgen mellom 15 og 17."
            )
        return availability_result
    pending = {
        "course": selected_slot["course"],
        "date": selected_slot["date"],
        "time": selected_slot["time"],
        "players": expected_players,
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


def start_golfbox_slot_booking(slot_payload, user=None):
    slot = _slot_from_payload(slot_payload)
    interpretation = slot_payload.get("interpretation") if isinstance(slot_payload, dict) else {}
    if not isinstance(interpretation, dict):
        interpretation = {}
    if _interpretation_has_player_details(interpretation):
        return _booking_confirmation_for_slot(slot, interpretation, user)
    return _slot_booking_player_question(slot, interpretation)


def continue_golfbox_slot_booking(slot_payload, player_prompt, user=None):
    slot = _slot_from_payload(slot_payload)
    prompt = " ".join((player_prompt or "").strip().split())
    if not prompt:
        return _slot_booking_player_question(slot, slot_payload.get("interpretation") if isinstance(slot_payload, dict) else {})

    interpretation_prompt = f"Book {slot['course']} {slot['date']} kl {slot['time']} for {prompt}"
    interpretation = _interpret_prompt_with_openai(interpretation_prompt, user)
    interpretation["intent"] = "create_booking"
    interpretation["courses"] = [slot["course"]]
    interpretation["date"] = slot["date"]
    interpretation["time_from"] = slot["time"]
    interpretation["time_to"] = _time_after(_parse_time(slot["time"], "booking_time"), minutes=30)
    if _solo_booking_prompt(prompt.lower()) and not interpretation.get("member_numbers") and not interpretation.get("player_names"):
        interpretation["include_current_user"] = True
        interpretation["players"] = 1
    return _booking_confirmation_for_slot(slot, interpretation, user)


def _slot_from_payload(slot_payload):
    if not isinstance(slot_payload, dict):
        raise ValueError("Fant ikke valgt GolfBox-tid.")
    slot = {
        "course": str(slot_payload.get("course") or "").strip(),
        "date": str(slot_payload.get("date") or "").strip(),
        "time": str(slot_payload.get("time") or "").strip(),
        "available_spots": int(slot_payload.get("available_spots") or 0),
        "club_guid": str(slot_payload.get("club_guid") or "").strip(),
        "resource_guid": str(slot_payload.get("resource_guid") or "").strip(),
    }
    if not slot["course"] or not slot["date"] or not slot["time"] or not slot["club_guid"] or not slot["resource_guid"]:
        raise ValueError("Den valgte GolfBox-tiden mangler nødvendig informasjon.")
    _parse_date(slot["date"])
    _parse_time(slot["time"], "booking_time")
    return slot


def _interpretation_has_player_details(interpretation):
    return bool(
        interpretation.get("include_current_user")
        or interpretation.get("player_names")
        or interpretation.get("member_numbers")
    )


def _slot_booking_player_question(slot, interpretation=None):
    result = {
        "intent": "create_booking",
        "status": "slot_booking_players_required",
        "message": (
            f"Hvem skal bookes inn på {slot['course']} {slot['date']} kl. {slot['time']}? "
            "Skriv «bare meg», eller skriv navn/medlemsnummer på de som skal med, for eksempel "
            "«meg og 65-2560»."
        ),
        "slot": slot,
        "pending_slot_booking": {
            **slot,
            "interpretation": interpretation or {},
        },
        "available_slots": [],
    }
    return _attach_interpretation_method(
        result,
        source="local_rules",
        detail="Brukeren valgte en konkret ledig GolfBox-tid, og må velge spillere før booking kan bekreftes.",
    )


def _booking_confirmation_for_slot(slot, interpretation, user):
    players = max(1, min(4, int(interpretation.get("players") or 1)))
    result = {
        "intent": "create_booking",
        "status": "ok",
        "course": slot["course"],
        "date": slot["date"],
        "time_from": slot["time"],
        "time_to": _time_after(_parse_time(slot["time"], "booking_time"), minutes=30),
        "players": players,
        "booking_enabled": True,
        "available_slots": [slot],
        "interpretation": interpretation,
    }
    return _attach_interpretation_method(
        _booking_confirmation_result(result, interpretation, user),
        interpretation=interpretation,
    )


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
    player_memberships, member_lookup_error = _resolve_requested_member_memberships(
        user,
        interpretation,
        player_memberships,
    )
    if member_lookup_error:
        return {
            "intent": "create_booking",
            "status": "needs_player_details",
            "message": member_lookup_error,
            "available_slots": [],
        }
    expected_players = max(int(interpretation["players"]), len(player_memberships))
    if len(player_memberships) < expected_players:
        if expected_players == 1:
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
                f"Jeg fant {len(player_memberships)} av {expected_players} spillere. "
                "Skriv navn på medspillere som har lagret GolfBox-medlemskap, eller oppgi medlemsnummer "
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


def _watch_booking_result(interpretation, prompt, user):
    if not _credentials_for_user(user):
        return {
            "intent": "create_booking",
            "status": "configuration_required",
            "message": "Legg GolfBox-innlogging inn på Min side før jeg kan følge med etter ledig tid.",
            "available_slots": [],
        }
    courses = interpretation.get("courses") or [DEFAULT_GOLFBOX_COURSE]
    if len(courses) != 1:
        return {
            "intent": "create_booking",
            "status": "booking_unsupported_course",
            "message": "Automatisk ledighetssjekk må peke på én konkret bane.",
            "available_slots": [],
        }
    course_name = courses[0]
    player_memberships = _booking_player_memberships(user, interpretation, course_name)
    player_memberships, member_lookup_error = _resolve_requested_member_memberships(
        user,
        interpretation,
        player_memberships,
    )
    if member_lookup_error:
        return {
            "intent": "create_booking",
            "status": "needs_player_details",
            "message": member_lookup_error,
            "available_slots": [],
        }
    expected_players = max(int(interpretation["players"]), len(player_memberships))
    if len(player_memberships) < expected_players:
        return {
            "intent": "create_booking",
            "status": "needs_player_details",
            "message": (
                f"Jeg fant {len(player_memberships)} av {expected_players} spillere. "
                "Skriv navn på medspillere som har lagret GolfBox-medlemskap, eller oppgi medlemsnummer."
            ),
            "available_slots": [],
        }

    availability = find_golfbox_availability(
        course=course_name,
        players=expected_players,
        play_date=interpretation["date"],
        time_from=interpretation["time_from"],
        time_to=interpretation["time_to"],
        user=user,
    )
    availability["intent"] = "create_booking"
    availability["prompt"] = prompt
    availability["interpretation"] = interpretation
    if availability.get("status") != "ok":
        return availability
    if availability.get("available_slots"):
        return _booking_confirmation_result(availability, interpretation, user)

    from models import GolfBoxWatchBooking

    play_date = _parse_date(interpretation["date"])
    start_time = _parse_time(interpretation["time_from"], "time_from")
    end_time = _parse_time(interpretation["time_to"], "time_to")
    expires_at = datetime.combine(play_date, end_time)
    if expires_at <= server_now():
        return {
            "intent": "create_booking",
            "status": "booking_failed",
            "message": "Tidsrommet er allerede passert, så jeg kan ikke følge med på denne bookingen.",
            "available_slots": [],
        }

    watch = GolfBoxWatchBooking(
        created_by_user_id=user.id,
        status="active",
        course=course_name,
        play_date=play_date,
        time_from=start_time.strftime("%H:%M"),
        time_to=end_time.strftime("%H:%M"),
        interval_minutes=5,
        next_run_at=server_now() + timedelta(minutes=5),
        expires_at=expires_at,
        players_json=json.dumps(player_memberships, ensure_ascii=False),
        requested_prompt=prompt,
    )
    db.session.add(watch)
    db.session.commit()
    player_text = ", ".join(player["player_name"] for player in player_memberships)
    return {
        "intent": "create_booking",
        "status": "watch_booking_created",
        "watch_booking_id": watch.id,
        "course": watch.course,
        "date": watch.play_date.isoformat(),
        "time_from": watch.time_from,
        "time_to": watch.time_to,
        "execute_at": watch.next_run_at.strftime("%Y-%m-%d %H:%M"),
        "players": len(player_memberships),
        "player_names": [player["player_name"] for player in player_memberships],
        "message": (
            f"Jeg fant ingen ledig tid nå, så jeg følger med på {watch.course} "
            f"{watch.play_date.isoformat()} mellom {watch.time_from} og {watch.time_to} "
            f"for {player_text}. Jeg sjekker hvert {watch.interval_minutes}. minutt og booker automatisk hvis jeg finner plass."
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
    play_weekday = int(recurrence.get("play_weekday", execute_weekday))
    play_weeks_ahead = int(recurrence.get("play_weeks_ahead", 0) or 0)
    next_run_at = _next_weekday_run(execute_weekday, execute_time)
    recurring = GolfBoxRecurringBooking(
        created_by_user_id=user.id,
        status="active",
        course=course_name,
        play_weekday=play_weekday,
        time_from=interpretation["time_from"],
        time_to=interpretation["time_to"],
        execute_weekday=execute_weekday,
        execute_time=execute_time,
        play_weeks_ahead=play_weeks_ahead,
        next_run_at=next_run_at,
        players_json=json.dumps(player_memberships, ensure_ascii=False),
        requested_prompt=prompt,
    )
    db.session.add(recurring)
    db.session.commit()
    player_text = ", ".join(player["player_name"] for player in player_memberships)
    first_play_date = _next_play_date_for_recurring(recurring)
    return {
        "intent": "create_booking",
        "status": "recurring_booking_created",
        "recurring_booking_id": recurring.id,
        "course": recurring.course,
        "play_date": first_play_date.isoformat(),
        "time_from": recurring.time_from,
        "time_to": recurring.time_to,
        "execute_at": recurring.next_run_at.strftime("%Y-%m-%d %H:%M"),
        "players": len(player_memberships),
        "player_names": [player["player_name"] for player in player_memberships],
        "message": (
            f"Jeg har lagt inn fast ukentlig booking: {recurring.course} hver "
            f"{WEEKDAY_NAMES[play_weekday]} mellom {recurring.time_from} og {recurring.time_to} "
            f"for {player_text}. Første forsøk kjøres {recurring.next_run_at:%Y-%m-%d %H:%M} "
            f"og gjelder {first_play_date.isoformat()}."
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
    from models import GolfBoxRecurringBooking, GolfBoxScheduledBooking, GolfBoxWatchBooking

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
    watch_bookings = (
        GolfBoxWatchBooking.query
        .filter_by(created_by_user_id=user.id)
        .filter(GolfBoxWatchBooking.status == "active")
        .order_by(GolfBoxWatchBooking.play_date.asc(), GolfBoxWatchBooking.time_from.asc())
        .all()
    )
    return (
        [_scheduled_booking_view(booking) for booking in bookings]
        + [_recurring_booking_view(booking) for booking in recurring_bookings]
        + [_watch_booking_view(booking) for booking in watch_bookings]
    )


def golfbox_booking_history(user, limit=50):
    from models import GolfBoxBookingRun, GolfBoxRecurringBooking, GolfBoxScheduledBooking, GolfBoxWatchBooking

    runs = (
        GolfBoxBookingRun.query
        .filter_by(created_by_user_id=user.id)
        .order_by(GolfBoxBookingRun.finished_at.desc(), GolfBoxBookingRun.id.desc())
        .limit(limit)
        .all()
    )
    rows = [_booking_run_history_view(run, user) for run in runs]
    logged_sources = {(run.booking_type, run.source_booking_id) for run in runs}

    scheduled = (
        GolfBoxScheduledBooking.query
        .filter_by(created_by_user_id=user.id)
        .filter(GolfBoxScheduledBooking.status.notin_(("scheduled", "running")))
        .all()
    )
    rows.extend(
        _legacy_scheduled_history_view(booking, user)
        for booking in scheduled
        if ("scheduled", booking.id) not in logged_sources
    )

    recurring = GolfBoxRecurringBooking.query.filter_by(created_by_user_id=user.id).all()
    rows.extend(
        _legacy_recurring_history_view(booking, user)
        for booking in recurring
        if booking.last_run_at and ("recurring", booking.id) not in logged_sources
    )

    watches = GolfBoxWatchBooking.query.filter_by(created_by_user_id=user.id).all()
    rows.extend(
        _legacy_watch_history_view(booking, user)
        for booking in watches
        if booking.status != "active" and ("watch", booking.id) not in logged_sources
    )
    rows.sort(key=lambda row: row["sort_at"], reverse=True)
    return rows[:limit]


def golfbox_booking_history_detail(user, record_type, record_id):
    from models import GolfBoxBookingRun, GolfBoxRecurringBooking, GolfBoxScheduledBooking, GolfBoxWatchBooking

    if record_type == "run":
        record = GolfBoxBookingRun.query.filter_by(id=record_id, created_by_user_id=user.id).first()
        return _booking_run_history_view(record, user, include_detail=True) if record else None
    if record_type == "scheduled":
        record = GolfBoxScheduledBooking.query.filter_by(id=record_id, created_by_user_id=user.id).first()
        return _legacy_scheduled_history_view(record, user, include_detail=True) if record else None
    if record_type == "recurring":
        record = GolfBoxRecurringBooking.query.filter_by(id=record_id, created_by_user_id=user.id).first()
        return _legacy_recurring_history_view(record, user, include_detail=True) if record else None
    if record_type == "watch":
        record = GolfBoxWatchBooking.query.filter_by(id=record_id, created_by_user_id=user.id).first()
        return _legacy_watch_history_view(record, user, include_detail=True) if record else None
    return None


def cancel_golfbox_scheduled_booking(booking_id, user, booking_type="scheduled"):
    from models import GolfBoxRecurringBooking, GolfBoxScheduledBooking, GolfBoxWatchBooking

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

    if booking_type == "watch":
        watch = GolfBoxWatchBooking.query.filter_by(id=booking_id, created_by_user_id=user.id).first()
        if not watch:
            raise ValueError("Fant ikke ledighetssøket.")
        if watch.status != "active":
            raise ValueError("Dette ledighetssøket kan ikke kanselleres lenger.")
        watch.status = "cancelled"
        watch.cancelled_at = server_now()
        db.session.commit()
        return watch

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
    from models import GolfBoxRecurringBooking, GolfBoxScheduledBooking, GolfBoxWatchBooking

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
        player_memberships = []
        started_at = server_now()
        booking.status = "running"
        booking.updated_at = server_now()
        db.session.commit()
        try:
            player_memberships = json.loads(booking.players_json or "[]")
            pending_booking = _scheduled_pending_booking(booking, player_memberships)
            result = confirm_golfbox_booking(
                pending_booking,
                user=booking.created_by_user,
                notification_event="scheduled_executed",
            )
            booking.executed_at = server_now()
            booking.result_message = result.get("message")
            booking.error_message = None if result.get("status") == "booking_created" else result.get("message")
            booking.status = "completed" if result.get("status") == "booking_created" else "failed"
            _record_golfbox_booking_run(
                booking,
                "scheduled",
                result.get("status") or booking.status,
                booking.play_date,
                booking.play_time,
                booking.play_time,
                player_memberships,
                result.get("message"),
                booking.error_message,
                started_at,
            )
            results.append({"id": booking.id, "status": booking.status, "message": result.get("message")})
            if booking.status == "failed":
                _send_booking_outcome_email(
                    booking.created_by_user,
                    "scheduled_failed",
                    booking.course,
                    booking.play_date.isoformat(),
                    booking.play_time,
                    player_memberships,
                    result.get("message"),
                )
        except Exception as exc:
            booking.executed_at = server_now()
            booking.status = "failed"
            booking.error_message = str(exc)
            _record_golfbox_booking_run(
                booking,
                "scheduled",
                "failed",
                booking.play_date,
                booking.play_time,
                booking.play_time,
                player_memberships,
                str(exc),
                str(exc),
                started_at,
            )
            results.append({"id": booking.id, "status": "failed", "message": str(exc)})
            _send_booking_outcome_email(
                booking.created_by_user,
                "scheduled_failed",
                booking.course,
                booking.play_date.isoformat(),
                booking.play_time,
                player_memberships,
                str(exc),
            )
        db.session.commit()
    remaining = max(0, limit - len(results))
    if remaining:
        watch_bookings = (
            GolfBoxWatchBooking.query
            .filter(GolfBoxWatchBooking.status == "active")
            .filter(GolfBoxWatchBooking.next_run_at <= server_now())
            .order_by(GolfBoxWatchBooking.next_run_at.asc())
            .limit(remaining)
            .all()
        )
        for booking in watch_bookings:
            results.append(_run_watch_golfbox_booking(booking))
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


def _scheduled_pending_booking(booking, player_memberships):
    return {
        "course": booking.course,
        "date": booking.play_date.isoformat(),
        "time": booking.play_time,
        "players": len(player_memberships),
        "player_memberships": player_memberships,
    }


def _run_watch_golfbox_booking(booking):
    now = server_now()
    if now >= booking.expires_at:
        player_memberships = json.loads(booking.players_json or "[]")
        booking.status = "expired"
        booking.last_run_at = now
        booking.last_result_message = "Ledighetssøket utløp uten booking."
        booking.updated_at = now
        _record_golfbox_booking_run(
            booking,
            "watch",
            "expired",
            booking.play_date,
            booking.time_from,
            booking.time_to,
            player_memberships,
            booking.last_result_message,
            None,
            now,
        )
        db.session.commit()
        _send_booking_outcome_email(
            booking.created_by_user,
            "watch_expired",
            booking.course,
            booking.play_date.isoformat(),
            booking.time_from,
            player_memberships,
            booking.last_result_message,
            time_to=booking.time_to,
        )
        return {"id": booking.id, "type": "watch", "status": "expired", "message": booking.last_result_message}
    try:
        player_memberships = json.loads(booking.players_json or "[]")
        availability = find_golfbox_availability(
            course=booking.course,
            players=len(player_memberships) or 1,
            play_date=booking.play_date.isoformat(),
            time_from=booking.time_from,
            time_to=booking.time_to,
            user=booking.created_by_user,
        )
        if availability.get("status") == "ok" and availability.get("available_slots"):
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
            booking.booked_time = selected_slot["time"] if status == "booking_created" else None
            booking.booked_at = now if status == "booking_created" else None
            booking.status = "completed" if status == "booking_created" else "failed"
            booking.last_error_message = None if status == "booking_created" else message
            _record_golfbox_booking_run(
                booking,
                "watch",
                status,
                booking.play_date,
                selected_slot["time"],
                selected_slot["time"],
                player_memberships,
                message,
                booking.last_error_message,
                now,
            )
        else:
            message = availability.get("message") or "Ingen ledig tid funnet ennå."
            status = "no_slot"
            booking.next_run_at = now + timedelta(minutes=max(1, booking.interval_minutes or 5))
            if booking.next_run_at > booking.expires_at:
                booking.next_run_at = booking.expires_at
            booking.last_error_message = None
        booking.last_run_at = now
        booking.last_result_message = message
        booking.updated_at = now
        db.session.commit()
        if booking.status == "failed":
            _send_booking_outcome_email(
                booking.created_by_user,
                "scheduled_failed",
                booking.course,
                booking.play_date.isoformat(),
                booking.time_from,
                player_memberships,
                message,
                time_to=booking.time_to,
            )
        return {"id": booking.id, "type": "watch", "status": status, "message": message}
    except Exception as exc:
        booking.last_run_at = now
        booking.last_error_message = str(exc)
        booking.next_run_at = now + timedelta(minutes=max(1, booking.interval_minutes or 5))
        if booking.next_run_at > booking.expires_at:
            booking.next_run_at = booking.expires_at
        booking.updated_at = now
        db.session.commit()
        return {"id": booking.id, "type": "watch", "status": "failed", "message": str(exc)}


def _run_recurring_golfbox_booking(booking):
    player_memberships = []
    play_date = _next_play_date_for_recurring(booking)
    started_at = server_now()
    try:
        player_memberships = json.loads(booking.players_json or "[]")
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
        _record_golfbox_booking_run(
            booking,
            "recurring",
            status,
            play_date,
            selected_slot["time"] if status == "booking_created" else booking.time_from,
            selected_slot["time"] if status == "booking_created" else booking.time_to,
            player_memberships,
            message,
            booking.last_error_message,
            started_at,
        )
        db.session.commit()
        if status != "booking_created":
            _send_booking_outcome_email(
                booking.created_by_user,
                "no_availability" if status == "no_slot" else "scheduled_failed",
                booking.course,
                play_date.isoformat(),
                booking.time_from,
                player_memberships,
                message,
                time_to=booking.time_to,
            )
        return {"id": booking.id, "type": "recurring", "status": status, "message": message}
    except Exception as exc:
        booking.last_run_at = server_now()
        booking.last_error_message = str(exc)
        booking.next_run_at = _next_weekday_run(booking.execute_weekday, booking.execute_time, from_dt=server_now() + timedelta(minutes=1))
        booking.updated_at = server_now()
        _record_golfbox_booking_run(
            booking,
            "recurring",
            "failed",
            play_date,
            booking.time_from,
            booking.time_to,
            player_memberships,
            str(exc),
            str(exc),
            started_at,
        )
        db.session.commit()
        _send_booking_outcome_email(
            booking.created_by_user,
            "scheduled_failed",
            booking.course,
            play_date.isoformat(),
            booking.time_from,
            player_memberships,
            str(exc),
            time_to=booking.time_to,
        )
        return {"id": booking.id, "type": "recurring", "status": "failed", "message": str(exc)}


def _record_golfbox_booking_run(
    booking,
    booking_type,
    status,
    play_date,
    time_from,
    time_to,
    players,
    message,
    error_message,
    started_at,
):
    from models import GolfBoxBookingRun

    db.session.add(GolfBoxBookingRun(
        created_by_user_id=booking.created_by_user_id,
        booking_type=booking_type,
        source_booking_id=booking.id,
        status=status,
        course=booking.course,
        play_date=play_date,
        time_from=time_from,
        time_to=time_to,
        players_json=json.dumps(players or [], ensure_ascii=False),
        requested_prompt=booking.requested_prompt,
        message=message,
        error_message=error_message,
        started_at=started_at,
        finished_at=server_now(),
    ))


def _send_booking_outcome_email(user, event, course, play_date, time_from, players, message, time_to=None):
    send_golfbox_booking_email(user, event, {
        "course": course,
        "date": play_date,
        "time": time_from,
        "time_to": time_to,
        "player_memberships": players,
        "message": message,
    })


def _next_play_date_for_recurring(booking):
    base = booking.next_run_at.date()
    days_ahead = (booking.play_weekday - base.weekday()) % 7
    play_weeks_ahead = max(0, int(getattr(booking, "play_weeks_ahead", 0) or 0))
    if days_ahead == 0 and play_weeks_ahead:
        days_ahead = 7 * play_weeks_ahead
    elif play_weeks_ahead > 1:
        days_ahead += 7 * (play_weeks_ahead - 1)
    return base + timedelta(days=days_ahead)


BOOKING_TYPE_LABELS = {
    "scheduled": "Planlagt enkeltbooking",
    "recurring": "Fast booking",
    "watch": "Ledighetssøk",
}

BOOKING_STATUS_LABELS = {
    "booking_created": "Gjennomført",
    "completed": "Gjennomført",
    "failed": "Feilet",
    "payment_required": "Stoppet ved betaling",
    "wrong_club": "Stoppet ved feil klubb",
    "wrong_membership": "Stoppet ved medlemskontroll",
    "no_slot": "Ingen ledig tid",
    "expired": "Utløpt uten booking",
    "cancelled": "Kansellert",
}


def _history_status_class(status):
    if status in {"booking_created", "completed"}:
        return "success"
    if status in {"failed", "payment_required", "wrong_club", "wrong_membership"}:
        return "error"
    return "neutral"


def _history_datetime(value):
    return value.strftime("%Y-%m-%d %H:%M") if value else None


def _history_players(record, user):
    try:
        players = json.loads(record.players_json or "[]")
    except json.JSONDecodeError:
        players = []
    return _booking_player_labels(players, user, record.course)


def _history_base(record_type, record_id, booking_type, status, course, play_date, time_from, time_to, players, history_at):
    return {
        "record_type": record_type,
        "id": record_id,
        "booking_type": booking_type,
        "type_label": BOOKING_TYPE_LABELS.get(booking_type, "GolfBox-booking"),
        "status": status,
        "status_label": BOOKING_STATUS_LABELS.get(status, status.replace("_", " ").capitalize()),
        "status_class": _history_status_class(status),
        "course": course,
        "play_date": play_date.isoformat() if play_date else "-",
        "play_time": time_from if not time_to or time_to == time_from else f"{time_from}-{time_to}",
        "players": players,
        "history_at": _history_datetime(history_at),
        "sort_at": history_at or datetime.min,
    }


def _booking_run_history_view(run, user, include_detail=False):
    if not run:
        return None
    row = _history_base(
        "run",
        run.id,
        run.booking_type,
        run.status,
        run.course,
        run.play_date,
        run.time_from,
        run.time_to,
        _history_players(run, user),
        run.finished_at,
    )
    if include_detail:
        row.update({
            "requested_prompt": run.requested_prompt,
            "message": run.message,
            "error_message": run.error_message,
            "events": [
                {"label": "Kjøring startet", "time": _history_datetime(run.started_at), "text": "Den automatiske GolfBox-kjøringen startet."},
                {"label": "Kjøring avsluttet", "time": _history_datetime(run.finished_at), "text": run.message or run.error_message or "Kjøringen ble avsluttet."},
            ],
        })
    return row


def _legacy_scheduled_history_view(booking, user, include_detail=False):
    if not booking:
        return None
    history_at = booking.executed_at or booking.cancelled_at or booking.updated_at or booking.created_at
    row = _history_base(
        "scheduled",
        booking.id,
        "scheduled",
        booking.status,
        booking.course,
        booking.play_date,
        booking.play_time,
        booking.play_time,
        _history_players(booking, user),
        history_at,
    )
    if include_detail:
        events = [
            {"label": "Bestilling opprettet", "time": _history_datetime(booking.created_at), "text": "Bookingen ble lagt i kø."},
            {"label": "Planlagt kjøring", "time": _history_datetime(booking.execute_at), "text": "Tidspunktet bookingen skulle gjennomføres."},
        ]
        if history_at:
            events.append({
                "label": "Resultat",
                "time": _history_datetime(history_at),
                "text": booking.result_message or booking.error_message or BOOKING_STATUS_LABELS.get(booking.status, booking.status),
            })
        row.update({
            "requested_prompt": booking.requested_prompt,
            "message": booking.result_message,
            "error_message": booking.error_message,
            "events": events,
        })
    return row


def _legacy_recurring_history_view(booking, user, include_detail=False):
    if not booking:
        return None
    status = "failed" if booking.last_error_message else (
        "booking_created" if "sendt til GolfBox" in (booking.last_result_message or "") else "no_slot"
    )
    date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", booking.last_result_message or "")
    play_date = date.fromisoformat(date_match.group(1)) if date_match else _play_date_for_recurring_run(
        booking,
        booking.last_run_at or booking.created_at,
    )
    row = _history_base(
        "recurring",
        booking.id,
        "recurring",
        status,
        booking.course,
        play_date,
        booking.time_from,
        booking.time_to,
        _history_players(booking, user),
        booking.last_run_at,
    )
    if include_detail:
        row.update({
            "requested_prompt": booking.requested_prompt,
            "message": booking.last_result_message,
            "error_message": booking.last_error_message,
            "events": [{
                "label": "Siste registrerte kjøring",
                "time": _history_datetime(booking.last_run_at),
                "text": booking.last_result_message or booking.last_error_message or "Ingen resultatmelding lagret.",
            }],
        })
    return row


def _play_date_for_recurring_run(booking, run_at):
    base = run_at.date()
    days_ahead = (booking.play_weekday - base.weekday()) % 7
    play_weeks_ahead = max(0, int(getattr(booking, "play_weeks_ahead", 0) or 0))
    if days_ahead == 0 and play_weeks_ahead:
        days_ahead = 7 * play_weeks_ahead
    elif play_weeks_ahead > 1:
        days_ahead += 7 * (play_weeks_ahead - 1)
    return base + timedelta(days=days_ahead)


def _legacy_watch_history_view(booking, user, include_detail=False):
    if not booking:
        return None
    history_at = booking.booked_at or booking.last_run_at or booking.cancelled_at or booking.updated_at
    status = "booking_created" if booking.status == "completed" else booking.status
    row = _history_base(
        "watch",
        booking.id,
        "watch",
        status,
        booking.course,
        booking.play_date,
        booking.booked_time or booking.time_from,
        booking.booked_time or booking.time_to,
        _history_players(booking, user),
        history_at,
    )
    if include_detail:
        row.update({
            "requested_prompt": booking.requested_prompt,
            "message": booking.last_result_message,
            "error_message": booking.last_error_message,
            "events": [{
                "label": "Siste registrerte hendelse",
                "time": _history_datetime(history_at),
                "text": booking.last_result_message or booking.last_error_message or BOOKING_STATUS_LABELS.get(status, status),
            }],
        })
    return row


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
        "players": _booking_player_labels(players, booking.created_by_user, booking.course),
        "can_cancel": booking.status == "scheduled" and server_now() < booking.execute_at - timedelta(minutes=1),
    }


def _recurring_booking_view(booking):
    try:
        players = json.loads(booking.players_json or "[]")
    except json.JSONDecodeError:
        players = []
    play_date = _next_play_date_for_recurring(booking)
    return {
        "id": booking.id,
        "type": "recurring",
        "status": booking.status,
        "course": booking.course,
        "play_date": play_date.isoformat(),
        "schedule_label": f"Hver {WEEKDAY_NAMES[booking.play_weekday]}",
        "play_time": f"{booking.time_from}-{booking.time_to}",
        "execute_at": booking.next_run_at.strftime("%Y-%m-%d %H:%M"),
        "players": _booking_player_labels(players, booking.created_by_user, booking.course),
        "can_cancel": booking.status == "active",
    }


def _watch_booking_view(booking):
    try:
        players = json.loads(booking.players_json or "[]")
    except json.JSONDecodeError:
        players = []
    return {
        "id": booking.id,
        "type": "watch",
        "status": booking.status,
        "course": booking.course,
        "play_date": booking.play_date.isoformat(),
        "play_time": f"{booking.time_from}-{booking.time_to}",
        "execute_at": booking.next_run_at.strftime("%Y-%m-%d %H:%M"),
        "players": _booking_player_labels(players, booking.created_by_user, booking.course),
        "can_cancel": booking.status == "active",
    }


def _booking_player_labels(players, user=None, club_name=None):
    labels = []
    for player in players:
        name = (player.get("player_name") or "").strip()
        member_number = (player.get("member_number") or "").strip()
        if member_number and (not name or _normalize_name(name) == _normalize_name(f"Medlemsnummer {member_number}")):
            favorite = _favorite_for_member_number(user, member_number, club_name)
            if favorite:
                name = favorite.name
        if name and member_number:
            labels.append(f"{name} ({member_number})")
        elif name:
            labels.append(name)
        elif member_number:
            labels.append(member_number)
    return labels


def _players_from_prompt(prompt_lower, default=2):
    match = re.search(r"(\d+)\s*(person|personer|spiller|spillere)", prompt_lower)
    if match:
        return int(match.group(1))
    return default


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
