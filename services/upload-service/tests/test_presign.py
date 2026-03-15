from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


def test_presign_contract(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "create_track", lambda owner_id, payload, object_key: "track-123")

    class FakeS3Client:
        @staticmethod
        def generate_presigned_url(*args, **kwargs):
            return "http://minio.local/presigned-url"

    monkeypatch.setattr(main_module, "s3_client", FakeS3Client())

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
