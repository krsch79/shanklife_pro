import html
import json
import re
from datetime import datetime
from urllib.parse import urljoin

import httpx

from models import CourseHole, CourseTeeLength, ScoreEntry
from services.golfbox import GOLFBOX_BASE_URL, _credentials_for_user, _form_inputs, _login, user_has_golfbox_credentials
from services.handicap import round_half_up
from services.round_length import round_handicap_stroke_index, round_hole_count, round_holes
from services.time import format_server_datetime, server_now


SCORE_FORM_PATH = "/site/my_golfbox/score/whs/newWHSScore.asp?selected={238637A4-005F-4F66-B31A-C2747726FC0B}"


def round_player_score_payload(round_player):
    round_obj = round_player.round
    holes = round_holes(round_obj)
    entries = {
        entry.hole_number: entry
        for entry in ScoreEntry.query.filter_by(round_player_id=round_player.id).all()
    }
    rows = []
    for hole in holes:
        entry = entries.get(hole.hole_number)
        rows.append(
            {
                "hole_number": hole.hole_number,
                "par": hole.par,
                "stroke_index": round_handicap_stroke_index(round_obj, hole),
                "strokes": entry.strokes if entry else None,
                "length": _tee_length(round_player, hole),
            }
        )
    return {
        "round_id": round_obj.id,
        "round_player_id": round_player.id,
        "course_name": round_obj.course.name,
        "tee_name": round_player.selected_tee.name if round_player.selected_tee else "",
        "hole_count": round_hole_count(round_obj),
        "played_at": round_obj.finished_at or round_obj.started_at,
        "hcp": round_player.hcp_for_round,
        "rows": rows,
        "total": sum(row["strokes"] for row in rows if row["strokes"] is not None),
        "complete": all(row["strokes"] is not None for row in rows),
    }


def search_marker(user, query):
    query = " ".join((query or "").split())
    if not query:
        raise ValueError("Skriv inn markørnavn.")
    credentials = _credentials_or_error(user)
    with _golfbox_client() as client:
        _login(client, credentials)
        response = client.post(
            f"{GOLFBOX_BASE_URL}/site/my_golfbox/score/whs/_searchMember.asp",
            data={"name": query, "country": "NO"},
        )
        response.raise_for_status()
    return _parse_marker_search_results(response.text)


def submit_score(round_player, user, marker_guid, marker_name, marker_club, course_selection=None):
    payload = round_player_score_payload(round_player)
    if not payload["complete"]:
        raise ValueError("Alle hullscorer må være fylt ut før runden kan sendes til GolfBox.")
    if payload["hole_count"] not in (9, 18):
        raise ValueError("GolfBox-innsending støtter bare 9 eller 18 hull.")
    if not marker_guid:
        raise ValueError("Velg markør før innsending.")

    credentials = _credentials_or_error(user)
    with _golfbox_client() as client:
        form_page = _load_score_form(client, credentials)
        form_data = _build_score_form_data(client, form_page, round_player, payload, marker_guid, course_selection=course_selection)
        matched_course_name = form_data.pop("_matched_course_name", None)
        matched_tee_name = form_data.pop("_matched_tee_name", None)
        submit_response = client.post(
            str(form_page["url"]),
            data=form_data,
            headers={"Referer": str(form_page["url"])},
        )
        submit_response.raise_for_status()

    result = _submission_result(submit_response.text)
    result.update(
        {
            "marker_guid": marker_guid,
            "marker_name": marker_name,
            "marker_club": marker_club,
            "course_name": matched_course_name or payload["course_name"],
            "tee_name": matched_tee_name or payload["tee_name"],
        }
    )
    return result


def _credentials_or_error(user):
    if not user_has_golfbox_credentials(user):
        raise ValueError("GolfBox-innlogging mangler. Legg inn GolfBox på Min side først.")
    return _credentials_for_user(user)


def _golfbox_client():
    return httpx.Client(
        follow_redirects=True,
        timeout=35,
        headers={"User-Agent": "Mozilla/5.0"},
    )


