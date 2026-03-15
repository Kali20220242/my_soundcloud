import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pythonjsonlogger import jsonlogger
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

SERVICE_NAME = "api-gateway"
IDENTITY_SERVICE_URL = os.getenv("IDENTITY_SERVICE_URL", "http://identity-service:8000")
TRACKS_SERVICE_URL = os.getenv("TRACKS_SERVICE_URL", "http://tracks-service:8000")
UPLOAD_SERVICE_URL = os.getenv("UPLOAD_SERVICE_URL", "http://upload-service:8000")
SOCIAL_SERVICE_URL = os.getenv("SOCIAL_SERVICE_URL", "http://social-service:8000")


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

rate_limit = os.getenv("RATE_LIMIT", "100/minute")
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_limit])

app = FastAPI(title="API Gateway", version="0.2.0")
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"}),
)
app.add_middleware(SlowAPIMiddleware)

cors_allow_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@dataclass
class GatewayUser:
    user_id: str
    email: str | None


class VerifyRequest(BaseModel):
    id_token: str


class PresignRequest(BaseModel):
    filename: str
    content_type: str = "audio/mpeg"
    title: str
    artist: str
    visibility: str = "private"


class CompleteRequest(BaseModel):
    track_id: str
    object_key: str


class LikeRequest(BaseModel):
    track_id: str


class CommentRequest(BaseModel):
    track_id: str
    text: str


class FollowRequest(BaseModel):
    target_user_id: str


@app.middleware("http")
async def csrf_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
    csrf_protect = os.getenv("CSRF_PROTECT", "0") == "1"
    if csrf_protect and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not request.headers.get("x-csrf-token"):
            return JSONResponse(status_code=403, content={"detail": "Missing CSRF token"})

    return await call_next(request)


def extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return auth_header.split(" ", 1)[1].strip()


async def verify_identity_token(id_token: str) -> GatewayUser:
    async with httpx.AsyncClient(timeout=6.0) as client:
        response = await client.post(
            f"{IDENTITY_SERVICE_URL}/auth/verify",
            json={"id_token": id_token},
        )

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = response.json()
    return GatewayUser(user_id=payload["user_id"], email=payload.get("email"))


async def auth_from_request(request: Request) -> GatewayUser:
    token = extract_bearer_token(request)
    return await verify_identity_token(token)


async def proxy_request(
    method: str,
    url: str,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> Any:
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.request(
            method=method,
            url=url,
            json=json_body,
            headers=headers,
            params=params,
        )

    if response.status_code >= 500:
        raise HTTPException(status_code=502, detail="Upstream service error")
    if response.status_code >= 400:
        detail = response.json().get("detail", "Bad request") if response.headers.get("content-type", "").startswith("application/json") else "Bad request"
        raise HTTPException(status_code=response.status_code, detail=detail)

    if not response.content:
        return None
    return response.json()


@app.get("/healthz")
@limiter.limit("30/second")
async def healthz(request: Request) -> dict[str, str]:
    logger.info("healthcheck", extra={"service": SERVICE_NAME})
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/services/health")
@limiter.limit("10/second")
async def services_health(request: Request) -> dict[str, Any]:
    services = {
        "identity": IDENTITY_SERVICE_URL,
        "tracks": TRACKS_SERVICE_URL,
        "upload": UPLOAD_SERVICE_URL,
        "social": SOCIAL_SERVICE_URL,
    }

    results: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for service, base_url in services.items():
            try:
                response = await client.get(f"{base_url}/healthz")
                results[service] = {
                    "status": "ok" if response.status_code == 200 else "degraded",
                    "code": response.status_code,
                }
            except Exception as exc:  # pragma: no cover
                results[service] = {"status": "down", "error": str(exc)}

    return {"gateway": "ok", "services": results}


@app.post("/auth/verify")
@limiter.limit("20/second")
async def auth_verify(request: Request, payload: VerifyRequest | None = None) -> dict[str, Any]:
    token = payload.id_token if payload else extract_bearer_token(request)
    user = await verify_identity_token(token)
    return {"user_id": user.user_id, "email": user.email}


@app.get("/tracks")
@limiter.limit("30/second")
async def list_tracks(request: Request, owner_id: str | None = None, status: str | None = None, visibility: str | None = None) -> dict[str, Any]:
    params: dict[str, str] = {}
    if owner_id:
        params["owner_id"] = owner_id
    if status:
        params["status"] = status
    if visibility:
        params["visibility"] = visibility

    return await proxy_request("GET", f"{TRACKS_SERVICE_URL}/tracks", params=params)


@app.get("/tracks/{track_id}")
@limiter.limit("30/second")
async def get_track(request: Request, track_id: str) -> dict[str, Any]:
    return await proxy_request("GET", f"{TRACKS_SERVICE_URL}/tracks/{track_id}")


@app.post("/uploads/presign")
@limiter.limit("10/second")
async def upload_presign(request: Request, payload: PresignRequest) -> dict[str, Any]:
    user = await auth_from_request(request)
    return await proxy_request(
        "POST",
        f"{UPLOAD_SERVICE_URL}/uploads/presign",
        json_body=payload.model_dump(),
        headers={"x-user-id": user.user_id},
    )


@app.post("/uploads/complete")
@limiter.limit("10/second")
async def upload_complete(request: Request, payload: CompleteRequest) -> dict[str, Any]:
    user = await auth_from_request(request)
    return await proxy_request(
        "POST",
        f"{UPLOAD_SERVICE_URL}/uploads/complete",
        json_body=payload.model_dump(),
        headers={"x-user-id": user.user_id},
    )


@app.post("/social/likes")
@limiter.limit("20/second")
async def social_like(request: Request, payload: LikeRequest) -> dict[str, Any]:
    user = await auth_from_request(request)
    return await proxy_request(
        "POST",
        f"{SOCIAL_SERVICE_URL}/likes",
        json_body=payload.model_dump(),
        headers={"x-user-id": user.user_id},
    )


@app.delete("/social/likes/{track_id}")
@limiter.limit("20/second")
async def social_unlike(request: Request, track_id: str) -> dict[str, Any]:
    user = await auth_from_request(request)
    return await proxy_request(
        "DELETE",
        f"{SOCIAL_SERVICE_URL}/likes/{track_id}",
        headers={"x-user-id": user.user_id},
    )


@app.post("/social/comments")
@limiter.limit("20/second")
async def social_comment(request: Request, payload: CommentRequest) -> dict[str, Any]:
    user = await auth_from_request(request)
    return await proxy_request(
        "POST",
        f"{SOCIAL_SERVICE_URL}/comments",
        json_body=payload.model_dump(),
        headers={"x-user-id": user.user_id},
    )


@app.get("/social/comments/{track_id}")
@limiter.limit("30/second")
async def social_comments(request: Request, track_id: str) -> dict[str, Any]:
    return await proxy_request("GET", f"{SOCIAL_SERVICE_URL}/comments/{track_id}")


@app.post("/social/follows")
@limiter.limit("20/second")
async def social_follow(request: Request, payload: FollowRequest) -> dict[str, Any]:
    user = await auth_from_request(request)
    return await proxy_request(
        "POST",
        f"{SOCIAL_SERVICE_URL}/follows",
        json_body=payload.model_dump(),
        headers={"x-user-id": user.user_id},
    )
