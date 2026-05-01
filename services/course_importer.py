# Generated: 2026-04-18
# Version: 1.0.0

import base64
import json
import os

from openai import OpenAI

PROMPT_VERSION_SCORECARD = "2.2"
PROMPT_VERSION_SLOPE = "1.0"


def allowed_file(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in {"jpg", "jpeg", "png", "webp"}


def extract_json_from_text(text: str):
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Fant ikke JSON i AI-respons.")
    return json.loads(text[start:end + 1])


def _normalize_int(value, default=""):
    if value is None:
        return default
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text == "":
        return default
    try:
        return int(text)
    except ValueError:
        return default


def _normalize_float(value, default=""):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if text == "":
        return default
    try:
        return float(text)
    except ValueError:
        return default


def analyze_scorecard_with_openai(image_path: str):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    with open(image_path, "rb") as f:
        image = base64.b64encode(f.read()).decode()

    prompt = f"""
PROMPT_VERSION: {PROMPT_VERSION_SCORECARD}

Du får et bilde av et golf-scorekort.

Oppgave:
Les scorekortet og returner KUN gyldig JSON.

Scorekort kan være:
- horisontale (hull bortover)
- vertikale (hull nedover)

VIKTIG:
- Finn først hvordan hullene er organisert.
- Bruk kun én konsistent hovedtabell.
- Ikke bland data fra ulike deler av bildet.

KRITISK FOR INDEX:
- Bruk KUN én handicap/index-rad eller kolonne.
- Ikke bland flere handicap-rader.
- Prioriter "Men’s Handicap" hvis den finnes.
- Hvis det finnes flere mulige tolkninger for et index-felt, for eksempel "7/3" eller noe utydelig:
  - velg én verdi bare hvis du er rimelig sikker
  - velg helst en verdi som ikke skaper duplikat
  - hvis du ikke er sikker, returner null for stroke_index
- Det er BEDRE å returnere null enn å duplisere en index.
- Du må aldri bevisst returnere samme stroke_index to ganger hvis det kan unngås.

KRITISK FOR PAR:
- Returner par som heltall når du er rimelig sikker.
- Hvis du ikke klarer å lese par sikkert, returner null.

KRITISK FOR TEES OG LENGDER:
- Returner mellom 1 og 5 tees.
- Hver tee må ha navn og nøyaktig én lengde per hull.
- Hver lengde skal kun være for enkelt-hull, ikke summer.
- IGNORER alltid totalsummer og summeringsfelt som:
  - OUT
  - IN
  - TOT
  - TOTAL
  - SUM
  - front 9 sum
  - back 9 sum
  - total yardage/meters
- En hullengde skal normalt være mellom 50 og 650 meter.
- Hvis en verdi er under 50 eller over 650:
  - tolk den som ugyldig
  - ikke bruk den som hullengde
  - returner null hvis du ikke finner en bedre verdi
- Hvis en tee-rad inneholder både hullengder og summer:
  - ta bare med selve hullengdene
  - ikke ta med OUT/IN/TOTAL som del av lengths-listen
- Tee-navn skal være korte og slik de står på kortet, for eksempel:
  - "58"
  - "56"
  - "52"
  - "46"
  - "Hvit"
  - "Gul"
  - "Rød"
  - "B/W"
  - "Gold"
  - "Blue"
  - "Black"

RETURNER DETTE FORMATET:

{{
  "prompt_version": "{PROMPT_VERSION_SCORECARD}",
  "course_name": "",
  "hole_count": 18,
  "holes": [
    {{
      "hole_number": 1,
      "par": 4,
      "stroke_index": 17
    }}
  ],
  "tees": [
    {{
      "name": "Hvit",
      "lengths": [275, 412, 297]
    }}
  ]
}}

REGLER:
- prompt_version må være "{PROMPT_VERSION_SCORECARD}"
- hole_count må være 9 eller 18
- holes må være sortert stigende fra 1 til hole_count
- Hvis du er usikker på et enkeltfelt, returner null for det feltet
- Ikke returner forklaringstekst
- Returner kun JSON
"""

    response = client.responses.create(
        model="gpt-4.1",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{image}"
                }
            ]
        }]
    )

    text = response.output_text
    print("\n=== AI RAW RESPONSE SCORECARD ===")
    print(text)
    print("=================================\n")

    data = extract_json_from_text(text)

    hole_count = _normalize_int(data.get("hole_count"), default=0)
    if hole_count not in (9, 18):
        raise ValueError(f"Ugyldig hole_count fra AI: {hole_count}")

    raw_holes = data.get("holes", [])
    if not isinstance(raw_holes, list) or len(raw_holes) != hole_count:
        raise ValueError("AI returnerte feil antall hull.")

    normalized_holes = []
    used_indexes = set()

    for expected_hole_number, hole in enumerate(raw_holes, start=1):
        hole_number = _normalize_int(hole.get("hole_number"), default=expected_hole_number)
        par = _normalize_int(hole.get("par"), default="")
        stroke_index = _normalize_int(hole.get("stroke_index"), default="")

        if hole_number != expected_hole_number:
            raise ValueError("Hullene fra AI er ikke komplette og sortert riktig.")

        if par != "" and not (3 <= par <= 6):
            par = ""

        if stroke_index != "":
            if not (1 <= stroke_index <= hole_count):
                stroke_index = ""
            elif stroke_index in used_indexes:
                stroke_index = ""
            else:
                used_indexes.add(stroke_index)

        normalized_holes.append(
            {
                "hole_number": hole_number,
                "par": par,
                "stroke_index": stroke_index,
            }
        )

    raw_tees = data.get("tees", [])
    if not isinstance(raw_tees, list) or not (1 <= len(raw_tees) <= 5):
        raise ValueError("AI returnerte ugyldig antall tees.")

    normalized_tees = []
    used_tee_names = set()

    for idx, tee in enumerate(raw_tees, start=1):
        tee_name = str(tee.get("name", "")).strip() or f"Tee {idx}"
        tee_name_key = tee_name.lower()

        if tee_name_key in used_tee_names:
            tee_name = f"{tee_name} {idx}"
            tee_name_key = tee_name.lower()

        used_tee_names.add(tee_name_key)

        raw_lengths = tee.get("lengths", [])
        if not isinstance(raw_lengths, list):
            raise ValueError(f"Tee '{tee_name}' mangler lengths-liste.")

        normalized_lengths = {}
        trimmed_lengths = list(raw_lengths[:hole_count])

        while len(trimmed_lengths) < hole_count:
            trimmed_lengths.append(None)

        for hole_number, raw_length in enumerate(trimmed_lengths, start=1):
            length_value = _normalize_int(raw_length, default="")
            if length_value != "" and not (50 <= length_value <= 650):
                length_value = ""
            normalized_lengths[hole_number] = length_value

        normalized_tees.append(
            {
                "index": idx,
                "name": tee_name,
                "lengths": normalized_lengths,
                "ratings": {
                    "male": {"slope": "", "course_rating": ""},
                    "female": {"slope": "", "course_rating": ""},
                },
            }
        )

    return {
        "prompt_version": data.get("prompt_version"),
        "course_name": str(data.get("course_name", "")).strip() or "Ukjent bane",
        "hole_count": hole_count,
        "holes": normalized_holes,
        "tees": normalized_tees,
    }


