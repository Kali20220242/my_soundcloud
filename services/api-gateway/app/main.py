import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
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
SOUNDCLOUD_API_BASE = os.getenv("SOUNDCLOUD_API_BASE", "https://api.soundcloud.com")


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

app = FastAPI(title="API Gateway", version="1.0.0")
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
    description: str | None = Field(default=None, max_length=1000)
    genre: str | None = Field(default=None, max_length=64)


class CompleteRequest(BaseModel):
    track_id: str
    object_key: str


class AvatarPresignRequest(BaseModel):
    filename: str
    content_type: str = "image/jpeg"


class SoundCloudImportRequest(BaseModel):
    access_token: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=200, ge=1, le=2000)


class LikeRequest(BaseModel):
    track_id: str


class CommentRequest(BaseModel):
    track_id: str
    text: str


class FollowRequest(BaseModel):
    target_user_id: str


class UpdateProfileRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    username: str | None = Field(default=None, max_length=32)
    bio: str | None = Field(default=None, max_length=500)
    picture: str | None = Field(default=None, max_length=1000)


class UpdateTrackRequest(BaseModel):
    title: str | None = Field(default=None, max_length=180)
    artist: str | None = Field(default=None, max_length=120)
    visibility: str | None = Field(default=None)
    description: str | None = Field(default=None, max_length=1000)
    genre: str | None = Field(default=None, max_length=64)


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
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return token


def extract_optional_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization")
    if not auth_header:
        return None
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return token


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


async def optional_auth_from_request(request: Request) -> GatewayUser | None:
    token = extract_optional_bearer_token(request)
    if not token:
        return None
    return await verify_identity_token(token)


