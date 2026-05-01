import os
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func
from werkzeug.utils import secure_filename

from extensions import db
from models import Course, CourseHole, CourseTee, CourseTeeLength, CourseTeeRating, Round
from services.course_forms import (
    holes_data_for_course,
    merge_imported_ratings_into_tees,
    render_edit_course_form_from_request,
    render_new_course_form,
    render_new_course_form_from_request,
    tees_data_for_course,
    validate_holes_data,
    validate_tees_data,
)
from services.course_importer import (
    allowed_file,
    analyze_scorecard_with_openai,
    analyze_slope_table_with_openai,
)

courses_bp = Blueprint("courses", __name__)


@courses_bp.route("/courses")
def courses():
    all_courses = Course.query.order_by(Course.name.asc()).all()
    return render_template("courses.html", courses=all_courses)


@courses_bp.route("/courses/import", methods=["GET", "POST"])
def import_course():
    if request.method == "POST":
        if "scorecard_image" not in request.files:
            flash("Du må velge et bilde av scorekortet.", "error")
            return render_template("course_import.html")

        scorecard_file = request.files["scorecard_image"]
        slope_file = request.files.get("slope_table_image")

        if not scorecard_file or scorecard_file.filename == "":
            flash("Du må velge et bilde av scorekortet.", "error")
            return render_template("course_import.html")

        if not allowed_file(scorecard_file.filename):
            flash("Kun jpg, jpeg, png og webp er støttet for scorekort.", "error")
            return render_template("course_import.html")

        if slope_file and slope_file.filename and not allowed_file(slope_file.filename):
            flash("Kun jpg, jpeg, png og webp er støttet for slopetabell.", "error")
            return render_template("course_import.html")

        os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        scorecard_path = os.path.join(
            current_app.config["UPLOAD_FOLDER"],
            f"{timestamp}_score_{secure_filename(scorecard_file.filename)}",
        )
        scorecard_file.save(scorecard_path)

        try:
            score_data = analyze_scorecard_with_openai(scorecard_path)
        except Exception as e:
            flash(f"Import feilet: {str(e)}", "error")
            return render_template("course_import.html")

        tees_data = score_data["tees"]

        slope_imported = False
        if slope_file and slope_file.filename:
            slope_path = os.path.join(
                current_app.config["UPLOAD_FOLDER"],
                f"{timestamp}_slope_{secure_filename(slope_file.filename)}",
            )
            slope_file.save(slope_path)

            try:
                slope_data = analyze_slope_table_with_openai(slope_path)
                tees_data = merge_imported_ratings_into_tees(tees_data, slope_data.get("ratings", []))
                slope_imported = True
                flash("Scorekort analysert. Slopedata lest og forhåndsutfylt.", "success")
            except Exception:
                flash("Scorekort analysert. Slopedata kunne ikke tolkes - bruker dummy-verdier.", "warning")
        else:
            flash("Scorekort analysert. Bruker dummy-verdier for slope og course rating.", "warning")

        # Set dummy values if no slope data was imported
        if not slope_imported:
            for tee in tees_data:
                tee["ratings"]["male"]["slope"] = "113"
                tee["ratings"]["male"]["course_rating"] = "70.0"
                tee["ratings"]["female"]["slope"] = "120"
                tee["ratings"]["female"]["course_rating"] = "72.0"

        return render_template(
            "course_form.html",
            course=None,
            hole_count=score_data["hole_count"],
            tee_count=len(tees_data),
            holes_data=score_data["holes"],
            tees_data=tees_data,
            imported_course_name=score_data["course_name"],
            slope_imported=slope_imported,
        )

    return render_template("course_import.html")


