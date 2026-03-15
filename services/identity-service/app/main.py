import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
from pythonjsonlogger import jsonlogger
from sqlalchemy import create_engine, text

try:
    import firebase_admin
    from firebase_admin import auth, credentials
except Exception:  # pragma: no cover
    firebase_admin = None
    auth = None
    credentials = None

SERVICE_NAME = "identity-service"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@postgres:5432/soundcloud")
AUTH_BYPASS = os.getenv("AUTH_BYPASS", "1") == "1"
STARTUP_STRICT = os.getenv("STARTUP_STRICT", "0") == "1"
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


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
app = FastAPI(title="Identity Service", version="1.0.0")


class VerifyRequest(BaseModel):
    id_token: str


class VerifyResponse(BaseModel):
    user_id: str
    email: str | None
    name: str | None
    picture: str | None
    username: str | None
    bio: str | None
    is_new: bool


class UserProfileOut(BaseModel):
    user_id: str
    email: str | None
    name: str | None
    picture: str | None
    username: str | None
    bio: str | None
    created_at: str | None
    updated_at: str | None


class UpdateMePayload(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    username: str | None = Field(default=None, max_length=32)
    bio: str | None = Field(default=None, max_length=500)
    picture: str | None = Field(default=None, max_length=1000)


@dataclass
class IdentityClaims:
    uid: str
    email: str | None
    name: str | None
    picture: str | None


def init_firebase() -> None:
    if AUTH_BYPASS:
        logger.info("firebase_bypass_enabled")
        return

    if firebase_admin is None:
        raise RuntimeError("firebase-admin is not installed")

    if firebase_admin._apps:  # type: ignore[attr-defined]
        return

    credentials_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
    if credentials_path:
        cred = credentials.Certificate(credentials_path)
        firebase_admin.initialize_app(cred)
    else:
        firebase_admin.initialize_app()


def verify_token(id_token: str) -> IdentityClaims:
    if AUTH_BYPASS:
        parts = id_token.split(":")
        if len(parts) >= 2 and parts[0] == "dev":
            uid = parts[1]
            email = parts[2] if len(parts) >= 3 and parts[2] else f"{uid}@local.dev"
            name = parts[3] if len(parts) >= 4 and parts[3] else uid
            return IdentityClaims(uid=uid, email=email, name=name, picture=None)

        uid = "dev-user"
        return IdentityClaims(uid=uid, email="dev-user@local.dev", name="Dev User", picture=None)

    if auth is None:
        raise HTTPException(status_code=500, detail="Firebase auth module unavailable")

    try:
        claims = auth.verify_id_token(id_token)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=401, detail="Invalid Firebase ID token") from exc

    return IdentityClaims(
        uid=claims["uid"],
        email=claims.get("email"),
        name=claims.get("name"),
        picture=claims.get("picture"),
    )


