"""Owner-scoped Starttider drafts and reviewed operations using existing GolfBox services.

Commit the small workspace/action claim before upstream I/O. Never replay an uncertain
external action. Credentials remain in the existing encrypted account fields.
"""
import json
import re
import secrets
from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
from openai import OpenAI
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import GolfBoxAction, GolfBoxFavorite, GolfBoxWorkspace
from services import golfbox as gb
from services.time import server_now


class StaleDraft(ValueError):
    pass


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


def default_draft():
    return {"courses": ["Ballerud"], "date": server_now().date().isoformat(),
            "time_from": "06:00", "time_to": "22:00", "players": 1,
            "player_refs": ["self"], "unresolved_names": []}


def workspace(user):
    row = db.session.get(GolfBoxWorkspace, user.id)
    if row is None:
        row = GolfBoxWorkspace(user_id=user.id, state_json=dumps({"draft": default_draft()}))
        db.session.add(row)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            row = db.session.get(GolfBoxWorkspace, user.id)
    if row.busy and row.updated_at < server_now() - timedelta(minutes=5):
        row.busy = False  # Actions remain claimed/unknown and are never replayed.
        db.session.commit()
    return row


def public_state(row):
    state = json.loads(row.state_json)
    if row.updated_at < server_now() - timedelta(hours=24) and not row.busy:
        state = {"draft": default_draft(), "message": "Det gamle søket er utløpt. Start et nytt søk."}
    return {**state, "revision": row.revision, "busy": row.busy}


def claim(row, revision):
    result = db.session.execute(update(GolfBoxWorkspace).where(
        GolfBoxWorkspace.user_id == row.user_id, GolfBoxWorkspace.revision == revision,
        GolfBoxWorkspace.busy.is_(False),
    ).values(busy=True, revision=GolfBoxWorkspace.revision + 1, updated_at=server_now()))
    db.session.commit()
    if result.rowcount != 1:
        raise StaleDraft("Søket er endret i en annen fane, eller en forespørsel kjører. Hent gjeldende søk.")
    db.session.refresh(row)


def save(row, state):
    row.state_json = dumps(state)
    row.updated_at = server_now()
    row.busy = False
    db.session.commit()
    return public_state(row)


def validate_draft(raw, user):
    if not isinstance(raw, dict):
        raise ValueError("Ugyldig søk.")
    courses = raw.get("courses") or []
    if isinstance(courses, str):
        courses = [s.strip() for s in courses.split(",") if s.strip()]
    if not isinstance(courses, list) or not 1 <= len(courses) <= 8:
        raise ValueError("Velg én til åtte baner.")
    courses = list(dict.fromkeys(str(c).strip() for c in courses))
    if any(not c or len(c) > 120 for c in courses):
        raise ValueError("Skriv gyldige banenavn.")
    play_date = gb._parse_date(str(raw.get("date", "")))
    if play_date < server_now().date():
        raise ValueError("Spilledato må være i dag eller senere.")
    start = gb._parse_time(str(raw.get("time_from", "")), "time_from")
    end = gb._parse_time(str(raw.get("time_to", "")), "time_to")
    if end <= start:
        raise ValueError("Sluttid må være etter starttid.")
    try:
        count = int(raw.get("players", 1))
    except (TypeError, ValueError):
        raise ValueError("Velg antall plasser fra én til fire.")
    if not 1 <= count <= 4:
        raise ValueError("Velg antall plasser fra én til fire.")
    refs = raw.get("player_refs", [])
    if not isinstance(refs, list) or len(refs) > 4:
        raise ValueError("Velg maksimalt fire spillere.")
    refs = ["self"] + list(dict.fromkeys(str(r) for r in refs if r != "self"))
    for ref in refs:
        if ref == "self":
            continue
        if re.fullmatch(r"m:\d{1,5}-\d{1,8}", ref):
            continue
        if not re.fullmatch(r"f:\d{1,5}-\d{1,8}", ref) or not GolfBoxFavorite.query.filter_by(member_number=ref[2:], user_id=user.id).first():
            raise ValueError("En valgt favoritt finnes ikke i din GolfBox-liste. Velg spilleren på nytt.")
    if len(refs) > count:
        raise ValueError("Antall plasser kan ikke være lavere enn antall valgte spillere.")
    return {"courses": courses, "date": play_date.isoformat(), "time_from": start.strftime("%H:%M"),
            "time_to": end.strftime("%H:%M"), "players": count, "player_refs": refs,
            "unresolved_names": [str(n)[:80] for n in raw.get("unresolved_names", [])][:4]}


