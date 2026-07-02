from flask import Flask, jsonify, render_template, request

from balletour_survey.database import (
    create_database_engine,
    delete_feature,
    init_database,
    list_features,
    save_feature,
)


ALLOWED_FEATURE_TYPES = {
    "tee",
    "basket",
    "green",
    "fairway",
    "ob",
    "path",
    "hazard",
    "sign",
    "other",
}
ALLOWED_GEOMETRY_TYPES = {"Point", "LineString", "Polygon"}


def create_app(database_url=None):
    app = Flask(__name__)
    engine = create_database_engine(database_url)
    init_database(engine)
    app.config["SURVEY_ENGINE"] = engine

    @app.after_request
    def allow_survey_geolocation(response):
        response.headers["Permissions-Policy"] = "geolocation=(self)"
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/features")
    def api_features():
        return jsonify({"features": list_features(engine)})

    @app.get("/api/export.geojson")
    def api_export_geojson():
        return jsonify({
            "type": "FeatureCollection",
            "features": list_features(engine),
        })

    @app.post("/api/features")
    def api_create_feature():
        payload = request.get_json(silent=True) or {}
        error = validate_feature_payload(payload)
        if error:
            return jsonify({"error": error}), 400
        feature = save_feature(engine, payload)
        return jsonify({"feature": feature}), 201

    @app.delete("/api/features/<int:feature_id>")
    def api_delete_feature(feature_id):
        if not delete_feature(engine, feature_id):
            return jsonify({"error": "Fant ikke punktet."}), 404
        return jsonify({"deleted": True})

    return app


def validate_feature_payload(payload):
    name = (payload.get("name") or "").strip()
    feature_type = (payload.get("feature_type") or "").strip()
    geometry = payload.get("geometry")

    if not name:
        return "Navn mangler."
    if feature_type not in ALLOWED_FEATURE_TYPES:
        return "Ukjent type."
    if not isinstance(geometry, dict) or geometry.get("type") not in ALLOWED_GEOMETRY_TYPES:
        return "Ugyldig geometri."
    if not _valid_coordinates(geometry.get("type"), geometry.get("coordinates")):
        return "Ugyldige koordinater."

    hole_number = payload.get("hole_number")
    if hole_number not in (None, ""):
        try:
            hole_number = int(hole_number)
        except (TypeError, ValueError):
            return "Hullnummer må være et tall."
        if hole_number < 1 or hole_number > 18:
            return "Hullnummer må være mellom 1 og 18."
        payload["hole_number"] = hole_number
    else:
        payload["hole_number"] = None

    accuracy = payload.get("accuracy_m")
    if accuracy not in (None, ""):
        try:
            payload["accuracy_m"] = round(float(accuracy), 2)
        except (TypeError, ValueError):
            return "GPS-nøyaktighet må være et tall."
    else:
        payload["accuracy_m"] = None

    payload["name"] = name[:160]
    payload["feature_type"] = feature_type
    payload["notes"] = (payload.get("notes") or "").strip()[:1000]
    return None


def _valid_position(value):
    if not isinstance(value, list) or len(value) < 2:
        return False
    lon, lat = value[0], value[1]
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        return False
    return -180 <= lon <= 180 and -90 <= lat <= 90


def _valid_coordinates(geometry_type, coordinates):
    if geometry_type == "Point":
        return _valid_position(coordinates)
    if geometry_type == "LineString":
        return isinstance(coordinates, list) and len(coordinates) >= 2 and all(
            _valid_position(position) for position in coordinates
        )
    if geometry_type == "Polygon":
        if not isinstance(coordinates, list) or not coordinates:
            return False
        ring = coordinates[0]
        return isinstance(ring, list) and len(ring) >= 4 and all(
            _valid_position(position) for position in ring
        )
    return False


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5060, debug=False)
