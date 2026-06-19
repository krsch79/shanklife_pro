def score_to_par_for_entries(entries, par_by_hole, excluded_hole_number=None):
    total = 0
    for entry in entries:
        if entry.hole_number == excluded_hole_number or entry.strokes is None:
            continue
        par = par_by_hole.get(entry.hole_number)
        if par is None:
            continue
        total += entry.strokes - par
    return total