def favorites(user):
    rows = GolfBoxFavorite.query.filter_by(user_id=user.id).order_by(GolfBoxFavorite.name).all()
    return [{"ref": "f:" + r.member_number, "name": r.name, "club": r.club_name,
             "member_number": r.member_number} for r in rows]


def search_players(user, query):
    """Read the existing GolfBox directory, without changing favorites or booking."""
    from services.golfbox_scores import search_marker
    query = " ".join(str(query or "").split())
    if not 2 <= len(query) <= 100:
        raise ValueError("Skriv minst to tegn i navnet eller et medlemsnummer som 65-1234.")
    if not gb.user_has_golfbox_credentials(user):
        raise ValueError("Koble til din GolfBox-konto i Profil før du søker etter spillere.")
    db.session.commit()  # No SQLite transaction across an upstream read.
    if re.fullmatch(r"\d{1,5}-\d{1,8}", query):
        members = list(gb._lookup_golfbox_members_by_number(user, [query]).values())
    else:
        members = []
        for row in search_marker(user, query)[:30]:
            # GolfBox name-search labels start with the national membership ID.
            # Names and GUIDs alone are insufficient for its booking form.
            match = re.match(r"\s*(\d{1,5}-\d{1,8})\s*,", row.get("label", ""))
            if match:
                members.append({"member_number": match[1], "player_name": row["name"],
                                "club_name": row["club"], "golfbox_player_guid": row["guid"]})
    own_favorites = {p["member_number"]: p for p in favorites(user)}
    seen, results = set(), []
    for member in members:
        number = member["member_number"]
        if number in seen or gb._membership_represents_user(user, member):
            continue
        seen.add(number)
        results.append(own_favorites.get(number) or {"ref": "m:" + number,
            "name": member["player_name"], "club": member["club_name"], "member_number": number})
    return results


def player_labels(draft, user):
    options = {p["ref"]: p["name"] for p in favorites(user)}
    return ["Meg" if r == "self" else options.get(r, r.removeprefix("m:")) for r in draft["player_refs"]]


def selected_members(draft, user, course):
    if draft.get("unresolved_names"):
        raise ValueError("Velg de riktige spillerne i spillervelgeren: " + ", ".join(draft["unresolved_names"]))
    if not draft["player_refs"] or draft["player_refs"][0] != "self":
        raise ValueError("Du skal alltid være spiller 1. Velg spillerne på nytt.")
    if len(draft["player_refs"]) != draft["players"]:
        raise ValueError("Velg navn eller medlemsnummer for alle spillerne før du bekrefter.")
    members = []
    # Keep the account identity first, matching the existing GolfBox booking window.
    refs = sorted(draft["player_refs"], key=lambda r: r != "self")
    for ref in refs:
        if ref == "self":
            membership = gb._ensure_membership_for_user(user, course) or gb._self_booking_membership(user, course)
        elif ref.startswith("f:"):
            f = GolfBoxFavorite.query.filter_by(member_number=ref[2:], user_id=user.id).first()
            if f is None:
                raise ValueError("En favoritt er fjernet. Velg spilleren på nytt.")
            membership = {"player_name": f.name, "member_number": f.member_number, "club_name": f.club_name}
        else:
            found = gb._lookup_golfbox_members_by_number(user, [ref[2:]])
            membership = found.get(ref[2:])
        if not membership or not membership.get("member_number"):
            raise ValueError("GolfBox-medlemskap mangler. Kontroller tilkoblingen eller velg riktig medlemskap.")
        if ref != "self" and gb._membership_represents_user(user, membership):
            raise ValueError("Du er allerede spiller 1. Velg en annen medspiller.")
        members.append(membership)
    if len({m["member_number"] for m in members}) != len(members):
        raise ValueError("Samme medlemskap er valgt flere ganger. Velg ulike spillere.")
    return members


