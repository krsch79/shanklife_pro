import re
import unicodedata


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