def analyze_slope_table_with_openai(image_path: str):
    client = OpenAI(api_key=OPENAI_API_KEY)

    with open(image_path, "rb") as f:
        image = base64.b64encode(f.read()).decode()

    prompt = f"""
PROMPT_VERSION: {PROMPT_VERSION_SLOPE}

Du får et bilde av en slopetabell eller en del av et golfkort som kan inneholde:
- tee-navn
- slope
- course rating
- verdier for herre og dame

Oppgave:
Finn så mye du klarer, men returner KUN JSON.
Hvis du er usikker, returner tomme felt.
Feil eller manglende slope-data må aldri stoppe prosessen.

RETURNER KUN DETTE FORMATET:

{{
  "prompt_version": "{PROMPT_VERSION_SLOPE}",
  "ratings": [
    {{
      "tee_name": "Blue",
      "male_slope": 133,
      "male_course_rating": 71.1,
      "female_slope": 130,
      "female_course_rating": 69.7
    }}
  ]
}}

REGLER:
- ratings kan være tom liste hvis du er usikker
- tee_name skal være kort og matche navnet som står på kortet best mulig
- slope skal være heltall
- course_rating skal være tall med eller uten desimal
- bruk null hvis enkeltfelt er usikre
- ikke returner forklaring
- returner kun JSON
"""

    response = client.responses.create(
        model="gpt-4.1",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{image}"
                }
            ]
        }]
    )

    text = response.output_text
    print("\n=== AI RAW RESPONSE SLOPE ===")
    print(text)
    print("=============================\n")

    data = extract_json_from_text(text)

    normalized = []
    for item in data.get("ratings", []):
        tee_name = str(item.get("tee_name", "")).strip()
        if not tee_name:
            continue

        male_slope = _normalize_int(item.get("male_slope"), default="")
        male_course_rating = _normalize_float(item.get("male_course_rating"), default="")
        female_slope = _normalize_int(item.get("female_slope"), default="")
        female_course_rating = _normalize_float(item.get("female_course_rating"), default="")

        if male_slope != "" and not (55 <= male_slope <= 155):
            male_slope = ""
        if female_slope != "" and not (55 <= female_slope <= 155):
            female_slope = ""
        if male_course_rating != "" and not (40.0 <= male_course_rating <= 80.0):
            male_course_rating = ""
        if female_course_rating != "" and not (40.0 <= female_course_rating <= 80.0):
            female_course_rating = ""

        normalized.append(
            {
                "tee_name": tee_name,
                "male_slope": male_slope,
                "male_course_rating": male_course_rating,
                "female_slope": female_slope,
                "female_course_rating": female_course_rating,
            }
        )

    return {
        "prompt_version": data.get("prompt_version"),
        "ratings": normalized,
    }
