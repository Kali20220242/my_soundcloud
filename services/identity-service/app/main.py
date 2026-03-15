import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
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
app = FastAPI(title="Identity Service", version="0.2.0")


class VerifyRequest(BaseModel):
    id_token: str


class VerifyResponse(BaseModel):
    user_id: str
    email: str | None
    name: str | None
    picture: str | None
    is_new: bool


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
        # dev token formats:
        # dev:<uid>
        # dev:<uid>:<email>:<name>
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
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )


def upsert_user(claims: IdentityClaims) -> tuple[dict[str, str | None], bool]:
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT uid FROM users WHERE uid = :uid"),
            {"uid": claims.uid},
        ).first()
        is_new = existing is None

        row = conn.execute(
            text(
                """
                INSERT INTO users (uid, email, name, picture)
                VALUES (:uid, :email, :name, :picture)
                ON CONFLICT (uid)
                DO UPDATE SET
                    email = EXCLUDED.email,
                    name = EXCLUDED.name,
                    picture = EXCLUDED.picture,
                    updated_at = NOW()
                RETURNING uid, email, name, picture
                """
            ),
            {
                "uid": claims.uid,
                "email": claims.email,
                "name": claims.name,
                "picture": claims.picture,
            },
        ).one()

    return {
        "user_id": row.uid,
        "email": row.email,
        "name": row.name,
        "picture": row.picture,
    }, is_new


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
    return {"status": "ok", "service": SERVICE_NAME, "ts": datetime.utcnow().isoformat()}


@app.post("/auth/verify", response_model=VerifyResponse)
def verify(payload: VerifyRequest) -> VerifyResponse:
    claims = verify_token(payload.id_token)
    user, is_new = upsert_user(claims)
    return VerifyResponse(**user, is_new=is_new)
