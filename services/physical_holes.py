import re
import unicodedata
from collections import defaultdict
from hashlib import sha1


def normalize_physical_value(value):
    value = " ".join(str(value or "").strip().split())
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def _display_name(value):
    value = " ".join(str(value or "").strip().split())
    return value.upper() if len(value) <= 3 else value.title()


def infer_physical_hole_identity(course_name, hole_number, hole_count):
    """Infer loop identity from course names like 'Haga Blå+Gul'."""
    if hole_count not in (9, 18):
        return None

    name = " ".join(str(course_name or "").strip().split())
    if "+" not in name:
        return None

    match = re.match(r"^(?P<group>.+?)\s+(?P<loops>[^+\s]+(?:\s*\+\s*[^+\s]+)+)$", name)
    if not match:
        return None

    loops = [part.strip() for part in match.group("loops").split("+") if part.strip()]
    if not loops:
        return None

    hole_number = int(hole_number)
    if hole_number < 1 or hole_number > hole_count:
        return None

    loop_index = 0 if hole_number <= 9 else 1
    if loop_index >= len(loops):
        return None

    return {
        "physical_course_group": _display_name(match.group("group")),
        "physical_loop": _display_name(loops[loop_index]),
        "physical_hole_number": ((hole_number - 1) % 9) + 1,
    }


def _course_holes_by_number(course):
    return {hole.hole_number: hole for hole in course.holes}


def _tee_lengths_by_hole(course):
    lengths = defaultdict(list)
    for tee in sorted(course.tees, key=lambda item: item.display_order):
        for length in tee.lengths:
            lengths[length.hole_number].append(length.length_meters)
    return {
        hole_number: tuple(sorted(values))
        for hole_number, values in lengths.items()
    }


def loop_segment_signature(course, start_hole_number):
    holes = _course_holes_by_number(course)
    lengths_by_hole = _tee_lengths_by_hole(course)
    rows = []
    for offset in range(9):
        hole_number = start_hole_number + offset
        hole = holes.get(hole_number)
        if not hole:
            return None
        lengths = lengths_by_hole.get(hole_number)
        if not lengths:
            return None
        rows.append((hole.par, lengths))
    return tuple(rows)


def _loop_segments(course):
    if course.hole_count == 9:
        return [(1, range(1, 10))]
    if course.hole_count == 18:
        return [(1, range(1, 10)), (10, range(10, 19))]
    return []


def _segment_identity(course, hole_numbers):
    holes = _course_holes_by_number(course)
    group = None
    loop = None
    seen_physical_numbers = set()
    for expected_number, hole_number in enumerate(hole_numbers, start=1):
        hole = holes.get(hole_number)
        if not hole:
            return None
        hole_group = (hole.physical_course_group or "").strip()
        hole_loop = (hole.physical_loop or "").strip()
        physical_number = hole.physical_hole_number
        if not hole_group or not hole_loop or physical_number != expected_number:
            return None
        group = group or hole_group
        loop = loop or hole_loop
        if hole_group != group or hole_loop != loop:
            return None
        seen_physical_numbers.add(physical_number)
    if seen_physical_numbers != set(range(1, 10)):
        return None
    return {"physical_course_group": group, "physical_loop": loop}


def _auto_identity_for_signature(signature):
    digest = sha1(repr(signature).encode("utf-8")).hexdigest()[:8].upper()
    return {
        "physical_course_group": "Auto",
        "physical_loop": f"Sløyfe {digest}",
    }


def assign_physical_identities_from_loop_signatures(courses):
    """Fill missing physical hole identities by matching equal 9-hole loop signatures."""
    signature_identities = defaultdict(set)
    segments = []

    for course in courses:
        for start_hole, hole_numbers in _loop_segments(course):
            signature = loop_segment_signature(course, start_hole)
            if not signature:
                continue
            identity = _segment_identity(course, hole_numbers)
            if identity:
                signature_identities[signature].add(
                    (identity["physical_course_group"], identity["physical_loop"])
                )
            segments.append((course, start_hole, tuple(hole_numbers), signature))

    changed = False
    for course, _start_hole, hole_numbers, signature in segments:
        existing_identity = _segment_identity(course, hole_numbers)
        if existing_identity:
            continue

        known_identities = signature_identities.get(signature, set())
        if len(known_identities) == 1:
            group, loop = next(iter(known_identities))
            identity = {"physical_course_group": group, "physical_loop": loop}
        elif not known_identities:
            identity = _auto_identity_for_signature(signature)
        else:
            continue

        holes = _course_holes_by_number(course)
        for physical_number, hole_number in enumerate(hole_numbers, start=1):
            hole = holes[hole_number]
            if not (hole.physical_course_group or "").strip():
                hole.physical_course_group = identity["physical_course_group"]
                changed = True
            if not (hole.physical_loop or "").strip():
                hole.physical_loop = identity["physical_loop"]
                changed = True
            if not hole.physical_hole_number:
                hole.physical_hole_number = physical_number
                changed = True

    return changed


def physical_hole_label(hole):
    group = (getattr(hole, "physical_course_group", None) or "").strip()
    loop = (getattr(hole, "physical_loop", None) or "").strip()
    number = getattr(hole, "physical_hole_number", None)
    if not group or not loop or not number:
        return None
    return f"{group} {loop} hull {number}"


def physical_hole_filter_values(hole):
    group = " ".join(str(getattr(hole, "physical_course_group", "") or "").lower().split())
    loop = " ".join(str(getattr(hole, "physical_loop", "") or "").lower().split())
    number = getattr(hole, "physical_hole_number", None)
    if not group or not loop or not number:
        return None
    return group, loop, int(number)