@courses_bp.route("/courses/new", methods=["GET", "POST"])
def new_course():
    if request.method == "POST":
        form_action = request.form.get("form_action", "save").strip()
        name = request.form.get("name", "").strip()
        hole_count_raw = request.form.get("hole_count", "18").strip()
        tee_count_raw = request.form.get("tee_count", "1").strip()

        try:
            hole_count = int(hole_count_raw)
        except ValueError:
            hole_count = 18

        try:
            tee_count = int(tee_count_raw)
        except ValueError:
            tee_count = 1

        if hole_count not in (9, 18):
            hole_count = 18

        if tee_count < 1 or tee_count > 6:
            tee_count = 1

        if form_action == "refresh_layout":
            return render_new_course_form_from_request(
                hole_count=hole_count,
                tee_count=tee_count,
                imported_course_name=name or None,
            )

        if not name:
            flash("Banenavn må fylles ut.", "error")
            return render_new_course_form_from_request(hole_count, tee_count)

        duplicate = Course.query.filter(func.lower(Course.name) == name.lower()).first()
        if duplicate:
            flash("Det finnes allerede en bane med dette navnet.", "error")
            return render_new_course_form_from_request(hole_count, tee_count)

        try:
            holes = validate_holes_data(hole_count)
            tees = validate_tees_data(hole_count, tee_count)
        except ValueError as e:
            flash(str(e), "error")
            return render_new_course_form_from_request(hole_count, tee_count)

        course = Course(name=name, hole_count=hole_count)
        db.session.add(course)
        db.session.flush()

        hole_map = {}
        for hole_data in holes:
            hole = CourseHole(
                course_id=course.id,
                hole_number=hole_data["hole_number"],
                par=hole_data["par"],
                stroke_index=hole_data["stroke_index"],
            )
            db.session.add(hole)
            db.session.flush()
            hole_map[hole.hole_number] = hole

        for tee_data in tees:
            tee = CourseTee(
                course_id=course.id,
                name=tee_data["name"],
                display_order=tee_data["index"],
            )
            db.session.add(tee)
            db.session.flush()

            for hole_number, length_meters in tee_data["lengths"].items():
                db.session.add(
                    CourseTeeLength(
                        tee_id=tee.id,
                        hole_id=hole_map[hole_number].id,
                        hole_number=hole_number,
                        length_meters=length_meters,
                    )
                )

            db.session.add(
                CourseTeeRating(
                    tee_id=tee.id,
                    gender="male",
                    slope=tee_data["ratings"]["male"]["slope"],
                    course_rating=tee_data["ratings"]["male"]["course_rating"],
                )
            )
            db.session.add(
                CourseTeeRating(
                    tee_id=tee.id,
                    gender="female",
                    slope=tee_data["ratings"]["female"]["slope"],
                    course_rating=tee_data["ratings"]["female"]["course_rating"],
                )
            )

        db.session.commit()
        flash("Bane opprettet.", "success")
        return redirect(url_for("courses.courses"))

    return render_new_course_form(hole_count=18, tee_count=1)


@courses_bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)

    if request.method == "POST":
        form_action = request.form.get("form_action", "save").strip()
        name = request.form.get("name", "").strip()
        tee_count_raw = request.form.get("tee_count", "1").strip()

        try:
            tee_count = int(tee_count_raw)
        except ValueError:
            tee_count = max(1, len(course.tees))

        if tee_count < 1 or tee_count > 6:
            tee_count = max(1, len(course.tees))

        if form_action == "refresh_layout":
            return render_edit_course_form_from_request(course, tee_count)

        if not name:
            flash("Banenavn må fylles ut.", "error")
            return render_edit_course_form_from_request(course, tee_count)

        duplicate = Course.query.filter(
            func.lower(Course.name) == name.lower(),
            Course.id != course.id,
        ).first()
        if duplicate:
            flash("Det finnes allerede en annen bane med dette navnet.", "error")
            return render_edit_course_form_from_request(course, tee_count)

        try:
            holes = validate_holes_data(course.hole_count)
            tees = validate_tees_data(course.hole_count, tee_count)
        except ValueError as e:
            flash(str(e), "error")
            return render_edit_course_form_from_request(course, tee_count)

        course.name = name

        existing_holes = {hole.hole_number: hole for hole in course.holes}
        for hole_data in holes:
            existing_holes[hole_data["hole_number"]].par = hole_data["par"]
            existing_holes[hole_data["hole_number"]].stroke_index = hole_data["stroke_index"]

        for tee in list(course.tees):
            db.session.delete(tee)
        db.session.flush()

        for tee_data in tees:
            tee = CourseTee(
                course_id=course.id,
                name=tee_data["name"],
                display_order=tee_data["index"],
            )
            db.session.add(tee)
            db.session.flush()

            for hole_number, length_meters in tee_data["lengths"].items():
                db.session.add(
                    CourseTeeLength(
                        tee_id=tee.id,
                        hole_id=existing_holes[hole_number].id,
                        hole_number=hole_number,
                        length_meters=length_meters,
                    )
                )

            db.session.add(
                CourseTeeRating(
                    tee_id=tee.id,
                    gender="male",
                    slope=tee_data["ratings"]["male"]["slope"],
                    course_rating=tee_data["ratings"]["male"]["course_rating"],
                )
            )
            db.session.add(
                CourseTeeRating(
                    tee_id=tee.id,
                    gender="female",
                    slope=tee_data["ratings"]["female"]["slope"],
                    course_rating=tee_data["ratings"]["female"]["course_rating"],
                )
            )

        db.session.commit()
        flash("Bane oppdatert.", "success")
        return redirect(url_for("courses.courses"))

    existing_tees = tees_data_for_course(course)
    tee_count = max(1, len(existing_tees))

    return render_template(
        "course_form.html",
        course=course,
        hole_count=course.hole_count,
        tee_count=tee_count,
        holes_data=holes_data_for_course(course),
        tees_data=existing_tees,
    )


@courses_bp.route("/courses/<int:course_id>/delete", methods=["POST"])
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)

    is_in_use = Round.query.filter_by(course_id=course.id).first() is not None
    if is_in_use:
        flash("Kan ikke slette bane som allerede er brukt i en eller flere runder.", "error")
        return redirect(url_for("courses.courses"))

    db.session.delete(course)
    db.session.commit()
    flash("Bane slettet.", "success")
    return redirect(url_for("courses.courses"))