def _load_score_form(client, credentials):
    _login(client, credentials)
    response = client.get(f"{GOLFBOX_BASE_URL}{SCORE_FORM_PATH}")
    response.raise_for_status()
    return {"url": response.url, "html": response.text}


def score_course_suggestions(user, round_player):
    payload = round_player_score_payload(round_player)
    credentials = _credentials_or_error(user)
    with _golfbox_client() as client:
        form_page = _load_score_form(client, credentials)
        form_data = _form_inputs(form_page["html"])
        form_data.update(_selected_form_values(form_page["html"]))
        return _course_suggestions(client, form_data, payload)


def _build_score_form_data(client, form_page, round_player, payload, marker_guid, course_selection=None):
    page_html = form_page["html"]
    form_data = _form_inputs(page_html)
    form_data.update(_selected_form_values(page_html))

    played_at = payload["played_at"] or server_now()
    form_data["command"] = "save"
    form_data["commandValue"] = ""
    form_data["fld_ScoreDate"] = played_at.strftime("%d.%m.%Y")
    form_data["fld_ScoreTime"] = played_at.strftime("%H:%M")
    form_data["fld_OldHCP"] = str(round_half_up(payload["hcp"] * 10))
    form_data["rdo_RoundType"] = "2"
    form_data["fld_HolesPlayed"] = str(payload["hole_count"])
    form_data["fld_MarkerMemberGUID"] = marker_guid
    form_data["chk_IsCounting"] = "on"
    form_data["chk_InputHoleScores"] = "on"
    form_data["fld_TotalStrokes"] = str(payload["total"])

    match = _match_golfbox_course_and_tee(client, form_data, round_player, payload, course_selection=course_selection)
    form_data["fld_Club"] = match["club_guid"]
    form_data["fld_Course"] = match["course_guid"]
    form_data["fld_Tee"] = match["tee_guid"]
    form_data["isHcpQualifying"] = "1" if match.get("is_hcp_qualifying", True) else "0"
    form_data["fld_CoursePar"] = str(match["course_par"])
    form_data["fld_CourseRating"] = _decimal_comma(match["course_rating"])
    form_data["fld_Slope"] = str(match["slope"])
    form_data["fld_TextPHCP"] = str(match["playing_handicap"])
    form_data["fld_TotalPoints"] = str(_stableford_points(payload, match["playing_handicap"]))
    form_data["fld_TotalAjustedGrossScore"] = str(_adjusted_gross_score(payload, match["playing_handicap"]))
    form_data["_matched_course_name"] = match["course_name"]
    form_data["_matched_tee_name"] = match["tee_name"]

    for index in range(18):
        form_data[f"ScoreHole_{index}"] = ""
    for row in payload["rows"]:
        form_data[f"ScoreHole_{row['hole_number'] - 1}"] = str(row["strokes"])

    return form_data


def _match_golfbox_course_and_tee(client, form_data, round_player, payload, course_selection=None):
    suggestions = _course_suggestions(client, form_data, payload, course_selection=course_selection)
    if course_selection:
        match = suggestions[0] if suggestions else None
        if not match:
            raise ValueError("Bekreftet GolfBox-bane kunne ikke valideres. Velg klubb og bane på nytt.")
        return match
    if len(suggestions) == 1:
        return suggestions[0]
    if suggestions:
        raise ValueError("Bekreft hvilken GolfBox-klubb og bane scoren skal sendes til før innsending.")
    raise ValueError(f"Fant ikke bane i GolfBox for {payload['course_name']}.")