def new_review(user, kind, payload, summary):
    action = GolfBoxAction(id=secrets.token_urlsafe(24), user_id=user.id, kind=kind,
                          payload_json=dumps(payload), expires_at=server_now() + timedelta(minutes=10))
    db.session.add(action)
    db.session.commit()
    return {"id": action.id, "kind": kind, "expires_at": action.expires_at.isoformat(), **summary}


def search(draft, user):
    if not gb.user_has_golfbox_credentials(user):
        return {"status": "configuration_required", "message": "Koble til din GolfBox-konto i Profil før du søker.", "available_slots": []}
    result = gb.find_golfbox_availability_for_courses(courses=draft["courses"], players=draft["players"],
        play_date=draft["date"], time_from=draft["time_from"], time_to=draft["time_to"], user=user)
    # The browser receives a view; selection later uses this server-held list.
    result["available_slots"] = result.get("available_slots", [])[:200]
    # Every returned slot came from a successful, resolved course read. The old
    # aggregate flag only allowed booking when exactly one course was searched.
    result["booking_enabled"] = any(s.get("club_guid") and s.get("resource_guid") for s in result["available_slots"])
    result["fetched_at"] = server_now().isoformat()
    return result


def review_slot(index, state, user):
    result = state.get("result") or {}
    if result.get("status") != "ok" or not result.get("booking_enabled"):
        raise ValueError("Booking er ikke tilgjengelig for dette søkeresultatet.")
    fetched = datetime.fromisoformat(result["fetched_at"])
    if fetched < server_now() - timedelta(minutes=10):
        raise ValueError("Tidene er blitt gamle. Søk på nytt før du velger en tid.")
    slots = result.get("available_slots") or []
    if not isinstance(index, int) or not 0 <= index < len(slots):
        raise ValueError("Velg en tid fra ditt siste søkeresultat.")
    slot = slots[index]
    draft = validate_draft(state["draft"], user)
    if int(slot.get("available_spots") or 0) < draft["players"]:
        raise ValueError("Denne tiden har ikke plass til alle spillerne.")
    members = selected_members(draft, user, slot["course"])
    payload = {key: slot[key] for key in ("course", "date", "time", "club_guid", "resource_guid")}
    payload.update(players=len(members), player_memberships=members)
    return new_review(user, "booking", payload, {"course": slot["course"], "date": slot["date"],
        "time": slot["time"], "players": [m["player_name"] for m in members],
        "message": "Ledighet og medlemskap kontrolleres på nytt før reservasjonen bekreftes."})


