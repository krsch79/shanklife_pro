"""Conservative projection of original TrackMan scorecards for statistics."""
import json
from datetime import datetime

from extensions import db
from services.stats_summary import round_score_summary
from services.trackman_models import TrackManRound

ENVIRONMENTS = {"all": "Inne og ute", "simulator": "Kun simulator", "outdoor": "Kun utendørs"}


def environment_filter(value):
    return value if value in ENVIRONMENTS else "all"


def number(value):
    return value if isinstance(value, (float, int)) and not isinstance(value, bool) else None


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def project_scorecard(data):
    # Range games/closest-to-pin have scorecards but are not golf rounds.
    if data.get("kind") != "CoursePlay":
        return None
    kind = data.get("bayKind")
    environment = "simulator" if kind == "SIMULATOR_BAY" else "outdoor" if kind in {"ON_COURSE", "ON_COURSE_BAY"} else "unknown"
    holes = []
    for hole in data.get("holes") or []:
        if not isinstance(hole, dict) or hole.get("isPlayed") is not True:
            continue
        score = number(hole.get("grossScore"))
        if score is None or score <= 0:
            continue
        shots = [shot for shot in hole.get("shots") or [] if isinstance(shot, dict)]
        first_shot = min(shots, key=lambda shot: shot.get("shotNumber") or 0) if shots else None
        tee_shot = {"club": first_shot.get("club"), "total": number(first_shot.get("total")) if number(first_shot.get("total")) is not None else number((first_shot.get("measurement") or {}).get("total")), "carry": number((first_shot.get("measurement") or {}).get("carry")), "lie": first_shot.get("finalLie")} if first_shot else None
        holes.append({"tee_shot": tee_shot, "number": hole.get("holeNumber"), "par": number(hole.get("par")), "strokes": score, "putts": number(hole.get("putts")), "gir": hole.get("greenInRegulation") if isinstance(hole.get("greenInRegulation"), bool) else None, "mulligans": number(hole.get("mulligans")), "gimme": hole.get("gimmeWasGiven")})
    total = sum(h["strokes"] for h in holes) if holes else None
    par = sum(h["par"] for h in holes) if holes and all(h["par"] is not None for h in holes) else None
    expected = number(data.get("numberOfHolesToPlay"))
    complete = data.get("isCompleted") is True and expected in (9, 18) and len(holes) == expected and total == number(data.get("grossScore"))
    stat = data.get("stat") or {}
    setting = data.get("gameSettings") or {}
    putting = setting.get("puttingSettings") or {}
    # TrackMan often fills zero putts when automatic putting is used. Preserve
    # those raw values, but never mix them with physically measured putting.
    automatic = putting.get("isAuto") is not False or putting.get("puttingMode") not in {"MANUAL_AIMED", "MANUAL", "MANUAL_INPUT"}
    return {"environment": environment, "course_name": (data.get("course") or {}).get("displayName") or "Ukjent TrackMan-bane", "started_at": parse_time(data.get("startedAt") or data.get("createdAt")), "completed": complete, "holes_to_play": expected, "summary": {"holes": holes, "total": total, "par": par, "tee_name": data.get("teeName"), "stat": stat, "automatic_putting": automatic, "putting_mode": putting.get("puttingMode"), "mulligans": data.get("mulligans"), "game_score": setting.get("gameScore"), "team": data.get("isTeamScorecard")}}


def save_scorecard(user_id, data):
    projected = project_scorecard(data)
    if not projected:
        return
    row = TrackManRound.query.filter_by(user_id=user_id, remote_id=data["id"]).first()
    if row is None:
        row = TrackManRound(user_id=user_id, remote_id=data["id"])
        db.session.add(row)
    for key, value in projected.items():
        setattr(row, key, json.dumps(value, ensure_ascii=False) if key == "summary" else value)


def user_rounds(user_id, environment="all"):
    query = TrackManRound.query.filter_by(user_id=user_id)
    # Unknown environments are available in the archive, never guessed into a
    # combined comparison. Unknown and practice activities have their own page.
    query = query.filter(TrackManRound.environment.in_(["simulator", "outdoor"]) if environment == "all" else TrackManRound.environment == environment)
    return query.order_by(TrackManRound.started_at.desc(), TrackManRound.id.desc()).all()



def hole_putting(hole, summary):
    """TrackMan's putts already includes the conceded final stroke.

    Keep recorded/manual, conceded and automatically assigned counts distinct.
    Missing concession flags cannot establish a played-putt count. Unknown
    putting modes cannot establish an automatically assigned count either.
    """
    putts = number(hole.get("putts"))
    if putts is not None and (putts < 0 or int(putts) != putts):
        putts = None
    gimme = hole.get("gimme")
    gimmes = int(gimme) if isinstance(gimme, bool) else None
    automatic = summary["automatic_putting"]
    if gimmes == 1 and putts is not None and putts < 1:
        putts = None  # Contradictory upstream counts remain in the raw archive.
    return {
        "putts": putts if not automatic else None,
        "played_putts": putts - gimmes if not automatic and putts is not None and gimmes is not None else None,
        "gimmes": gimmes,
        "automatic_putts": putts if automatic and str(summary.get("putting_mode") or "").startswith("AUTO") else None,
    }


