STROKE_PLAY = "stroke_play"
MATCHPLAY = "matchplay"

PLAY_FORMAT_LABELS = {
    STROKE_PLAY: "Slagspill",
    MATCHPLAY: "Matchplay",
}

MATCHPLAY_HOLE_RESULTS = ("won", "lost", "halved")
MATCHPLAY_HOLE_RESULT_LABELS = {
    "won": "Vunnet",
    "lost": "Tapt",
    "halved": "Delt",
}


def normalize_play_format(value):
    value = (value or STROKE_PLAY).strip()
    if value not in PLAY_FORMAT_LABELS:
        raise ValueError("Ugyldig spilleform.")
    return value


def play_format_label(value):
    return PLAY_FORMAT_LABELS.get(value or STROKE_PLAY, value or PLAY_FORMAT_LABELS[STROKE_PLAY])


def is_matchplay_round(round_obj):
    return getattr(round_obj, "play_format", STROKE_PLAY) == MATCHPLAY


def matchplay_hole_result_label(value):
    return MATCHPLAY_HOLE_RESULT_LABELS.get(value or "", "—")
