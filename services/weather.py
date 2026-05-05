import json
import os
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from services.time import to_server_time


BEKKESTUA_LATITUDE = 59.9173
BEKKESTUA_LONGITUDE = 10.5876
MET_API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
WEATHER_USER_AGENT = os.environ.get(
    "MET_USER_AGENT",
    "ShanklifePro/1.0 kristian.schiander@gmail.com",
)

SYMBOL_TEXT = {
    "clearsky": "Klart",
    "fair": "Lettskyet",
    "partlycloudy": "Delvis skyet",
    "cloudy": "Overskyet",
    "rain": "Regn",
    "lightrain": "Lett regn",
    "heavyrain": "Kraftig regn",
    "snow": "Snø",
    "lightsnow": "Lett snø",
    "fog": "Tåke",
}

DIRECTION_TEXT = [
    "nord",
    "nord-øst",
    "øst",
    "sør-øst",
    "sør",
    "sør-vest",
    "vest",
    "nord-vest",
]


def _parse_time(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _target_utc(target_time=None):
    target_time = target_time or datetime.now()
    if target_time.tzinfo is None:
        return target_time.astimezone().astimezone(timezone.utc)
    return target_time.astimezone(timezone.utc)


def _symbol_text(symbol_code):
    if not symbol_code:
        return "Ukjent vær"
    base = symbol_code.split("_", 1)[0]
    return SYMBOL_TEXT.get(base, base.replace("_", " ").capitalize())


def _wind_direction_text(degrees):
    if degrees is None:
        return ""
    index = round((degrees % 360) / 45) % 8
    return DIRECTION_TEXT[index]


def summarize_weather_payload(payload):
    if not payload:
        return "Vær ikke tilgjengelig"
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return "Vær ikke tilgjengelig"

    text = payload.get("summary") or _symbol_text(payload.get("symbol_code"))
    temperature = payload.get("air_temperature")
    wind_speed = payload.get("wind_speed")
    wind_from = _wind_direction_text(payload.get("wind_from_direction"))

    parts = [text]
    if temperature is not None:
        parts.append(f"{temperature:g} grader")
    if wind_speed is not None:
        wind_text = f"{wind_speed:g} m/s vind"
        if wind_from:
            wind_text += f" fra {wind_from}"
        parts.append(wind_text)
    return ", ".join(parts)


def fetch_bekkestua_weather(target_time=None):
    query = urlencode({
        "lat": f"{BEKKESTUA_LATITUDE:.4f}",
        "lon": f"{BEKKESTUA_LONGITUDE:.4f}",
    })
    request = Request(
        f"{MET_API_URL}?{query}",
        headers={"User-Agent": WEATHER_USER_AGENT},
    )
    with urlopen(request, timeout=6) as response:
        data = json.loads(response.read().decode("utf-8"))

    timeseries = data.get("properties", {}).get("timeseries", [])
    if not timeseries:
        return None

    target = _target_utc(target_time)
    candidates = []
    for item in timeseries:
        item_time = _parse_time(item.get("time"))
        if item_time:
            candidates.append((abs((item_time - target).total_seconds()), item_time, item))
    if not candidates:
        return None

    _distance, item_time, item = min(candidates, key=lambda candidate: candidate[0])
    details = item.get("data", {}).get("instant", {}).get("details", {})
    next_1h = item.get("data", {}).get("next_1_hours", {}).get("summary", {})
    next_6h = item.get("data", {}).get("next_6_hours", {}).get("summary", {})
    symbol_code = next_1h.get("symbol_code") or next_6h.get("symbol_code")

    payload = {
        "provider": "api.met.no Locationforecast",
        "place": "Bekkestua",
        "latitude": BEKKESTUA_LATITUDE,
        "longitude": BEKKESTUA_LONGITUDE,
        "forecast_time": to_server_time(item_time).isoformat(timespec="minutes"),
        "fetched_at": datetime.now().isoformat(timespec="minutes"),
        "symbol_code": symbol_code,
        "summary": _symbol_text(symbol_code),
        "air_temperature": details.get("air_temperature"),
        "wind_speed": details.get("wind_speed"),
        "wind_from_direction": details.get("wind_from_direction"),
    }
    payload["summary_text"] = summarize_weather_payload(payload)
    return payload