def putting_stats(observations):
    """Pool independent known samples and expose their denominators."""
    result = {}
    for source, total_key, count_key in (
        ("putts", "putts_total", "putting_holes"),
        ("played_putts", "played_putts_total", "played_putting_holes"),
        ("gimmes", "gimmes_total", "gimme_recorded_holes"),
        ("automatic_putts", "automatic_putts_total", "automatic_putting_holes"),
    ):
        values = [row.get(source) for row in observations if row.get(source) is not None]
        result[total_key] = sum(values) if values else None
        result[count_key] = len(values)
    for average, total, count in (
        ("avg_putts", "putts_total", "putting_holes"),
        ("avg_played_putts", "played_putts_total", "played_putting_holes"),
    ):
        result[average] = round(result[total] / result[count], 1) if result[count] else None
    return result


def row_summary(row):
    s = json.loads(row.summary)
    scored = s["holes"]
    diffs = [h["strokes"] - h["par"] for h in scored if h["par"] is not None]
    gir = [h["gir"] for h in scored if h["gir"] is not None]
    putting = putting_stats([hole_putting(h, s) for h in scored])
    fw = [number(s["stat"].get(k)) for k in ("fairwayHitFairway", "fairwayHitLeft", "fairwayHitRight")]
    attempts = sum(fw) if all(v is not None for v in fw) else 0
    return {"trackman_id": row.id, "round_id": None, "started_at": row.started_at, "course_name": row.course_name, "tee_name": s.get("tee_name") or "—", "holes": len(scored), "total": s["total"], "to_par": s["total"] - s["par"] if s["total"] is not None and s["par"] is not None else None, "gir_percent": round(sum(gir) / len(gir) * 100, 1) if gir else None, "fairway_hit_percent": round(fw[0] / attempts * 100, 1) if attempts else None, "fairway_left_percent": round(fw[1] / attempts * 100, 1) if attempts else None, "fairway_right_percent": round(fw[2] / attempts * 100, 1) if attempts else None, **putting, "birdies": sum(d == -1 for d in diffs), "pars": sum(d == 0 for d in diffs), "bogeys": sum(d == 1 for d in diffs), "double_bogeys_or_worse": sum(d >= 2 for d in diffs), "environment": row.environment, "completed": row.completed, "team": s.get("team", False), "holes_to_play": row.holes_to_play, "automatic_putting": s["automatic_putting"], "mulligans": s.get("mulligans")}


def merge_stats(stats, trackman_rows):
    """Pool samples/numerators, never average already rounded percentages."""
    samples = stats.pop("_samples")
    completed = stats.pop("_completed")
    clubs = samples.get("clubs", {})
    putting = [{"putts": value, "played_putts": value} for value in samples["putts"]]
    stats["fairway_detail_attempts"] = samples["fairway_attempts"]
    stats["fairway_details_environment"] = "outdoor"
    for row in trackman_rows:
        s = json.loads(row.summary)
        summary = row_summary(row)
        stats["round_rows"].append(summary)
        if s.get("team") or str(s.get("game_score", "")).lower().startswith("match"):
            continue
        stats["round_count"] += 1
        stats["scored_holes"] += len(s["holes"])
        if row.completed:
            completed.append({"holes": len(s["holes"]), "total": s["total"], "par": s["par"]})
            stats["completed_round_count"] += 1
        for h in s["holes"]:
            shot = h.get("tee_shot")
            if h.get("par") in (4, 5) and shot:
                name = shot.get("club") or "Ukjent kølle (TrackMan)"
                bucket = clubs.setdefault(name, {"count": 0, "strokes": [], "drive_distances": [], "hit": 0, "left": 0, "right": 0, "fw_count": 0})
                bucket["count"] += 1
                bucket["strokes"].append(h["strokes"])
                bucket["drive_distances"].append(shot.get("total"))
            if h["par"] is not None:
                d = h["strokes"] - h["par"]
                key = "eagles_or_better" if d <= -2 else "birdies" if d == -1 else "pars" if d == 0 else "bogeys" if d == 1 else "double_bogeys_or_worse"
                stats[key] += 1
            if h["gir"] is not None:
                samples["gir_count"] += int(h["gir"])
                samples["gir_attempts"] += 1
            putting.append(hole_putting(h, s))
        fw = [number(s["stat"].get(k)) for k in ("fairwayHitFairway", "fairwayHitLeft", "fairwayHitRight")]
        if all(v is not None for v in fw):
            for key, value in zip(("hit", "left", "right"), fw):
                samples["fairway"][key] += value
            samples["fairway_attempts"] += sum(fw)
    stats.update(round_score_summary(completed))
    stats["gir_percent"] = round(samples["gir_count"] / samples["gir_attempts"] * 100, 1) if samples["gir_attempts"] else None
    stats.update(putting_stats(putting))
    stats["fairway_attempts"] = samples["fairway_attempts"]
    for key in ("hit", "left", "right"):
        stats["fairway_" + key + "_percent"] = round(samples["fairway"][key] / samples["fairway_attempts"] * 100, 1) if samples["fairway_attempts"] else None
    from routes.stats import _avg_normal_drive_distance
    stats["club_rows"] = [{"name": name, "count": b["count"], "avg": round(sum(b["strokes"]) / len(b["strokes"]), 1) if b["strokes"] else None, "avg_drive_distance": _avg_normal_drive_distance(b["drive_distances"]), "fairway_percent": round(b["hit"] / b["fw_count"] * 100, 1) if b["fw_count"] else None, "left_percent": round(b["left"] / b["fw_count"] * 100, 1) if b["fw_count"] else None, "right_percent": round(b["right"] / b["fw_count"] * 100, 1) if b["fw_count"] else None} for name, b in clubs.items()]
    stats["club_rows"].sort(key=lambda r: (-r["count"], r["name"]))
    stats["round_rows"].sort(key=lambda r: r["started_at"] or datetime.min, reverse=True)
    stats["environment_labels"] = ENVIRONMENTS
    return stats
