def validate_score_stat_combination(par, fairway_result, putts, score):
    if score is None:
        return

    putts = putts or 0
    if putts > 0 and putts > score - 1:
        raise ValueError("Antall putter må være 0, eller mellom 1 og score minus 1.")

    if par != 3:
        return

    raw_result = (fairway_result or "hit").strip()
    status = raw_result.partition(":")[0]
    if status in ("left", "right", "short", "long"):
        status = "miss"
    if status == "hit":
        return

    if score < putts + 2:
        raise ValueError("Ved miss eller bunker må total score være minst 2 slag pluss antall putter.")


def missing_saved_entry_choices(entry, hole, tracks_stats, club_required):
    if not entry or entry.strokes is None:
        return ["score"]

    missing = []
    if club_required and not entry.tee_club_id:
        missing.append("kølle")

    if not tracks_stats:
        return missing

    stat = entry.detailed_stat
    if hole.par == 3 and (not stat or not stat.fairway_result):
        missing.append("green")
    elif hole.par in (4, 5) and (not stat or not stat.fairway_result):
        missing.append("fairway")

    if not stat or stat.putts is None:
        missing.append("putter")
    elif stat.putts > 0 and stat.last_putt_distance_m is None:
        missing.append("siste putt")
    return missing
