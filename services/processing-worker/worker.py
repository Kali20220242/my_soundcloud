import json
import logging
import os
import sys
import time
from typing import Any

import boto3
import httpx
from botocore.client import Config
from botocore.exceptions import ClientError
from pythonjsonlogger import jsonlogger
from redis import Redis

SERVICE_NAME = "processing-worker"
QUEUE_NAME = os.getenv("PROCESSING_QUEUE", "processing:jobs")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
POLL_DELAY_SECONDS = float(os.getenv("WORKER_POLL_DELAY", "2"))
MAX_JOB_RETRIES = int(os.getenv("MAX_JOB_RETRIES", "5"))

MINIO_BUCKET = os.getenv("MINIO_BUCKET", "tracks")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_REGION = os.getenv("MINIO_REGION", "us-east-1")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")

TRACKS_SERVICE_URL = os.getenv("TRACKS_SERVICE_URL", "http://tracks-service:8000")
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")



def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


configure_logging()
logger = logging.getLogger(SERVICE_NAME)


s3_client = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    region_name=MINIO_REGION,
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)



def update_track(track_id: str, endpoint: str, payload: dict[str, Any]) -> None:
    headers = {}
    if INTERNAL_API_TOKEN:
        headers["x-internal-token"] = INTERNAL_API_TOKEN

    with httpx.Client(timeout=8.0) as client:
        response = client.patch(f"{TRACKS_SERVICE_URL}/internal/tracks/{track_id}/{endpoint}", json=payload, headers=headers)

    if response.status_code >= 400:
        raise RuntimeError(f"tracks_service_{endpoint}_failed:{response.status_code}:{response.text}")



def object_exists(bucket: str, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise



def mark_failed(track_id: str, error_message: str) -> None:
    try:
        update_track(track_id=track_id, endpoint="fail", payload={"error_message": error_message[:400]})
    except Exception as exc:  # pragma: no cover
        logger.error("track_fail_update_failed", extra={"track_id": track_id, "error": str(exc)})



def process_job(redis_client: Redis, job: dict[str, Any]) -> None:
    track_id = job.get("track_id")
    object_key = job.get("object_key")
    bucket = job.get("bucket", MINIO_BUCKET)
    retries = int(job.get("retries", 0))

    if not track_id or not object_key:
        logger.warning("job_missing_fields", extra={"job": job})
        return

    if not object_exists(bucket, object_key):
        if retries < MAX_JOB_RETRIES:
            job["retries"] = retries + 1
            redis_client.lpush(QUEUE_NAME, json.dumps(job))
            logger.info("job_requeued_waiting_for_object", extra={"track_id": track_id, "retries": retries + 1})
            return

        mark_failed(track_id=track_id, error_message="Uploaded object not found in bucket")
        return

    processed_key = object_key.replace("raw/", "processed/", 1)
    s3_client.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": object_key},
        Key=processed_key,
        MetadataDirective="REPLACE",
        ContentType="audio/mpeg",
    )

    # FFmpeg pipeline can be wired here; now we publish when processed copy exists.
    update_track(
        track_id=track_id,
        endpoint="publish",
        payload={
            "processed_object_key": processed_key,
            "duration_seconds": None,
            "loudness_lufs": None,
        },
    )

    logger.info("job_completed", extra={"track_id": track_id, "processed_key": processed_key})



def main() -> None:
    redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
    logger.info("worker_started", extra={"queue": QUEUE_NAME})

    while True:
        item = redis_client.brpop(QUEUE_NAME, timeout=3)
        if not item:
            time.sleep(POLL_DELAY_SECONDS)
            continue

        _, payload = item
        try:
            job = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("invalid_job_payload", extra={"payload": payload})
            continue

        try:
            process_job(redis_client, job)
        except Exception as exc:  # pragma: no cover
            logger.exception("job_failed", extra={"job": job, "error": str(exc)})
            track_id = job.get("track_id")
            if track_id:
                mark_failed(track_id=track_id, error_message=str(exc))


if __name__ == "__main__":
    main()
