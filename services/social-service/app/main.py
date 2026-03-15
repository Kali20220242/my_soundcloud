import logging
import os
import sys
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from pythonjsonlogger import jsonlogger
from sqlalchemy import create_engine, text

SERVICE_NAME = "social-service"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@postgres:5432/soundcloud")
STARTUP_STRICT = os.getenv("STARTUP_STRICT", "0") == "1"


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
app = FastAPI(title="Social Service", version="0.2.0")


class LikePayload(BaseModel):
    track_id: str


class CommentPayload(BaseModel):
    track_id: str
    text: str = Field(min_length=1, max_length=1000)


class FollowPayload(BaseModel):
    target_user_id: str


def create_tables() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS likes (
                    track_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (track_id, user_id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS comments (
                    id UUID PRIMARY KEY,
                    track_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS follows (
                    follower_id TEXT NOT NULL,
                    target_user_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (follower_id, target_user_id)
                )
                """
            )
        )


def require_user(x_user_id: str | None) -> str:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing x-user-id")
    return x_user_id


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
    return {"status": "ok", "service": SERVICE_NAME, "ts": datetime.utcnow().isoformat()}


@app.post("/likes")
def like_track(payload: LikePayload, x_user_id: str | None = Header(default=None)) -> dict[str, int]:
    user_id = require_user(x_user_id)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO likes (track_id, user_id)
                VALUES (:track_id, :user_id)
                ON CONFLICT (track_id, user_id)
                DO NOTHING
                """
            ),
            {"track_id": payload.track_id, "user_id": user_id},
        )

        count = conn.execute(
            text("SELECT COUNT(*) AS cnt FROM likes WHERE track_id = :track_id"),
            {"track_id": payload.track_id},
        ).scalar_one()

    return {"track_likes": int(count)}


@app.delete("/likes/{track_id}")
def unlike_track(track_id: str, x_user_id: str | None = Header(default=None)) -> dict[str, int]:
    user_id = require_user(x_user_id)

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM likes WHERE track_id = :track_id AND user_id = :user_id"),
            {"track_id": track_id, "user_id": user_id},
        )
        count = conn.execute(
            text("SELECT COUNT(*) AS cnt FROM likes WHERE track_id = :track_id"),
            {"track_id": track_id},
        ).scalar_one()

    return {"track_likes": int(count)}


@app.get("/likes/{track_id}/count")
def likes_count(track_id: str) -> dict[str, int]:
    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) AS cnt FROM likes WHERE track_id = :track_id"),
            {"track_id": track_id},
        ).scalar_one()
    return {"track_likes": int(count)}


@app.post("/comments")
def add_comment(payload: CommentPayload, x_user_id: str | None = Header(default=None)) -> dict[str, str]:
    user_id = require_user(x_user_id)
    comment_id = str(uuid4())

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO comments (id, track_id, user_id, text)
                VALUES (:id, :track_id, :user_id, :text)
                """
            ),
            {"id": comment_id, "track_id": payload.track_id, "user_id": user_id, "text": payload.text},
        )

    return {"comment_id": comment_id}


@app.get("/comments/{track_id}")
def list_comments(track_id: str) -> dict[str, list[dict[str, str]]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, user_id, text, created_at
                FROM comments
                WHERE track_id = :track_id
                ORDER BY created_at DESC
                LIMIT 200
                """
            ),
            {"track_id": track_id},
        ).all()

    return {
        "items": [
            {
                "id": str(row.id),
                "user_id": row.user_id,
                "text": row.text,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@app.post("/follows")
def follow(payload: FollowPayload, x_user_id: str | None = Header(default=None)) -> dict[str, int]:
    follower_id = require_user(x_user_id)
    if follower_id == payload.target_user_id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO follows (follower_id, target_user_id)
                VALUES (:follower_id, :target_user_id)
                ON CONFLICT (follower_id, target_user_id)
                DO NOTHING
                """
            ),
            {"follower_id": follower_id, "target_user_id": payload.target_user_id},
        )
        count = conn.execute(
            text("SELECT COUNT(*) AS cnt FROM follows WHERE target_user_id = :target_user_id"),
            {"target_user_id": payload.target_user_id},
        ).scalar_one()

    return {"followers": int(count)}


@app.delete("/follows/{target_user_id}")
def unfollow(target_user_id: str, x_user_id: str | None = Header(default=None)) -> dict[str, int]:
    follower_id = require_user(x_user_id)

    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM follows WHERE follower_id = :follower_id AND target_user_id = :target_user_id"
            ),
            {"follower_id": follower_id, "target_user_id": target_user_id},
        )
        count = conn.execute(
            text("SELECT COUNT(*) AS cnt FROM follows WHERE target_user_id = :target_user_id"),
            {"target_user_id": target_user_id},
        ).scalar_one()

    return {"followers": int(count)}


@app.get("/profiles/{user_id}/stats")
def profile_stats(user_id: str) -> dict[str, int]:
    with engine.begin() as conn:
        followers = conn.execute(
            text("SELECT COUNT(*) FROM follows WHERE target_user_id = :user_id"),
            {"user_id": user_id},
        ).scalar_one()
        following = conn.execute(
            text("SELECT COUNT(*) FROM follows WHERE follower_id = :user_id"),
            {"user_id": user_id},
        ).scalar_one()

    return {"followers": int(followers), "following": int(following)}
