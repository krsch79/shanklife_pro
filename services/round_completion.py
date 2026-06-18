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