def create_tables() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS users (
                    uid TEXT PRIMARY KEY,
                    email TEXT,
                    name TEXT,
                    picture TEXT,
                    username TEXT,
                    bio TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT"))
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique
                ON users (LOWER(username))
                WHERE username IS NOT NULL
                """
            )
        )


def default_username(uid: str) -> str:
    candidate = re.sub(r"[^a-zA-Z0-9_]", "_", uid).strip("_").lower()
    return candidate[:24] or "user"


def generate_unique_username(conn, uid: str) -> str:
    base = default_username(uid)
    candidate = base
    attempt = 0

    while True:
        taken = conn.execute(
            text("SELECT uid FROM users WHERE LOWER(username) = LOWER(:username) AND uid <> :uid"),
            {"username": candidate, "uid": uid},
        ).first()
        if taken is None:
            return candidate

        attempt += 1
        suffix = f"_{attempt}"
        candidate = f"{base[:max(1, 32 - len(suffix))]}{suffix}"


def serialize_user_row(row) -> dict[str, str | None]:
    return {
        "user_id": row.uid,
        "email": row.email,
        "name": row.name,
        "picture": row.picture,
        "username": row.username,
        "bio": row.bio,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def upsert_user(claims: IdentityClaims) -> tuple[dict[str, str | None], bool]:
    with engine.begin() as conn:
        existing = conn.execute(text("SELECT uid, username FROM users WHERE uid = :uid"), {"uid": claims.uid}).first()
        is_new = existing is None
        username = generate_unique_username(conn, claims.uid) if is_new or not existing.username else existing.username

        row = conn.execute(
            text(
                """
                INSERT INTO users (uid, email, name, picture, username)
                VALUES (:uid, :email, :name, :picture, :username)
                ON CONFLICT (uid)
                DO UPDATE SET
                    email = EXCLUDED.email,
                    name = EXCLUDED.name,
                    picture = EXCLUDED.picture,
                    username = COALESCE(users.username, EXCLUDED.username),
                    updated_at = NOW()
                RETURNING *
                """
            ),
            {
                "uid": claims.uid,
                "email": claims.email,
                "name": claims.name,
                "picture": claims.picture,
                "username": username,
            },
        ).one()

    return serialize_user_row(row), is_new


def get_user_row(user_id: str):
    with engine.begin() as conn:
        return conn.execute(text("SELECT * FROM users WHERE uid = :uid"), {"uid": user_id}).first()


def require_user(x_user_id: str | None) -> str:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing x-user-id")
    return x_user_id


def validate_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_PATTERN.match(username):
        raise HTTPException(status_code=400, detail="Username must be 3-32 chars: letters, digits, underscore")
    return username


@app.on_event("startup")
def on_startup() -> None:
    try:
        create_tables()
        init_firebase()
    except Exception as exc:  # pragma: no cover
        logger.exception("startup_partial_failure", extra={"service": SERVICE_NAME, "error": str(exc)})
        if STARTUP_STRICT:
            raise
    logger.info("startup_complete", extra={"service": SERVICE_NAME, "bypass": AUTH_BYPASS})


@app.get("/healthz")
def healthz() -> dict[str, str]:
    logger.info("healthcheck", extra={"service": SERVICE_NAME})
    return {"status": "ok", "service": SERVICE_NAME, "ts": datetime.now(UTC).isoformat()}


@app.post("/auth/verify", response_model=VerifyResponse)
def verify(payload: VerifyRequest) -> VerifyResponse:
    claims = verify_token(payload.id_token)
    user, is_new = upsert_user(claims)
    return VerifyResponse(**user, is_new=is_new)


@app.get("/users/{user_id}", response_model=UserProfileOut)
def get_user(user_id: str) -> UserProfileOut:
    row = get_user_row(user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserProfileOut(**serialize_user_row(row))


@app.get("/users")
def search_users(
    query: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, list[dict[str, str | None]]]:
    search_query = query or q
    params: dict[str, str | int] = {"limit": limit}
    sql = "SELECT * FROM users"
    if search_query:
        sql += " WHERE uid ILIKE :q OR email ILIKE :q OR name ILIKE :q OR username ILIKE :q"
        params["q"] = f"%{search_query.strip()}%"
    sql += " ORDER BY updated_at DESC LIMIT :limit"

    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).all()
    return {"items": [serialize_user_row(row) for row in rows]}


@app.get("/users/me", response_model=UserProfileOut)
def get_me(x_user_id: str | None = Header(default=None)) -> UserProfileOut:
    user_id = require_user(x_user_id)
    row = get_user_row(user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserProfileOut(**serialize_user_row(row))


@app.patch("/users/me", response_model=UserProfileOut)
def update_me(payload: UpdateMePayload, x_user_id: str | None = Header(default=None)) -> UserProfileOut:
    user_id = require_user(x_user_id)

    fields: dict[str, str] = {}
    if payload.name is not None:
        fields["name"] = payload.name.strip()
    if payload.picture is not None:
        fields["picture"] = payload.picture.strip()
    if payload.bio is not None:
        fields["bio"] = payload.bio.strip()
    if payload.username is not None:
        fields["username"] = validate_username(payload.username)

    if not fields:
        row = get_user_row(user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="User not found")
        return UserProfileOut(**serialize_user_row(row))

    setters = [f"{column} = :{column}" for column in fields.keys()]
    params: dict[str, str] = {"uid": user_id, **fields}

    with engine.begin() as conn:
        if "username" in fields:
            existing_username = conn.execute(
                text("SELECT uid FROM users WHERE LOWER(username) = LOWER(:username) AND uid <> :uid"),
                {"username": fields["username"], "uid": user_id},
            ).first()
            if existing_username is not None:
                raise HTTPException(status_code=409, detail="Username already taken")

        row = conn.execute(
            text(
                f"""
                UPDATE users
                SET {', '.join(setters)}, updated_at = NOW()
                WHERE uid = :uid
                RETURNING *
                """
            ),
            params,
        ).first()

    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    return UserProfileOut(**serialize_user_row(row))
