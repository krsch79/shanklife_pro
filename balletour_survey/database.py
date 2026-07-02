import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
)
from sqlalchemy.engine import make_url


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = REPO_ROOT / "instance" / "shanklife_pro.db"
metadata = MetaData()


survey_features = Table(
    "balletour_survey_features",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(160), nullable=False),
    Column("feature_type", String(40), nullable=False),
    Column("hole_number", Integer, nullable=True),
    Column("geometry_type", String(30), nullable=False),
    Column("geometry_json", Text, nullable=False),
    Column("accuracy_m", Float, nullable=True),
    Column("notes", Text, nullable=True),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)


def database_url():
    configured = os.environ.get("DATABASE_URL", "").strip()
    if configured:
        return configured
    return f"sqlite:///{DEFAULT_DATABASE_PATH}"


def create_database_engine(url=None):
    resolved_url = url or database_url()
    parsed_url = make_url(resolved_url)
    if parsed_url.drivername.startswith("sqlite") and parsed_url.database:
        Path(parsed_url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)
    return create_engine(resolved_url, future=True)


def init_database(engine):
    metadata.create_all(engine, tables=[survey_features])


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _row_to_feature(row):
    geometry = json.loads(row.geometry_json)
    properties = {
        "id": row.id,
        "name": row.name,
        "feature_type": row.feature_type,
        "hole_number": row.hole_number,
        "accuracy_m": row.accuracy_m,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    return {
        "type": "Feature",
        "id": row.id,
        "geometry": geometry,
        "properties": properties,
    }


def list_features(engine):
    statement = select(survey_features).order_by(survey_features.c.created_at.desc())
    with engine.connect() as connection:
        rows = connection.execute(statement).all()
    return [_row_to_feature(row) for row in rows]


def save_feature(engine, payload):
    now = utc_now()
    geometry = payload["geometry"]
    values = {
        "name": payload["name"],
        "feature_type": payload["feature_type"],
        "hole_number": payload.get("hole_number"),
        "geometry_type": geometry["type"],
        "geometry_json": json.dumps(geometry, separators=(",", ":")),
        "accuracy_m": payload.get("accuracy_m"),
        "notes": payload.get("notes") or None,
        "created_at": now,
        "updated_at": now,
    }
    with engine.begin() as connection:
        result = connection.execute(survey_features.insert().values(**values))
        row = connection.execute(
            select(survey_features).where(survey_features.c.id == result.inserted_primary_key[0])
        ).one()
    return _row_to_feature(row)


def delete_feature(engine, feature_id):
    with engine.begin() as connection:
        result = connection.execute(
            survey_features.delete().where(survey_features.c.id == feature_id)
        )
    return result.rowcount > 0