async def proxy_request(
    method: str,
    url: str,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
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
        detail = "Bad request"
        if response.headers.get("content-type", "").startswith("application/json"):
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
        elif response.text:
            detail = response.text[:200]
        raise HTTPException(status_code=response.status_code, detail=detail)

    if not response.content:
        return None
    return response.json()


def user_header(user: GatewayUser | None) -> dict[str, str] | None:
    if user is None:
        return None
    return {"x-user-id": user.user_id}


def map_soundcloud_track(item: dict[str, Any]) -> dict[str, Any] | None:
    track_id = item.get("id")
    if track_id is None:
        return None

    source_url = item.get("permalink_url")
    if not source_url:
        return None

    user_payload = item.get("user") if isinstance(item.get("user"), dict) else {}
    publisher_metadata = item.get("publisher_metadata") if isinstance(item.get("publisher_metadata"), dict) else {}
    title = str(item.get("title") or f"SoundCloud Track {track_id}").strip()
    artist = str(user_payload.get("username") or publisher_metadata.get("artist") or "SoundCloud Artist").strip()
    sharing = str(item.get("sharing") or "public").lower()
    visibility = "public" if sharing == "public" else "private"

    duration_ms = item.get("duration")
    duration_seconds: int | None = None
    if isinstance(duration_ms, (int, float)) and duration_ms >= 0:
        duration_seconds = int(duration_ms // 1000)

    playback_count = item.get("playback_count")
    plays_count = int(playback_count) if isinstance(playback_count, (int, float)) and playback_count >= 0 else 0
    description = item.get("description")
    genre = item.get("genre")
    artwork_url = item.get("artwork_url")

    return {
        "source_track_id": str(track_id),
        "source_url": str(source_url)[:2000],
        "title": title[:180] or f"SoundCloud Track {track_id}",
        "artist": artist[:120] or "SoundCloud Artist",
        "visibility": visibility,
        "description": (str(description)[:1000] if description else None),
        "genre": (str(genre)[:64] if genre else None),
        "artwork_url": (str(artwork_url)[:2000] if artwork_url else None),
        "duration_seconds": duration_seconds,
        "plays_count": plays_count,
    }


async def fetch_soundcloud_tracks(access_token: str, limit: int) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    next_url = f"{SOUNDCLOUD_API_BASE.rstrip('/')}/me/tracks?limit=200&linked_partitioning=1"
    auth_scheme = "Bearer"

    async with httpx.AsyncClient(timeout=20.0) as client:
        for scheme in ("Bearer", "OAuth"):
            probe = await client.get(next_url, headers={"Authorization": f"{scheme} {access_token}"})
            if probe.status_code == 200:
                auth_scheme = scheme
                payload = probe.json()
                collection = payload.get("collection", []) if isinstance(payload, dict) else []
                for item in collection:
                    if isinstance(item, dict):
                        collected.append(item)
                        if len(collected) >= limit:
                            return collected[:limit]
                next_url = payload.get("next_href") if isinstance(payload, dict) else None
                break
            if probe.status_code in {401, 403}:
                continue
            raise HTTPException(status_code=400, detail="Cannot read SoundCloud account tracks")
        else:
            raise HTTPException(status_code=401, detail="Invalid SoundCloud access token")

        while next_url and len(collected) < limit:
            response = await client.get(next_url, headers={"Authorization": f"{auth_scheme} {access_token}"})
            if response.status_code != 200:
                break
            payload = response.json()
            collection = payload.get("collection", []) if isinstance(payload, dict) else []
            for item in collection:
                if isinstance(item, dict):
                    collected.append(item)
                    if len(collected) >= limit:
                        break
            next_url = payload.get("next_href") if isinstance(payload, dict) else None

    return collected[:limit]


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


@app.get("/me")
@limiter.limit("20/second")
async def get_me(request: Request) -> dict[str, Any]:
    user = await auth_from_request(request)
    return await proxy_request("GET", f"{IDENTITY_SERVICE_URL}/users/{user.user_id}")


@app.patch("/me")
@limiter.limit("10/second")
async def update_me(request: Request, payload: UpdateProfileRequest) -> dict[str, Any]:
    user = await auth_from_request(request)
    return await proxy_request(
        "PATCH",
        f"{IDENTITY_SERVICE_URL}/users/me",
        json_body=payload.model_dump(exclude_none=True),
        headers={"x-user-id": user.user_id},
    )


@app.get("/users/{user_id}")
@limiter.limit("30/second")
async def get_user(request: Request, user_id: str) -> dict[str, Any]:
    return await proxy_request("GET", f"{IDENTITY_SERVICE_URL}/users/{user_id}")


@app.get("/users")
@limiter.limit("30/second")
async def list_users(request: Request, query: str | None = None, limit: int = 20) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": limit}
    if query:
        params["query"] = query
    return await proxy_request("GET", f"{IDENTITY_SERVICE_URL}/users", params=params)


@app.get("/tracks")
@limiter.limit("30/second")
async def list_tracks(
    request: Request,
    owner_id: str | None = None,
    status: str | None = None,
    visibility: str | None = None,
    q: str | None = None,
    sort: str = "recent",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    user = await optional_auth_from_request(request)
    params: dict[str, Any] = {
        "sort": sort,
        "limit": limit,
        "offset": offset,
    }
    if owner_id:
        params["owner_id"] = owner_id
    if status:
        params["status"] = status
    if visibility:
        params["visibility"] = visibility
    if q:
        params["q"] = q

    return await proxy_request(
        "GET",
        f"{TRACKS_SERVICE_URL}/tracks",
        params=params,
        headers=user_header(user),
    )


@app.get("/tracks/{track_id}")
@limiter.limit("30/second")
async def get_track(request: Request, track_id: str) -> dict[str, Any]:
    user = await optional_auth_from_request(request)
    return await proxy_request(
        "GET",
        f"{TRACKS_SERVICE_URL}/tracks/{track_id}",
        headers=user_header(user),
    )


@app.patch("/tracks/{track_id}")
@limiter.limit("15/second")
async def update_track(request: Request, track_id: str, payload: UpdateTrackRequest) -> dict[str, Any]:
    user = await auth_from_request(request)
    return await proxy_request(
        "PATCH",
        f"{TRACKS_SERVICE_URL}/tracks/{track_id}",
        json_body=payload.model_dump(exclude_none=True),
        headers={"x-user-id": user.user_id},
    )


@app.delete("/tracks/{track_id}")
@limiter.limit("15/second")
async def delete_track(request: Request, track_id: str) -> dict[str, Any]:
    user = await auth_from_request(request)
    return await proxy_request(
        "DELETE",
        f"{TRACKS_SERVICE_URL}/tracks/{track_id}",
        headers={"x-user-id": user.user_id},
    )


@app.post("/tracks/{track_id}/play")
@limiter.limit("40/second")
async def register_track_play(request: Request, track_id: str) -> dict[str, Any]:
    user = await optional_auth_from_request(request)
    return await proxy_request(
        "POST",
        f"{TRACKS_SERVICE_URL}/tracks/{track_id}/play",
        headers=user_header(user),
    )


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


@app.post("/uploads/avatar/presign")
@limiter.limit("10/second")
async def avatar_upload_presign(request: Request, payload: AvatarPresignRequest) -> dict[str, Any]:
    user = await auth_from_request(request)
    return await proxy_request(
        "POST",
        f"{UPLOAD_SERVICE_URL}/uploads/avatar/presign",
        json_body=payload.model_dump(),
        headers={"x-user-id": user.user_id},
    )


@app.post("/integrations/soundcloud/import")
@limiter.limit("5/minute")
async def import_soundcloud(request: Request, payload: SoundCloudImportRequest) -> dict[str, Any]:
    user = await auth_from_request(request)

    source_tracks = await fetch_soundcloud_tracks(payload.access_token, payload.limit)
    mapped_tracks = [mapped for mapped in (map_soundcloud_track(track) for track in source_tracks) if mapped is not None]
    skipped = len(source_tracks) - len(mapped_tracks)

    if not mapped_tracks:
        return {"fetched": len(source_tracks), "imported": 0, "created": 0, "updated": 0, "skipped": skipped}

    result = await proxy_request(
        "POST",
        f"{TRACKS_SERVICE_URL}/imports/soundcloud",
        json_body={"owner_id": user.user_id, "tracks": mapped_tracks},
        headers={"x-user-id": user.user_id},
    )

    return {
        "fetched": len(source_tracks),
        "imported": result.get("imported", 0),
        "created": result.get("created", 0),
        "updated": result.get("updated", 0),
        "skipped": skipped,
    }


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


@app.get("/social/likes/{track_id}/count")
@limiter.limit("30/second")
async def social_likes_count(request: Request, track_id: str) -> dict[str, Any]:
    return await proxy_request("GET", f"{SOCIAL_SERVICE_URL}/likes/{track_id}/count")


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


@app.delete("/social/follows/{target_user_id}")
@limiter.limit("20/second")
async def social_unfollow(request: Request, target_user_id: str) -> dict[str, Any]:
    user = await auth_from_request(request)
    return await proxy_request(
        "DELETE",
        f"{SOCIAL_SERVICE_URL}/follows/{target_user_id}",
        headers={"x-user-id": user.user_id},
    )


@app.get("/social/profiles/{user_id}/stats")
@limiter.limit("30/second")
async def social_profile_stats(request: Request, user_id: str) -> dict[str, Any]:
    return await proxy_request("GET", f"{SOCIAL_SERVICE_URL}/profiles/{user_id}/stats")
