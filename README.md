# SoundCloud MVP Microservices (Backend First)

Backend-first microservices MVP for a mini SoundCloud clone.

## Stack

- API services: FastAPI (Python 3.12)
- Database: PostgreSQL (metadata only)
- Queue/Cache: Redis
- Object storage: MinIO (S3-compatible)
- Reverse proxy: Nginx
- Frontend scaffold: React + Vite (optional for this stage)

## Services

- `api-gateway`: single entrypoint, CORS/CSRF/rate-limit, auth-aware routing
- `identity-service`: verifies Firebase ID token (or `AUTH_BYPASS=1`) and upserts user profile
- `tracks-service`: track CRUD + internal publish/fail endpoints
- `upload-service`: issues pre-signed upload URL and queues processing after upload completion
- `social-service`: likes, comments, follows
- `processing-worker`: consumes Redis jobs, checks MinIO object, publishes track

## Core flow

1. Client signs in with Firebase and gets `ID token`.
2. Client calls gateway endpoints with `Authorization: Bearer <id_token>`.
3. Gateway verifies token via `identity-service` and forwards `x-user-id`.
4. `upload-service` returns pre-signed URL + creates track in `processing` state.
5. Client uploads file to MinIO and calls `/uploads/complete`.
6. Worker consumes queue job and marks track as `published` (or `failed`).

## Quick start

```bash
cp .env.example .env
make up
make migrate
```

Open:

- Gateway: `http://localhost:8088/api`
- OpenAPI docs: `http://localhost:8088/api/docs`
- MinIO console: `http://localhost:9001`

## Verify Backend Flow

```bash
make smoke
```

The smoke script runs:

1. `/auth/verify`
2. `/uploads/presign`
3. file upload to MinIO (pre-signed URL)
4. `/uploads/complete`
5. status polling until track is `published`

## Migrations

Each service has its own Alembic history and version table in the shared PostgreSQL database:

- `identity-service` -> `alembic_version_identity`
- `tracks-service` -> `alembic_version_tracks`
- `social-service` -> `alembic_version_social`
- `upload-service` -> `alembic_version_upload` (baseline only, no SQL schema yet)

## Important env vars

- `DATABASE_URL`
- `REDIS_URL`
- `MINIO_*`
- `INTERNAL_API_TOKEN`
- `STARTUP_STRICT` (`1` to fail service startup when DB init fails)
- `AUTH_BYPASS` (`1` for local dev without Firebase credentials)
- `FIREBASE_CREDENTIALS_PATH` (required only when `AUTH_BYPASS=0`)

## Monorepo structure

```text
soundcloud-mvp/
  web/
  services/
    api-gateway/
    identity-service/
    tracks-service/
    upload-service/
    social-service/
    processing-worker/
  infra/nginx/
  docker-compose.yml
  Makefile
```