def _course_suggestions(client, form_data, payload, course_selection=None):
    score_date = _score_date_for_api(payload["played_at"] or server_now())
    clubs = _service_call(client, action="GetClubs", countryISO="NO", Club_GUID=form_data.get("fld_Club", ""), lcid="1044")
    selected_club_guid = (course_selection or {}).get("club_guid", "").strip("{}")
    selected_course_guid = (course_selection or {}).get("course_guid", "").strip("{}")
    selected_tee_guid = (course_selection or {}).get("tee_guid", "").strip("{}")

    if selected_club_guid:
        club_candidates = [club for club in clubs if _same_guid(club.get("value"), selected_club_guid)]
    else:
        club_candidates = _best_club_candidates(clubs, payload["course_name"])

    suggestions = []
    for club in club_candidates[:5]:
        courses = _service_call(client, action="GetCourses", ScoreDate=score_date, Club_GUID=club["value"])
        if selected_course_guid:
            course_candidates = [course for course in courses if _same_guid(course.get("course_guid"), selected_course_guid)]
        else:
            course_candidates = _best_course_candidates(courses, payload["course_name"], payload["hole_count"])
        for course in course_candidates[:4]:
            tee = _matched_tee(client, form_data, score_date, course, payload, selected_tee_guid=selected_tee_guid)
            if not tee:
                continue
            stats = _service_call(
                client,
                action="UpdateStats",
                ScoreDate=score_date,
                Course_GUID=course["course_guid"],
                Member_GUID=_member_guid(form_data),
                Tee_GUID=tee["value"],
            )
            data = stats[0] if isinstance(stats, list) and stats else stats
            if not isinstance(data, dict):
                continue
            suggestions.append(_course_match(club, course, tee, data, payload))
            if course_selection:
                return suggestions
    return suggestions


def _matched_tee(client, form_data, score_date, course, payload, selected_tee_guid=None):
    tees = _service_call(
        client,
        action="GetTees",
        ScoreDate=score_date,
        Course_GUID=course["course_guid"],
        Tee_GUID=form_data.get("fld_Tee", ""),
    )
    if selected_tee_guid:
        return next((tee for tee in tees if _same_guid(tee.get("value"), selected_tee_guid)), None)
    tee = _best_option(
        [item for item in tees if (item.get("Gender") or item.get("gender") or "").lower() in ("", "male")],
        payload["tee_name"],
    ) or _best_option(tees, payload["tee_name"])
    return tee


def _course_match(club, course, tee, data, payload):
    return {
        "club_guid": club["value"],
        "club_name": club["text"],
        "course_guid": course["course_guid"],
        "course_name": course["course_name"],
        "tee_guid": tee["value"],
        "tee_name": tee["text"],
        "is_hcp_qualifying": course.get("is_hcp_qualifying", True),
        "course_par": int(data.get("CoursePar") or sum(row["par"] for row in payload["rows"])),
        "course_rating": float(data.get("CR") or 0) / 10000,
        "slope": int(data.get("Slope") or 113),
        "playing_handicap": _playing_handicap_from_stats(data, payload["hcp"]),
    }


def _member_guid(form_data):
    return (
        form_data.get("fld_PlayerMemberGUID")
        or form_data.get("fld_MemberGUID")
        or form_data.get("Member_GUID")
        or ""
    ).strip("{}")


