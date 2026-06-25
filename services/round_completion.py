def validate_score_putts(putts, score):
    if score is None or putts is None:
        return

    if putts > 0 and putts > score - 1:
        raise ValueError("Score må være minst én mer enn antall putter.")


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

    return missing
