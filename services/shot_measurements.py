import json
import math


MAX_SHOT_MEASUREMENTS_PER_HOLE = 25
MAX_SHOT_DISTANCE_M = 1000


def haversine_distance_m(start_lat, start_lng, end_lat, end_lng):
    earth_radius_m = 6371000
    lat1 = math.radians(start_lat)
    lat2 = math.radians(end_lat)
    delta_lat = math.radians(end_lat - start_lat)
    delta_lng = math.radians(end_lng - start_lng)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_m * c


def parse_shot_measurements(raw_json):
    raw_json = (raw_json or "").strip()
    if not raw_json:
        return []

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError("GPS-målinger kunne ikke leses.") from exc

    if not isinstance(payload, list):
        raise ValueError("GPS-målinger har ugyldig format.")
    if len(payload) > MAX_SHOT_MEASUREMENTS_PER_HOLE:
        raise ValueError(f"Det kan maks lagres {MAX_SHOT_MEASUREMENTS_PER_HOLE} GPS-målinger per hull.")

    rows = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError("GPS-målinger har ugyldig format.")
        start = item.get("start") or {}
        end = item.get("end") or {}
        if not isinstance(start, dict) or not isinstance(end, dict):
            raise ValueError("GPS-målinger må ha start- og stoppunkt.")

        start_lat = _required_coordinate(start.get("lat"), -90, 90, "start-breddegrad")
        start_lng = _required_coordinate(start.get("lng"), -180, 180, "start-lengdegrad")
        end_lat = _required_coordinate(end.get("lat"), -90, 90, "stopp-breddegrad")
        end_lng = _required_coordinate(end.get("lng"), -180, 180, "stopp-lengdegrad")
        start_accuracy = _optional_float(start.get("accuracy_m"), 0, 1000, "start-presisjon")
        end_accuracy = _optional_float(end.get("accuracy_m"), 0, 1000, "stopp-presisjon")
        distance = _optional_float(item.get("distance_m"), 0.1, MAX_SHOT_DISTANCE_M, "slaglengde")
        if distance is None:
            distance = haversine_distance_m(start_lat, start_lng, end_lat, end_lng)
        if distance <= 0 or distance > MAX_SHOT_DISTANCE_M:
            raise ValueError(f"GPS-målt slag {index} må være mellom 0 og {MAX_SHOT_DISTANCE_M} meter.")

        rows.append({
            "shot_number": index,
            "start_lat": start_lat,
            "start_lng": start_lng,
            "start_accuracy_m": start_accuracy,
            "end_lat": end_lat,
            "end_lng": end_lng,
            "end_accuracy_m": end_accuracy,
            "distance_m": round(distance, 1),
        })
    return rows


def _required_coordinate(value, minimum, maximum, label):
    parsed = _optional_float(value, minimum, maximum, label)
    if parsed is None:
        raise ValueError(f"GPS-måling mangler {label}.")
    return parsed


def _optional_float(value, minimum, maximum, label):
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"GPS-måling har ugyldig {label}.") from exc
    if not math.isfinite(parsed) or parsed < minimum or parsed > maximum:
        raise ValueError(f"GPS-måling har ugyldig {label}.")
    return parsed
