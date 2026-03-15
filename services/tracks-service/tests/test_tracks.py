from fastapi.testclient import TestClient

from app.main import app


def test_create_track_invalid_visibility() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/tracks",
            json={
                "owner_id": "dev-user",
                "title": "Track A",
                "artist": "Artist A",
                "raw_object_key": "raw/dev-user/test.mp3",
                "visibility": "friends-only",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid visibility"


def test_list_tracks_invalid_sort() -> None:
    with TestClient(app) as client:
        response = client.get("/tracks?sort=oldest")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid sort; use recent or popular"


def test_list_tracks_rejects_non_public_visibility_for_anonymous_feed() -> None:
    with TestClient(app) as client:
        response = client.get("/tracks?visibility=private")

    assert response.status_code == 400
    assert response.json()["detail"] == "Only public visibility is allowed for this query"


def test_soundcloud_import_requires_user_header() -> None:
    with TestClient(app) as client:
        response = client.post("/imports/soundcloud", json={"owner_id": "alice", "tracks": []})

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing x-user-id"


def test_soundcloud_import_forbidden_on_owner_mismatch() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/imports/soundcloud",
            headers={"x-user-id": "alice"},
            json={"owner_id": "bob", "tracks": []},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"
