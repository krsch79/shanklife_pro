TEE_FILTERS = (
    {"key": "gul", "label": "Gul"},
    {"key": "rod", "label": "Rød"},
)


def tee_key_for_name(name):
    normalized = (name or "").strip().lower()
    if "gul" in normalized:
        return "gul"
    if "rød" in normalized or "rod" in normalized:
        return "rod"
    return None


def selected_tee_key(raw_value=None):
    normalized = (raw_value or "").strip().lower()
    if normalized in ("rød", "rod", "red"):
        return "rod"
    return "gul"


def tee_filter_options(course=None):
    available_keys = set()
    if course:
        for tee in course.tees:
            key = tee_key_for_name(tee.name)
            if key:
                available_keys.add(key)

    options = []
    for item in TEE_FILTERS:
        if not available_keys or item["key"] in available_keys:
            options.append(item)
    return options


def tee_ids_for_key(course, key):
    if not course:
        return []
    tee_ids = [
        tee.id
        for tee in course.tees
        if tee_key_for_name(tee.name) == key
    ]
    return tee_ids or [-1]


def round_player_matches_tee(round_player, key):
    return bool(
        round_player
        and round_player.selected_tee
        and tee_key_for_name(round_player.selected_tee.name) == key
    )
