from flask import render_template, request


def default_holes_data(hole_count: int):
    return [
        {
            "hole_number": i,
            "par": 4,
            "stroke_index": i,
        }
        for i in range(1, hole_count + 1)
    ]


def holes_data_for_course(course):
    return [
        {
            "hole_number": hole.hole_number,
            "par": hole.par,
            "stroke_index": hole.stroke_index,
        }
        for hole in sorted(course.holes, key=lambda h: h.hole_number)
    ]


def holes_data_from_request(hole_count: int):
    rows = []
    for i in range(1, hole_count + 1):
        rows.append(
            {
                "hole_number": i,
                "par": request.form.get(f"par_{i}", "").strip() or "4",
                "stroke_index": request.form.get(f"index_{i}", "").strip() or str(i),
            }
        )
    return rows


def _empty_rating_block():
    return {
        "male": {"slope": "", "course_rating": ""},
        "female": {"slope": "", "course_rating": ""},
    }


def default_tees_data(hole_count: int, tee_count: int):
    tees = []
    for t in range(1, tee_count + 1):
        lengths = {}
        for hole in range(1, hole_count + 1):
            lengths[hole] = ""
        tees.append(
            {
                "index": t,
                "name": f"Tee {t}",
                "lengths": lengths,
                "ratings": _empty_rating_block(),
            }
        )
    return tees


def tees_data_from_request(hole_count: int, tee_count: int):
    tees = []
    for t in range(1, tee_count + 1):
        lengths = {}
        for hole in range(1, hole_count + 1):
            lengths[hole] = request.form.get(f"tee_{t}_length_{hole}", "").strip()

        tees.append(
            {
                "index": t,
                "name": request.form.get(f"tee_{t}_name", "").strip() or f"Tee {t}",
                "lengths": lengths,
                "ratings": {
                    "male": {
                        "slope": request.form.get(f"tee_{t}_male_slope", "").strip(),
                        "course_rating": request.form.get(f"tee_{t}_male_course_rating", "").strip(),
                    },
                    "female": {
                        "slope": request.form.get(f"tee_{t}_female_slope", "").strip(),
                        "course_rating": request.form.get(f"tee_{t}_female_course_rating", "").strip(),
                    },
                },
            }
        )
    return tees


def tees_data_for_course(course):
    tees = []
    for idx, tee in enumerate(sorted(course.tees, key=lambda t: t.display_order), start=1):
        lengths = {}
        for length in sorted(tee.lengths, key=lambda l: l.hole_number):
            lengths[length.hole_number] = length.length_meters
        for hole_number in range(1, course.hole_count + 1):
            lengths.setdefault(hole_number, "")

        ratings = _empty_rating_block()
        for rating in tee.ratings:
            ratings[rating.gender] = {
                "slope": rating.slope,
                "course_rating": rating.course_rating,
            }

        tees.append(
            {
                "index": idx,
                "name": tee.name,
                "lengths": lengths,
                "ratings": ratings,
            }
        )
    return tees


def merge_imported_ratings_into_tees(tees_data, imported_ratings):
    if not imported_ratings:
        return tees_data

    rating_map = {}
    for item in imported_ratings:
        tee_name = str(item.get("tee_name", "")).strip().lower()
        if tee_name:
            rating_map[tee_name] = item

    merged = []
    for tee in tees_data:
        key = str(tee["name"]).strip().lower()
        imported = rating_map.get(key)

        if imported:
            tee["ratings"]["male"]["slope"] = imported.get("male_slope", "") or ""
            tee["ratings"]["male"]["course_rating"] = imported.get("male_course_rating", "") or ""
            tee["ratings"]["female"]["slope"] = imported.get("female_slope", "") or ""
            tee["ratings"]["female"]["course_rating"] = imported.get("female_course_rating", "") or ""

        merged.append(tee)

    return merged


def _parse_float(value):
    return float(str(value).replace(",", ".").strip())


