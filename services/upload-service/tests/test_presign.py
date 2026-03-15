from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


def test_presign_contract(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "create_track", lambda owner_id, payload, object_key: "track-123")

    class FakeS3Client:
        @staticmethod
        def generate_presigned_url(*args, **kwargs):
            return "http://minio.local/presigned-url"

    monkeypatch.setattr(main_module, "presign_client", FakeS3Client())

    with TestClient(app) as client:
        response = client.post(
            "/uploads/presign",
            headers={"x-user-id": "alice"},
            json={
                "filename": "My Track.mp3",
                "content_type": "audio/mpeg",
                "title": "My Track",
                "artist": "Alice",
                "visibility": "private",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["track_id"] == "track-123"
    assert payload["bucket"]
    assert payload["object_key"].startswith("raw/alice/")
    assert payload["upload_url"] == "http://minio.local/presigned-url"


def test_avatar_presign_contract(monkeypatch) -> None:
    class FakeS3Client:
        @staticmethod
        def generate_presigned_url(*args, **kwargs):
            return "http://minio.local/avatar-presigned-url"

    monkeypatch.setattr(main_module, "presign_client", FakeS3Client())
    monkeypatch.setattr(main_module, "MINIO_PUBLIC_ENDPOINT", "http://cdn.local")
    monkeypatch.setattr(main_module, "MINIO_BUCKET", "tracks")

    with TestClient(app) as client:
        response = client.post(
            "/uploads/avatar/presign",
            headers={"x-user-id": "alice"},
            json={
                "filename": "avatar.png",
                "content_type": "image/png",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["bucket"] == "tracks"
    assert payload["object_key"].startswith("avatars/alice/")
    assert payload["upload_url"] == "http://minio.local/avatar-presigned-url"
    assert payload["public_url"].startswith("http://cdn.local/tracks/avatars/alice/")
