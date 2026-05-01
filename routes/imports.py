import os
from flask import Blueprint, render_template, request, flash
from werkzeug.utils import secure_filename

from services.ai_import import analyze_scorecard

imports_bp = Blueprint("imports", __name__)

UPLOAD_FOLDER = "uploads"


@imports_bp.route("/courses/import", methods=["GET", "POST"])
def import_course():
    if request.method == "POST":
        file = request.files.get("scorecard_image")

        if not file:
            flash("Velg bilde", "error")
            return render_template("course_import.html")

        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        path = os.path.join(UPLOAD_FOLDER, secure_filename(file.filename))
        file.save(path)

        try:
            data = analyze_scorecard(path)
        except Exception as e:
            flash(str(e), "error")
            return render_template("course_import.html")

        return render_template(
            "course_form.html",
            hole_count=data["hole_count"],
            tees_data=data["tees"],
            holes_data=data["holes"],
            imported_course_name=data["course_name"]
        )

    return render_template("course_import.html")
