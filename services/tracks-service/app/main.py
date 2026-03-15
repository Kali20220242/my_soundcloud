import logging
import os
import sys
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
from pythonjsonlogger import jsonlogger
from sqlalchemy import create_engine, text

SERVICE_NAME = "tracks-service"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@postgres:5432/soundcloud")
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


configure_logging()
logger = logging.getLogger(SERVICE_NAME)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
app = FastAPI(title="Tracks Service", version="0.2.0")


class TrackCreate(BaseModel):
    owner_id: str
    title: str = Field(min_length=1, max_length=180)
    artist: str = Field(min_length=1, max_length=120)
    raw_object_key: str
    visibility: str = "private"


class TrackPublish(BaseModel):
    processed_object_key: str
    duration_seconds: int | None = None
    loudness_lufs: float | None = None


class TrackFail(BaseModel):
    error_message: str


def create_tables() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS tracks (
                    id UUID PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    visibility TEXT NOT NULL DEFAULT 'private',
                    status TEXT NOT NULL DEFAULT 'processing',
                    raw_object_key TEXT NOT NULL,
                    processed_object_key TEXT,
                    duration_seconds INTEGER,
                    loudness_lufs DOUBLE PRECISION,
                    error_message TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    published_at TIMESTAMPTZ
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tracks_owner ON tracks (owner_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks (status)"))


def require_internal_token(x_internal_token: str | None) -> None:
    if not INTERNAL_API_TOKEN:
        return
    if x_internal_token != INTERNAL_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid internal token")


def serialize_track(row) -> dict[str, str | int | float | None]:
    return {
        "id": str(row.id),
        "owner_id": row.owner_id,
        "title": row.title,
        "artist": row.artist,
        "visibility": row.visibility,
        "status": row.status,
        "raw_object_key": row.raw_object_key,
        "processed_object_key": row.processed_object_key,
        "duration_seconds": row.duration_seconds,
        "loudness_lufs": row.loudness_lufs,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
    }


@app.on_event("startup")
def on_startup() -> None:
    create_tables()
    logger.info("startup_complete", extra={"service": SERVICE_NAME})


@app.get("/healthz")
def healthz() -> dict[str, str]:
    logger.info("healthcheck", extra={"service": SERVICE_NAME})
    return {"status": "ok", "service": SERVICE_NAME, "ts": datetime.utcnow().isoformat()}


@app.post("/tracks")
def create_track(payload: TrackCreate) -> dict[str, str | int | float | None]:
    if payload.visibility not in {"public", "private", "unlisted"}:
        raise HTTPException(status_code=400, detail="Invalid visibility")

    track_id = str(uuid4())
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO tracks (id, owner_id, title, artist, visibility, status, raw_object_key)
                VALUES (:id, :owner_id, :title, :artist, :visibility, 'processing', :raw_object_key)
                RETURNING *
                """
            ),
            {
                "id": track_id,
                "owner_id": payload.owner_id,
                "title": payload.title,
                "artist": payload.artist,
                "visibility": payload.visibility,
                "raw_object_key": payload.raw_object_key,
            },
        ).one()

    return serialize_track(row)


@app.get("/tracks")
def list_tracks(
    owner_id: str | None = Query(default=None),
    visibility: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, list[dict[str, str | int | float | None]]]:
    query = "SELECT * FROM tracks WHERE 1=1"
    params: dict[str, str | int] = {"limit": limit, "offset": offset}

    if owner_id:
        query += " AND owner_id = :owner_id"
        params["owner_id"] = owner_id
    if visibility:
        query += " AND visibility = :visibility"
        params["visibility"] = visibility
    if status:
        query += " AND status = :status"
        params["status"] = status

    query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

    with engine.begin() as conn:
        rows = conn.execute(text(query), params).all()

    return {"items": [serialize_track(row) for row in rows]}


@app.get("/tracks/{track_id}")
def get_track(track_id: str) -> dict[str, str | int | float | None]:
    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM tracks WHERE id = :id"), {"id": track_id}).first()

    if row is None:
        raise HTTPException(status_code=404, detail="Track not found")

    return serialize_track(row)


@app.patch("/internal/tracks/{track_id}/publish")
def publish_track(
    track_id: str,
    payload: TrackPublish,
    x_internal_token: str | None = Header(default=None),
) -> dict[str, str | int | float | None]:
    require_internal_token(x_internal_token)

    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                UPDATE tracks
                SET status = 'published',
                    processed_object_key = :processed_object_key,
                    duration_seconds = :duration_seconds,
                    loudness_lufs = :loudness_lufs,
                    error_message = NULL,
                    published_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
                RETURNING *
                """
            ),
            {
                "id": track_id,
                "processed_object_key": payload.processed_object_key,
                "duration_seconds": payload.duration_seconds,
                "loudness_lufs": payload.loudness_lufs,
            },
        ).first()

    if row is None:
        raise HTTPException(status_code=404, detail="Track not found")

    return serialize_track(row)


@app.patch("/internal/tracks/{track_id}/fail")
def fail_track(
    track_id: str,
    payload: TrackFail,
    x_internal_token: str | None = Header(default=None),
) -> dict[str, str | int | float | None]:
    require_internal_token(x_internal_token)

    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                UPDATE tracks
                SET status = 'failed',
                    error_message = :error_message,
                    updated_at = NOW()
                WHERE id = :id
                RETURNING *
                """
            ),
            {"id": track_id, "error_message": payload.error_message},
        ).first()

    if row is None:
        raise HTTPException(status_code=404, detail="Track not found")

    return serialize_track(row)