def review_job(raw, draft, user):
    if len(draft["courses"]) != 1:
        raise ValueError("Et automatisk oppdrag må gjelde én konkret bane.")
    kind = raw.get("kind")
    if kind not in {"watch", "scheduled", "recurring"}:
        raise ValueError("Velg oppdragstype.")
    members = selected_members(draft, user, draft["courses"][0])
    interpretation = {**draft, "intent": "create_booking", "include_current_user": "self" in draft["player_refs"],
        "player_names": [m["player_name"] for m in members],
        "member_numbers": [m["member_number"] for m in members if not gb._membership_represents_user(user, m)],
        "member_number_names": {m["member_number"]: m["player_name"] for m in members}, "recurrence": {}}
    summary = {"course": draft["courses"][0], "date": draft["date"],
        "time": draft["time_from"] + "–" + draft["time_to"], "players": [m["player_name"] for m in members]}
    if kind == "scheduled":
        execute = gb._parse_execute_at(str(raw.get("execute_at") or ""))
        if not execute or execute <= server_now():
            raise ValueError("Velg en kjøring frem i tid.")
        if execute >= datetime.combine(datetime.fromisoformat(draft["date"]).date(), gb._parse_time(draft["time_from"], "time")):
            raise ValueError("Forsøket må kjøres før spilletiden.")
        interpretation["execute_at"] = execute.isoformat()
        summary["time"] = draft["time_from"]
        summary["message"] = f"Ett forsøk {execute:%d.%m.%Y %H:%M} (Europe/Oslo). Booker på valgt starttid uten ny bekreftelse."
    elif kind == "recurring":
        try:
            weekday = int(raw.get("weekday", 0)); weeks = int(raw.get("weeks_ahead", 0))
        except (TypeError, ValueError):
            raise ValueError("Velg ukedag og antall uker.")
        if weekday not in range(7) or weeks not in range(5):
            raise ValueError("Ugyldig ukentlig oppdrag.")
        execute_time = gb._parse_time(str(raw.get("execute_time", "")), "execute_time").strftime("%H:%M")
        play_weekday = datetime.fromisoformat(draft["date"]).weekday()
        interpretation["recurrence"] = {"frequency": "weekly", "execute_weekday": weekday,
            "execute_time": execute_time, "play_weekday": play_weekday, "play_weeks_ahead": weeks}
        interpretation["execute_at"] = gb._next_weekday_run(weekday, execute_time).isoformat()
        first_run = datetime.fromisoformat(interpretation["execute_at"])
        first_play = gb._next_play_date_for_recurring(SimpleNamespace(next_run_at=first_run, play_weekday=play_weekday, play_weeks_ahead=weeks))
        summary["date"] = first_play.isoformat()
        summary["message"] = (f"Første forsøk {first_run:%d.%m.%Y %H:%M}, første spilledag {first_play:%d.%m.%Y}. Forsøk hver {gb.WEEKDAY_NAMES[weekday]} kl. {execute_time} (Europe/Oslo), "
            f"for {gb.WEEKDAY_NAMES[play_weekday]}. Booker innenfor valgt tidsrom uten ny bekreftelse. Gjelder til du stopper oppdraget.")
    else:
        interpretation["watch"] = True
        summary["message"] = "Sjekker hvert 5. minutt frem til slutten av valgt tidsrom. Kan booke automatisk for de valgte spillerne."
    return new_review(user, kind, {"interpretation": interpretation, "members": members}, summary)