def validate_holes_data(hole_count: int):
    holes = []
    used_indexes = set()

    for i in range(1, hole_count + 1):
        par_raw = request.form.get(f"par_{i}", "").strip()
        index_raw = request.form.get(f"index_{i}", "").strip()

        try:
            par = int(par_raw)
            stroke_index = int(index_raw)
        except ValueError:
            raise ValueError(f"Par og index må være gyldige tall for hull {i}.")

        if par < 3 or par > 6:
            raise ValueError(f"Par må være mellom 3 og 6 for hull {i}.")

        if stroke_index < 1 or stroke_index > hole_count:
            raise ValueError(f"Index må være mellom 1 og {hole_count} for hull {i}.")

        if stroke_index in used_indexes:
            raise ValueError(f"Index {stroke_index} er brukt mer enn én gang.")

        used_indexes.add(stroke_index)
        holes.append(
            {
                "hole_number": i,
                "par": par,
                "stroke_index": stroke_index,
            }
        )

    return holes


def validate_tees_data(hole_count: int, tee_count: int):
    tees = []
    used_names = set()

    for t in range(1, tee_count + 1):
        tee_name = request.form.get(f"tee_{t}_name", "").strip()
        if not tee_name:
            raise ValueError(f"Navn mangler for tee {t}.")

        tee_name_key = tee_name.lower()
        if tee_name_key in used_names:
            raise ValueError(f"Tee-navnet '{tee_name}' er brukt mer enn én gang.")
        used_names.add(tee_name_key)

        lengths = {}
        for hole in range(1, hole_count + 1):
            raw_length = request.form.get(f"tee_{t}_length_{hole}", "").strip()
            if not raw_length:
                raise ValueError(f"Lengde mangler for tee '{tee_name}', hull {hole}.")

            try:
                length_meters = int(raw_length)
            except ValueError:
                raise ValueError(f"Lengde må være et heltall for tee '{tee_name}', hull {hole}.")

            if length_meters < 50 or length_meters > 650:
                raise ValueError(f"Lengde må være mellom 50 og 650 for tee '{tee_name}', hull {hole}.")

            lengths[hole] = length_meters

        try:
            male_slope = int(request.form.get(f"tee_{t}_male_slope", "").strip())
            male_course_rating = _parse_float(request.form.get(f"tee_{t}_male_course_rating", "").strip())
            female_slope = int(request.form.get(f"tee_{t}_female_slope", "").strip())
            female_course_rating = _parse_float(request.form.get(f"tee_{t}_female_course_rating", "").strip())
        except ValueError:
            raise ValueError(f"Slope og course rating må fylles ut korrekt for både herre og dame på tee '{tee_name}'.")

        if not (55 <= male_slope <= 155):
            raise ValueError(f"Herre slope må være mellom 55 og 155 på tee '{tee_name}'.")
        if not (55 <= female_slope <= 155):
            raise ValueError(f"Dame slope må være mellom 55 og 155 på tee '{tee_name}'.")
        if not (40.0 <= male_course_rating <= 80.0):
            raise ValueError(f"Herre course rating må være mellom 40.0 og 80.0 på tee '{tee_name}'.")
        if not (40.0 <= female_course_rating <= 80.0):
            raise ValueError(f"Dame course rating må være mellom 40.0 og 80.0 på tee '{tee_name}'.")

        tees.append(
            {
                "index": t,
                "name": tee_name,
                "lengths": lengths,
                "ratings": {
                    "male": {"slope": male_slope, "course_rating": male_course_rating},
                    "female": {"slope": female_slope, "course_rating": female_course_rating},
                },
            }
        )

    return tees


def render_new_course_form(hole_count=18, tee_count=1, imported_course_name=None):
    return render_template(
        "course_form.html",
        course=None,
        hole_count=hole_count,
        tee_count=tee_count,
        holes_data=default_holes_data(hole_count),
        tees_data=default_tees_data(hole_count, tee_count),
        imported_course_name=imported_course_name,
    )


def render_new_course_form_from_request(hole_count: int, tee_count: int, imported_course_name=None):
    return render_template(
        "course_form.html",
        course=None,
        hole_count=hole_count,
        tee_count=tee_count,
        holes_data=holes_data_from_request(hole_count),
        tees_data=tees_data_from_request(hole_count, tee_count),
        imported_course_name=imported_course_name,
    )


def render_edit_course_form_from_request(course, tee_count: int):
    return render_template(
        "course_form.html",
        course=course,
        hole_count=course.hole_count,
        tee_count=tee_count,
        holes_data=holes_data_from_request(course.hole_count),
        tees_data=tees_data_from_request(course.hole_count, tee_count),
    )