def _service_call(client, **params):
    response = client.get(
        f"{GOLFBOX_BASE_URL}/site/score/whs/api/serviceCaller.asp",
        params=params,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("Success", True):
        raise ValueError(data.get("Message") or "GolfBox-oppslag feilet.")
    rows = data.get("Data") or []
    if isinstance(rows, dict):
        return rows
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized.append(_normalize_api_option(row))
    return normalized


def _normalize_api_option(row):
    value = row.get("value") or row.get("Value") or row.get("Club_GUID") or row.get("Course_GUID") or row.get("Guid")
    text = row.get("text") or row.get("Text") or row.get("Club_Name") or row.get("Course_Name") or row.get("Name")
    normalized = dict(row)
    normalized["value"] = str(value or "").strip("{}")
    normalized["text"] = str(text or "").strip()
    if row.get("Course_GUID"):
        normalized["course_guid"] = str(row["Course_GUID"]).strip("{}")
        normalized["course_name"] = str(row.get("Course_Name") or "").strip()
        normalized["is_hcp_qualifying"] = _truthy(row.get("Course_isHcpQualifying", True))
    return normalized


def _parse_marker_search_results(page_html):
    select_match = re.search(r"<select[^>]+id=[\"']slc_MarkerSearch4result[\"'][^>]*>(.*?)</select>", page_html, re.I | re.S)
    if not select_match:
        return []
    markers = []
    for option_match in re.finditer(r"<option\b(?P<attrs>[^>]*)>(?P<label>.*?)</option>", select_match.group(1), re.I | re.S):
        raw_value = _attr_value(option_match.group("attrs"), "value")
        if not raw_value:
            continue
        raw_json = raw_value.replace("'", '"')
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        markers.append(
            {
                "guid": str(data.get("g") or "").strip(),
                "name": str(data.get("n") or "").strip(),
                "club": str(data.get("c") or "").strip(),
                "national_right": bool(data.get("nat")),
                "local_right": bool(data.get("loc")),
                "label": " ".join(re.sub(r"<[^>]+>", " ", option_match.group("label")).split()),
            }
        )
    return [marker for marker in markers if marker["guid"] and marker["name"]]


def _selected_form_values(page_html):
    values = {}
    for select_match in re.finditer(r"<select\b(?P<attrs>[^>]*)>(?P<body>.*?)</select>", page_html, re.I | re.S):
        name = _attr_value(select_match.group("attrs"), "name")
        if not name:
            continue
        selected = re.search(r"<option\b(?P<attrs>[^>]*)selected[^>]*>", select_match.group("body"), re.I | re.S)
        option = selected or re.search(r"<option\b(?P<attrs>[^>]*)>", select_match.group("body"), re.I | re.S)
        if option:
            values[name] = _attr_value(option.group("attrs"), "value")
    return values


def _attr_value(attrs, attr_name):
    match = re.search(rf"{re.escape(attr_name)}=(?P<quote>[\"'])(?P<value>.*?)(?P=quote)", attrs, re.I | re.S)
    return html.unescape(match.group("value")) if match else ""


def _best_option(options, requested):
    requested_key = _normalize_name(requested)
    if not requested_key and options:
        return options[0]
    for option in options:
        if _normalize_name(option.get("text")) == requested_key:
            return option
    for option in options:
        option_key = _normalize_name(option.get("text"))
        if requested_key and (requested_key in option_key or option_key in requested_key):
            return option
    requested_words = {word for word in requested_key.split() if len(word) > 2 and word not in {"golf", "golfklubb", "hull"}}
    for option in options:
        option_words = set(_normalize_name(option.get("text")).split())
        if requested_words and requested_words.issubset(option_words):
            return option
    return None


def _best_course(courses, requested, hole_count):
    candidates = _best_course_candidates(courses, requested, hole_count)
    return candidates[0] if candidates else None


def _best_club_candidates(clubs, requested):
    scored = [
        (_name_match_score(club.get("text"), _club_search_name(requested), club=True), club)
        for club in clubs
    ]
    matches = [item for score, item in sorted(scored, key=lambda row: row[0], reverse=True) if score > 0]
    return matches[:5]


def _best_course_candidates(courses, requested, hole_count):
    hole_text = f"{hole_count} hull"
    normalized_hole_text = _normalize_name(hole_text)
    matching_holes = [
        course
        for course in courses
        if normalized_hole_text in _normalize_name(course.get("course_name"))
    ]
    if len(matching_holes) == 1:
        return matching_holes

    source = matching_holes or courses
    scored = []
    for course in source:
        score = _name_match_score(course.get("course_name"), requested)
        if normalized_hole_text in _normalize_name(course.get("course_name")):
            score += 35
        if "ballrenne" in _normalize_name(course.get("course_name")):
            score -= 30
        scored.append((score, course))
    matches = [item for score, item in sorted(scored, key=lambda row: row[0], reverse=True) if score > 0]
    return matches[:6]


def _club_search_name(course_name):
    first_word = (course_name or "").split()[0] if course_name else ""
    return f"{first_word} Golfklubb" if first_word else course_name


def _normalize_name(value):
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-zæøå]+", " ", (value or "").lower())).strip()


