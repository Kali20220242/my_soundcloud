import json
import logging
import os
import re
import sys
from datetime import datetime
from uuid import uuid4

import boto3
import httpx
from botocore.client import Config
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from pythonjsonlogger import jsonlogger
from redis import Redis

SERVICE_NAME = "upload-service"
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_NAME = os.getenv("PROCESSING_QUEUE", "processing:jobs")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "tracks")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_REGION = os.getenv("MINIO_REGION", "us-east-1")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
PRESIGN_EXPIRES_SECONDS = int(os.getenv("PRESIGN_EXPIRES_SECONDS", "3600"))
TRACKS_SERVICE_URL = os.getenv("TRACKS_SERVICE_URL", "http://tracks-service:8000")


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
app = FastAPI(title="Upload Service", version="0.2.0")

s3_client = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    region_name=MINIO_REGION,
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)


class PresignRequest(BaseModel):
    filename: str
    content_type: str = "audio/mpeg"
    title: str = Field(min_length=1, max_length=180)
    artist: str = Field(min_length=1, max_length=120)
    visibility: str = "private"


class CompleteRequest(BaseModel):
    track_id: str
    object_key: str


def sanitize_filename(filename: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]", "-", filename.strip())
    return normalized[:180] or "track.bin"


def get_user_id(header_user_id: str | None) -> str:
    if not header_user_id:
        raise HTTPException(status_code=401, detail="Missing x-user-id header")
    return header_user_id


def create_track(owner_id: str, payload: PresignRequest, object_key: str) -> str:
    with httpx.Client(timeout=6.0) as client:
        response = client.post(
            f"{TRACKS_SERVICE_URL}/tracks",
            json={
                "owner_id": owner_id,
                "title": payload.title,
                "artist": payload.artist,
                "raw_object_key": object_key,
                "visibility": payload.visibility,
            },
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Tracks service unavailable")

    return response.json()["id"]


def enqueue_processing(track_id: str, owner_id: str, object_key: str) -> str:
    job_id = str(uuid4())
    redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.lpush(
        QUEUE_NAME,
        json.dumps(
            {
                "job_id": job_id,
                "track_id": track_id,
                "owner_id": owner_id,
                "object_key": object_key,
                "bucket": MINIO_BUCKET,
                "retries": 0,
            }
        ),
    )
    return job_id


@app.get("/healthz")
def healthz() -> dict[str, str]:
    logger.info("healthcheck", extra={"service": SERVICE_NAME})
    return {"status": "ok", "service": SERVICE_NAME, "ts": datetime.utcnow().isoformat()}


@app.post("/uploads/presign")
def create_presigned_upload(
    payload: PresignRequest,
    x_user_id: str | None = Header(default=None),
) -> dict[str, str | int]:
    owner_id = get_user_id(x_user_id)
    if payload.visibility not in {"public", "private", "unlisted"}:
        raise HTTPException(status_code=400, detail="Invalid visibility")

    safe_name = sanitize_filename(payload.filename)
    object_key = f"raw/{owner_id}/{uuid4()}-{safe_name}"

    track_id = create_track(owner_id=owner_id, payload=payload, object_key=object_key)

    upload_url = s3_client.generate_presigned_url(
        "put_object",
        Params={"Bucket": MINIO_BUCKET, "Key": object_key, "ContentType": payload.content_type},
        ExpiresIn=PRESIGN_EXPIRES_SECONDS,
    )

    return {
        "track_id": track_id,
        "object_key": object_key,
        "bucket": MINIO_BUCKET,
        "upload_url": upload_url,
        "expires_in_seconds": PRESIGN_EXPIRES_SECONDS,
    }


@app.post("/uploads/complete")
def mark_upload_complete(
    payload: CompleteRequest,
    x_user_id: str | None = Header(default=None),
) -> dict[str, str]:
    owner_id = get_user_id(x_user_id)

    with httpx.Client(timeout=6.0) as client:
        track_response = client.get(f"{TRACKS_SERVICE_URL}/tracks/{payload.track_id}")

    if track_response.status_code != 200:
        raise HTTPException(status_code=404, detail="Track not found")

    track = track_response.json()
    if track["owner_id"] != owner_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if track["raw_object_key"] != payload.object_key:
        raise HTTPException(status_code=400, detail="object_key mismatch")

    job_id = enqueue_processing(track_id=payload.track_id, owner_id=owner_id, object_key=payload.object_key)
    return {"status": "queued", "job_id": job_id}
