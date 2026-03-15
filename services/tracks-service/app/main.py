import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
from pythonjsonlogger import jsonlogger
from sqlalchemy import create_engine, text

SERVICE_NAME = "tracks-service"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@postgres:5432/soundcloud")
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")
STARTUP_STRICT = os.getenv("STARTUP_STRICT", "0") == "1"
VALID_VISIBILITY = {"public", "private", "unlisted"}
VALID_STATUS = {"processing", "published", "failed"}


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
app = FastAPI(title="Tracks Service", version="1.0.0")


class TrackCreate(BaseModel):
    owner_id: str
    title: str = Field(min_length=1, max_length=180)
    artist: str = Field(min_length=1, max_length=120)
    raw_object_key: str
    visibility: str = "private"
    description: str | None = Field(default=None, max_length=1000)
    genre: str | None = Field(default=None, max_length=64)


class TrackUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    artist: str | None = Field(default=None, min_length=1, max_length=120)
    visibility: str | None = Field(default=None)
    description: str | None = Field(default=None, max_length=1000)
    genre: str | None = Field(default=None, max_length=64)


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
                    description TEXT,
                    genre TEXT,
                    plays_count INTEGER NOT NULL DEFAULT 0,
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
        conn.execute(text("ALTER TABLE tracks ADD COLUMN IF NOT EXISTS description TEXT"))
        conn.execute(text("ALTER TABLE tracks ADD COLUMN IF NOT EXISTS genre TEXT"))
        conn.execute(text("ALTER TABLE tracks ADD COLUMN IF NOT EXISTS plays_count INTEGER NOT NULL DEFAULT 0"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tracks_owner ON tracks (owner_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks (status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tracks_visibility ON tracks (visibility)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tracks_created ON tracks (created_at DESC)"))


def require_internal_token(x_internal_token: str | None) -> None:
    if not INTERNAL_API_TOKEN:
        return
    if x_internal_token != INTERNAL_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid internal token")


def require_user(x_user_id: str | None) -> str:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing x-user-id")
    return x_user_id


def normalize_visibility(visibility: str) -> str:
    normalized = visibility.strip().lower()
    if normalized not in VALID_VISIBILITY:
        raise HTTPException(status_code=400, detail="Invalid visibility")
    return normalized


def validate_status(status: str) -> None:
    if status not in VALID_STATUS:
        raise HTTPException(status_code=400, detail="Invalid status filter")


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def can_view_track(row, requester_id: str | None) -> bool:
    if requester_id and row.owner_id == requester_id:
        return True
    if row.visibility == "private":
        return False
    return row.status == "published"


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
        "description": row.description,
        "genre": row.genre,
        "plays_count": row.plays_count,
        "duration_seconds": row.duration_seconds,
        "loudness_lufs": row.loudness_lufs,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
    }


@app.on_event("startup")
def on_startup() -> None:
    try:
        create_tables()
    except Exception as exc:  # pragma: no cover
        logger.exception("startup_partial_failure", extra={"service": SERVICE_NAME, "error": str(exc)})
        if STARTUP_STRICT:
            raise
    logger.info("startup_complete", extra={"service": SERVICE_NAME})


@app.get("/healthz")
def healthz() -> dict[str, str]:
    logger.info("healthcheck", extra={"service": SERVICE_NAME})
    return {"status": "ok", "service": SERVICE_NAME, "ts": datetime.now(UTC).isoformat()}


@app.post("/tracks")
def create_track(payload: TrackCreate) -> dict[str, str | int | float | None]:
    visibility = normalize_visibility(payload.visibility)
    title = payload.title.strip()
    artist = payload.artist.strip()
    if not title or not artist:
        raise HTTPException(status_code=400, detail="Title and artist cannot be blank")

    track_id = str(uuid4())
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO tracks (id, owner_id, title, artist, visibility, status, raw_object_key, description, genre)
                VALUES (:id, :owner_id, :title, :artist, :visibility, 'processing', :raw_object_key, :description, :genre)
                RETURNING *
                """
            ),
            {
                "id": track_id,
                "owner_id": payload.owner_id,
                "title": title,
                "artist": artist,
                "visibility": visibility,
                "raw_object_key": payload.raw_object_key,
                "description": normalize_optional_text(payload.description),
                "genre": normalize_optional_text(payload.genre),
            },
        ).one()

    return serialize_track(row)


@app.get("/tracks")
def list_tracks(
    owner_id: str | None = Query(default=None),
    visibility: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    sort: str = Query(default="recent"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    x_user_id: str | None = Header(default=None),
) -> dict[str, list[dict[str, str | int | float | None]] | int]:
    normalized_visibility = normalize_visibility(visibility) if visibility else None
    if status:
        validate_status(status)
    if sort not in {"recent", "popular"}:
        raise HTTPException(status_code=400, detail="Invalid sort; use recent or popular")

    requester_id = x_user_id
    is_owner_request = owner_id is not None and owner_id == requester_id
    where_clauses = ["1=1"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if owner_id:
        where_clauses.append("owner_id = :owner_id")
        params["owner_id"] = owner_id

    search_query = q.strip() if q else ""
    if search_query:
        where_clauses.append("(title ILIKE :q OR artist ILIKE :q OR COALESCE(description, '') ILIKE :q OR COALESCE(genre, '') ILIKE :q)")
        params["q"] = f"%{search_query}%"

    if is_owner_request:
        if normalized_visibility:
            where_clauses.append("visibility = :visibility")
            params["visibility"] = normalized_visibility
        if status:
            where_clauses.append("status = :status")
            params["status"] = status
    else:
        if normalized_visibility and normalized_visibility != "public":
            raise HTTPException(status_code=400, detail="Only public visibility is allowed for this query")
        if status and status != "published":
            raise HTTPException(status_code=400, detail="Only published status is allowed for this query")
        where_clauses.append("visibility = 'public'")
        where_clauses.append("status = 'published'")

    where_sql = " AND ".join(where_clauses)
    order_sql = "plays_count DESC, published_at DESC NULLS LAST, created_at DESC" if sort == "popular" else "created_at DESC"

    items_sql = f"SELECT * FROM tracks WHERE {where_sql} ORDER BY {order_sql} LIMIT :limit OFFSET :offset"
    count_sql = f"SELECT COUNT(*) FROM tracks WHERE {where_sql}"

    count_params = dict(params)
    count_params.pop("limit", None)
    count_params.pop("offset", None)

    with engine.begin() as conn:
        rows = conn.execute(text(items_sql), params).all()
        total = conn.execute(text(count_sql), count_params).scalar_one()

    return {"items": [serialize_track(row) for row in rows], "total": int(total)}


@app.get("/tracks/{track_id}")
def get_track(track_id: str, x_user_id: str | None = Header(default=None)) -> dict[str, str | int | float | None]:
    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM tracks WHERE id = :id"), {"id": track_id}).first()

    if row is None:
        raise HTTPException(status_code=404, detail="Track not found")
    if not can_view_track(row, x_user_id):
        raise HTTPException(status_code=404, detail="Track not found")

    return serialize_track(row)


@app.patch("/tracks/{track_id}")
def update_track(
    track_id: str,
    payload: TrackUpdate,
    x_user_id: str | None = Header(default=None),
) -> dict[str, str | int | float | None]:
    user_id = require_user(x_user_id)

    with engine.begin() as conn:
        current = conn.execute(
            text("SELECT * FROM tracks WHERE id = :id AND owner_id = :owner_id"),
            {"id": track_id, "owner_id": user_id},
        ).first()
        if current is None:
            raise HTTPException(status_code=404, detail="Track not found or no access")

        updates: dict[str, Any] = {}
        if payload.title is not None:
            title = payload.title.strip()
            if not title:
                raise HTTPException(status_code=400, detail="Title cannot be blank")
            updates["title"] = title
        if payload.artist is not None:
            artist = payload.artist.strip()
            if not artist:
                raise HTTPException(status_code=400, detail="Artist cannot be blank")
            updates["artist"] = artist
        if payload.description is not None:
            updates["description"] = normalize_optional_text(payload.description)
        if payload.genre is not None:
            updates["genre"] = normalize_optional_text(payload.genre)
        if payload.visibility is not None:
            updates["visibility"] = normalize_visibility(payload.visibility)

        if not updates:
            return serialize_track(current)

        params: dict[str, Any] = {"id": track_id, "owner_id": user_id}
        setters: list[str] = []
        for key, value in updates.items():
            setters.append(f"{key} = :{key}")
            params[key] = value

        row = conn.execute(
            text(
                f"""
                UPDATE tracks
                SET {', '.join(setters)}, updated_at = NOW()
                WHERE id = :id AND owner_id = :owner_id
                RETURNING *
                """
            ),
            params,
        ).first()

    return serialize_track(row)


@app.delete("/tracks/{track_id}")
def delete_track(track_id: str, x_user_id: str | None = Header(default=None)) -> dict[str, str]:
    user_id = require_user(x_user_id)
    with engine.begin() as conn:
        row = conn.execute(
            text("DELETE FROM tracks WHERE id = :id AND owner_id = :owner_id RETURNING id"),
            {"id": track_id, "owner_id": user_id},
        ).first()

    if row is None:
        raise HTTPException(status_code=404, detail="Track not found or no access")

    return {"status": "deleted", "track_id": str(row.id)}


@app.post("/tracks/{track_id}/play")
def register_play(track_id: str, x_user_id: str | None = Header(default=None)) -> dict[str, int]:
    with engine.begin() as conn:
        current = conn.execute(
            text("SELECT owner_id, visibility, status FROM tracks WHERE id = :id"),
            {"id": track_id},
        ).first()
        if current is None:
            raise HTTPException(status_code=404, detail="Track not found")

        if current.status != "published":
            raise HTTPException(status_code=409, detail="Track is not published")
        if current.visibility == "private" and current.owner_id != x_user_id:
            raise HTTPException(status_code=404, detail="Track not found")

        row = conn.execute(
            text(
                """
                UPDATE tracks
                SET plays_count = plays_count + 1,
                    updated_at = NOW()
                WHERE id = :id
                RETURNING plays_count
                """
            ),
            {"id": track_id},
        ).first()

    return {"plays_count": int(row.plays_count)}


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
