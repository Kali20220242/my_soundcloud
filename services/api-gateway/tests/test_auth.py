from fastapi.testclient import TestClient

import app.main as main_module
from app.main import GatewayUser, app


def test_gateway_auth_verify_with_payload(monkeypatch) -> None:
    async def fake_verify(_: str) -> GatewayUser:
        return GatewayUser(user_id="alice", email="alice@example.com")

    monkeypatch.setattr(main_module, "verify_identity_token", fake_verify)

    with TestClient(app) as client:
        response = client.post("/auth/verify", json={"id_token": "dev:alice"})

    assert response.status_code == 200
    assert response.json() == {"user_id": "alice", "email": "alice@example.com"}


def test_gateway_get_me_proxies_identity(monkeypatch) -> None:
    async def fake_auth_from_request(_) -> GatewayUser:
        return GatewayUser(user_id="alice", email="alice@example.com")

    async def fake_proxy_request(method: str, url: str, **kwargs):
        assert method == "GET"
        assert url.endswith("/users/alice")
        return {"user_id": "alice", "username": "alice"}

    monkeypatch.setattr(main_module, "auth_from_request", fake_auth_from_request)
    monkeypatch.setattr(main_module, "proxy_request", fake_proxy_request)

    with TestClient(app) as client:
        response = client.get("/me", headers={"Authorization": "Bearer dev:alice"})

    assert response.status_code == 200
    assert response.json()["user_id"] == "alice"


def test_gateway_tracks_passes_query_and_optional_user(monkeypatch) -> None:
    async def fake_optional_auth(_) -> GatewayUser:
        return GatewayUser(user_id="alice", email="alice@example.com")

    async def fake_proxy_request(method: str, url: str, **kwargs):
        assert method == "GET"
        assert url.endswith("/tracks")
        assert kwargs["headers"] == {"x-user-id": "alice"}
        assert kwargs["params"]["q"] == "wave"
        assert kwargs["params"]["sort"] == "popular"
        assert kwargs["params"]["limit"] == 5
        assert kwargs["params"]["offset"] == 2
        return {"items": [], "total": 0}

    monkeypatch.setattr(main_module, "optional_auth_from_request", fake_optional_auth)
    monkeypatch.setattr(main_module, "proxy_request", fake_proxy_request)

    with TestClient(app) as client:
        response = client.get("/tracks?q=wave&sort=popular&limit=5&offset=2", headers={"Authorization": "Bearer dev:alice"})

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_gateway_avatar_presign_requires_auth_and_proxies(monkeypatch) -> None:
    async def fake_auth_from_request(_) -> GatewayUser:
        return GatewayUser(user_id="alice", email="alice@example.com")

    async def fake_proxy_request(method: str, url: str, **kwargs):
        assert method == "POST"
        assert url.endswith("/uploads/avatar/presign")
        assert kwargs["headers"] == {"x-user-id": "alice"}
        assert kwargs["json_body"]["filename"] == "avatar.png"
        return {"upload_url": "http://minio.local/upload"}

    monkeypatch.setattr(main_module, "auth_from_request", fake_auth_from_request)
    monkeypatch.setattr(main_module, "proxy_request", fake_proxy_request)

    with TestClient(app) as client:
        response = client.post(
            "/uploads/avatar/presign",
            headers={"Authorization": "Bearer dev:alice"},
            json={"filename": "avatar.png", "content_type": "image/png"},
        )

    assert response.status_code == 200
    assert response.json()["upload_url"] == "http://minio.local/upload"


def test_gateway_soundcloud_import(monkeypatch) -> None:
    async def fake_auth_from_request(_) -> GatewayUser:
        return GatewayUser(user_id="alice", email="alice@example.com")

    async def fake_fetch_soundcloud_tracks(access_token: str, limit: int):
        assert access_token == "sc-token"
        assert limit == 2
        return [
            {
                "id": 10,
                "title": "Track A",
                "permalink_url": "https://soundcloud.com/alice/track-a",
                "sharing": "public",
                "user": {"username": "Alice"},
                "playback_count": 12,
            }
        ]

    async def fake_proxy_request(method: str, url: str, **kwargs):
        assert method == "POST"
        assert url.endswith("/imports/soundcloud")
        assert kwargs["headers"] == {"x-user-id": "alice"}
        assert kwargs["json_body"]["owner_id"] == "alice"
        assert kwargs["json_body"]["tracks"][0]["source_track_id"] == "10"
        return {"imported": 1, "created": 1, "updated": 0}

    monkeypatch.setattr(main_module, "auth_from_request", fake_auth_from_request)
    monkeypatch.setattr(main_module, "fetch_soundcloud_tracks", fake_fetch_soundcloud_tracks)
    monkeypatch.setattr(main_module, "proxy_request", fake_proxy_request)

    with TestClient(app) as client:
        response = client.post(
            "/integrations/soundcloud/import",
            headers={"Authorization": "Bearer dev:alice"},
            json={"access_token": "sc-token", "limit": 2},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["fetched"] == 1
    assert payload["imported"] == 1
    assert payload["created"] == 1