def confirm(action_id, user):
    action = GolfBoxAction.query.filter_by(id=action_id, user_id=user.id).first()
    if not action:
        raise ValueError("Fant ikke denne handlingen i din konto.")
    if action.status != "ready":
        return json.loads(action.result_json) if action.result_json else {
            "status": "booking_unverified", "message": "Handlingen er allerede sendt. Kontroller Mine tider og hendelsesloggen før du prøver igjen."}
    if action.expires_at < server_now():
        raise ValueError("Oppsummeringen er utløpt. Velg tiden eller oppdraget på nytt.")
    payload, kind = json.loads(action.payload_json), action.kind
    if kind in {"booking", "watch", "scheduled", "recurring"}:
        members = payload.get("player_memberships", []) if kind == "booking" else payload.get("members", [])
        if not members or not gb._membership_represents_user(user, members[0]):
            raise ValueError("Du skal alltid være spiller 1. Velg tiden og spillerne på nytt.")
    changed = db.session.execute(update(GolfBoxAction).where(
        GolfBoxAction.id == action.id, GolfBoxAction.status == "ready"
    ).values(status="processing"))
    db.session.commit()
    if changed.rowcount != 1:
        raise StaleDraft("Denne handlingen er allerede sendt. Kontroller status før et nytt forsøk.")
    try:
        if kind == "booking":
            # Refresh exact capacity before entering the existing verified booking flow.
            available = gb.find_golfbox_availability_for_courses(courses=[payload["course"]], players=payload["players"],
                play_date=payload["date"], time_from=payload["time"],
                time_to=gb._time_after(gb._parse_time(payload["time"], "time"), minutes=1), user=user)
            if available.get("status") != "ok":
                result = {"status": "booking_failed", "message": available.get("message") or "Kunne ikke kontrollere ledigheten. Velg tiden på nytt."}
            elif not any(s["time"] == payload["time"] and s.get("resource_guid") == payload["resource_guid"]
                         and int(s.get("available_spots") or 0) >= payload["players"] for s in available.get("available_slots", [])):
                result = {"status": "booking_failed", "message": "Tiden er ikke lenger ledig for alle. Søk etter en annen tid."}
            else:
                result = gb.confirm_golfbox_booking(payload, user=user)
        elif kind in {"watch", "scheduled", "recurring"}:
            i = payload["interpretation"]
            if kind == "watch":
                result = gb._watch_booking_result(i, "Opprettet i Starttider etter bekreftelse", user)
            elif kind == "scheduled":
                result = gb._scheduled_booking_result(i, "Opprettet i Starttider etter bekreftelse", user)
            else:
                if datetime.fromisoformat(i["execute_at"]) <= server_now():
                    raise ValueError("Tidspunktet er passert. Opprett en ny oppsummering.")
                result = gb._recurring_booking_result(i, "Opprettet i Starttider etter bekreftelse", user, i["courses"][0], payload["members"])
        elif kind == "cancel":
            result = gb.cancel_golfbox_booking(user, **payload)
            if result.get("status") == "booking_cancelled":
                current = gb.upcoming_golfbox_bookings(user)
                if current.get("status") != "ok" or any(b.get("booking_guid") == payload["booking_guid"] for b in current.get("bookings", [])):
                    result = {"status": "booking_unverified", "message": "Avbestillingen er sendt, men resultatet kunne ikke verifiseres. Oppdater Mine tider før du prøver igjen."}
        elif kind == "stop":
            gb.cancel_golfbox_scheduled_booking(payload["id"], user, booking_type=payload["type"])
            result = {"status": "scheduled_booking_cancelled", "message": "Oppdraget er stoppet. Eventuelle reservasjoner håndteres i Mine tider."}
        else:
            raise ValueError("Ukjent handling.")
    except Exception:
        # A timeout can follow a completed submit; never offer blind replay.
        db.session.rollback()
        result = {"status": "booking_unverified", "message": "Resultatet kunne ikke avklares. Kontroller Mine tider eller oppdragsloggen før et nytt forsøk."}
    action = db.session.get(GolfBoxAction, action_id)
    action.status = "unknown" if result.get("status") == "booking_unverified" else "done"
    action.result_json = dumps(result)
    db.session.commit()
    return result


