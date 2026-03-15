from fastapi.testclient import TestClient

from app.main import app


def test_create_track_contract() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/tracks",
            json={
                "owner_id": "dev-user",
                "title": "Track A",
                "artist": "Artist A",
                "raw_object_key": "raw/dev-user/test.mp3",
                "visibility": "private",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processing"
    assert payload["title"] == "Track A"
