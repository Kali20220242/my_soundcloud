# SoundCloud Microservices Web App

Full-stack web app (not landing/MVP shell) built as microservices.

## Stack

- Frontend: React + Vite + React Router
- API services: FastAPI (Python 3.12)
- Database: PostgreSQL (metadata only)
- Queue/Cache: Redis
- Object storage: MinIO (S3-compatible)
- Reverse proxy: Nginx

## Services

- `api-gateway`: single entrypoint, CORS/CSRF/rate-limit, auth-aware routing
- `identity-service`: Firebase token verification, profile data (`username`, `bio`, `picture`)
- `tracks-service`: track CRUD, feed filters/search/sort, play counter
- `upload-service`: pre-signed upload for tracks + avatar image pre-signed upload
- `social-service`: likes, comments, follows, profile stats
- `processing-worker`: consumes Redis jobs and publishes processed tracks
- `web`: multi-page SPA (`/`, `/login`, `/upload`, `/tracks/:id`, `/profiles/:userId`)

## Core flow

1. Client signs in (`dev:*` token locally or Firebase Google).
2. Frontend sends `Authorization: Bearer <id_token>` to gateway.
3. Gateway verifies token via `identity-service` and forwards `x-user-id`.
4. Upload track flow:
   - `/uploads/presign`
   - direct PUT to MinIO
   - `/uploads/complete`
   - worker marks track `processing -> published`
5. Avatar flow:
   - `/uploads/avatar/presign`
   - direct PUT to MinIO
   - `/me` PATCH with `picture` URL

## Frontend pages

- `GET /` Feed page (search/sort, track cards)
- `GET /login` Login page
- `GET /upload` Upload page (auth required)
- `GET /tracks/:trackId` Track page (player, comments, likes, owner editing)
- `GET /profiles/:userId` Profile page (avatar, profile edit, user tracks, follow/unfollow)

## Quick start

```bash
cp .env.example .env
make up
make migrate
```

Open:

- Web app: `http://localhost:5173`
- Gateway: `http://localhost:8088/api`
- OpenAPI docs: `http://localhost:8088/api/docs`
- MinIO console: `http://localhost:9001`

## Validation

```bash
make test
make smoke
```

`make smoke` verifies auth -> presign -> upload -> queue -> publish flow.

## Important env vars

- `DATABASE_URL`
- `REDIS_URL`
- `MINIO_ENDPOINT`
- `MINIO_PUBLIC_ENDPOINT`
- `MINIO_BUCKET`
- `INTERNAL_API_TOKEN`
- `AUTH_BYPASS`
- `FIREBASE_CREDENTIALS_PATH`
- `VITE_FIREBASE_*` (optional for Google login on web)

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