def interpret(prompt, draft, user):
    """Return a validated partial patch. Interpretation can never execute a booking."""
    prompt = str(prompt).strip()
    if not prompt or len(prompt) > 1000:
        raise ValueError("Skriv en kort beskrivelse på maksimalt 1000 tegn.")
    lower = prompt.lower()
    if any(w in lower for w in ("avbestill", "kanseller", "avbook")):
        raise ValueError("Åpne Mine tider for å velge og bekrefte riktig avbestilling.")
    patch, method = {}, "Lokale regler"
    if gb.os.environ.get("OPENAI_API_KEY"):
        try:
            response = OpenAI(api_key=gb.os.environ["OPENAI_API_KEY"], timeout=18, max_retries=0).responses.create(
                model=gb.os.environ.get("OPENAI_MODEL", "gpt-5.2"),
                input=[{"role": "system", "content": "Tolk endringer i et golfsøk som JSON. Returner KUN eksplisitte endringer, ingen standardverdier. "
                    "Tillatte felt: courses (liste banenavn), date (YYYY-MM-DD), time_from, time_to (HH:MM), players (1-4), player_names (liste), include_current_user (bool). "
                    "Ved 'etter 17' endres bare time_from. Behold andre felt. Ingen bookinger eller oppdrag kan utføres. "
                    + "I dag: " + server_now().date().isoformat() + ". Gjeldende søk: " + dumps(draft)},
                    {"role": "user", "content": prompt}])
            candidate = gb._extract_json(response.output_text)
            if isinstance(candidate, dict):
                patch = {k: v for k, v in candidate.items() if k in {"courses", "date", "time_from", "time_to", "players", "player_names", "include_current_user"}}
                method = "AI + validering"
        except Exception:
            pass  # Manual search and the bounded local parser remain available.
    fallback = gb._fallback_prompt_interpretation(prompt, user=user)
    # Explicit local cues also make common follow-ups reliable without AI.
    if re.search(r"\b(i dag|i morgen|imorgen|\d{4}-\d{2}-\d{2})\b", lower):
        patch.setdefault("date", fallback["date"])
    mentioned_courses = [c for c in gb.OSLO_AREA_COURSES if c.lower() in lower]
    if mentioned_courses:
        patch.setdefault("courses", mentioned_courses)
    if "oslo-området" in lower:
        patch["courses"] = gb.OSLO_AREA_COURSES
    if re.search(r"\b(etter|fra|mellom|kl\.?|før)\s*\d", lower):
        patch.setdefault("time_from", fallback["time_from"])
        if re.search(r"mellom|\bfør\b|\btil\s*\d|\d\s*[-–]\s*\d", lower):
            patch.setdefault("time_to", fallback["time_to"])
    if gb._prompt_has_explicit_player_count(lower):
        patch.setdefault("players", fallback["players"])
    options = favorites(user)
    names = patch.pop("player_names", None)
    explicit_self = patch.pop("include_current_user", None)
    manual_numbers = gb._member_numbers_from_prompt(lower)
    found_names = list(dict.fromkeys(o["name"] for o in options if re.search(r"(?<!\w)" + re.escape(o["name"].lower()) + r"(?!\w)", lower)))
    if names is not None or found_names or manual_numbers or re.search(r"\b(meg|jeg|bare meg)\b", lower):
        names = names if isinstance(names, list) else found_names
        additive = bool(re.search(r"legg til|også|ta med|pluss", lower))
        subtractive = bool(re.search(r"\b(uten|fjern)\b", lower))
        refs = list(draft["player_refs"]) if additive or subtractive else []
        unresolved = list(draft.get("unresolved_names", [])) if additive or subtractive else []
        if explicit_self or re.search(r"\b(meg|jeg)\b", lower):
            refs.append("self")
        for name in names:
            matches = [o for o in options if gb._name_matches(o["name"], str(name))]
            if len(matches) == 1:
                if subtractive:
                    refs = [r for r in refs if r != matches[0]["ref"]]
                else:
                    refs.append(matches[0]["ref"])
            else:
                unresolved.append(str(name))
        refs.extend("m:" + n for n in manual_numbers if not subtractive)
        patch["player_refs"] = list(dict.fromkeys(refs))
        patch["unresolved_names"] = unresolved
        if "players" not in patch:
            patch["players"] = max(1, len(refs) + len(unresolved))
    if not patch:
        raise ValueError("Jeg fikk ikke avklart endringen. Bruk feltene, eller skriv for eksempel «heller etter 17». Ingen booking er sendt.")
    # AI can infer the number of places, but identities are chosen after a time.
    patch["player_refs"] = ["self"]
    patch["unresolved_names"] = []
    return validate_draft({**draft, **patch}, user), method