def _name_words(value, club=False):
    words = set(_normalize_name(value).split())
    aliases = {
        "golfbane": "golf",
        "golfklubb": "golf",
        "gk": "golf",
        "golfclub": "golf",
        "club": "golf",
    }
    expanded = set()
    for word in words:
        expanded.add(aliases.get(word, word))
    ignored = {"hull", "golf"} if not club else {"golf"}
    return {word for word in expanded if len(word) > 1 and word not in ignored}


def _name_match_score(option_name, requested, club=False):
    option_key = _normalize_name(option_name)
    requested_key = _normalize_name(requested)
    if not option_key or not requested_key:
        return 0
    if option_key == requested_key:
        return 120
    score = 0
    if requested_key in option_key or option_key in requested_key:
        score += 80
    option_words = _name_words(option_name, club=club)
    requested_words = _name_words(requested, club=club)
    overlap = option_words & requested_words
    if overlap:
        score += 30 * len(overlap)
    if requested_words and requested_words.issubset(option_words):
        score += 40
    if option_words and option_words.issubset(requested_words):
        score += 25
    return score


def _same_guid(left, right):
    return str(left or "").strip("{}").lower() == str(right or "").strip("{}").lower()


def _truthy(value):
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"false", "0", "no", "nei"}:
        return False
    if text in {"true", "1", "yes", "ja"}:
        return True
    return bool(value)


def _score_date_for_api(value):
    return value.strftime("%Y%m%dT%H%M%S")


def _decimal_comma(value):
    return str(value).replace(".", ",")


def _playing_handicap_from_stats(data, hcp):
    value = data.get("PHCP") or data.get("PlayingHandicap") or data.get("CourseHandicap") or ""
    if str(value).strip():
        return str(value).strip()
    try:
        slope = int(data.get("Slope") or 113)
        course_rating = float(data.get("CR") or 0) / 10000
        course_par = int(data.get("CoursePar") or 0)
        return round_half_up((hcp * slope / 113) + course_rating - course_par)
    except (TypeError, ValueError):
        return ""


def _adjusted_gross_score(payload, playing_handicap):
    return sum(
        min(row["strokes"], _maximum_hole_score(row, playing_handicap))
        for row in payload["rows"]
        if row["strokes"] is not None
    )


def _maximum_hole_score(row, playing_handicap):
    if int(playing_handicap or 0) > 54:
        return row["par"] + 5
    return row["par"] + _extra_strokes_for_hole(row["stroke_index"], playing_handicap) + 2


def _stableford_points(payload, playing_handicap):
    total = 0
    for row in payload["rows"]:
        if row["strokes"] is None:
            continue
        net_score = row["strokes"] - _extra_strokes_for_hole(row["stroke_index"], playing_handicap)
        total += max(row["par"] - net_score + 2, 0)
    return total


def _extra_strokes_for_hole(stroke_index, playing_handicap):
    try:
        index = int(stroke_index or 0)
        handicap = int(playing_handicap or 0)
    except (TypeError, ValueError):
        return 0
    if index <= 0 or handicap == 0:
        return 0
    if handicap > 0:
        return (handicap // 18) + (1 if index <= handicap % 18 else 0)
    return -((-handicap // 18) + (1 if index > 18 - (-handicap % 18) else 0))


def _submission_result(page_html):
    text = " ".join(re.sub(r"<[^>]+>", " ", page_html).split())
    lowered = text.lower()
    if "error '800" in lowered or "/classes/clsarray.asp" in lowered:
        raise ValueError("GolfBox returnerte en teknisk feil ved lagring. Scoren ble ikke bekreftet som sendt.")
    status = "submitted"
    message = "Scoren er sendt til GolfBox. Kontroller GolfBox for endelig godkjenning."
    if "til godkjennelse" in lowered or "godkjennelse" in lowered:
        message = "Scoren er sendt til GolfBox og ligger til godkjenning."
    return {
        "status": status,
        "message": message,
        "response_excerpt": text[:1000],
    }


def _tee_length(round_player, hole):
    if not round_player.selected_tee_id:
        return None
    length = CourseTeeLength.query.filter_by(
        tee_id=round_player.selected_tee_id,
        hole_number=hole.hole_number,
    ).first()
    return length.length_meters if length else None
