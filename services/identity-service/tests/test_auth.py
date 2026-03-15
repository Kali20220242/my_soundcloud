from fastapi.testclient import TestClient

import app.main as main_module
from app.main import IdentityClaims, app


def test_verify_dev_token_without_db(monkeypatch) -> None:
    def fake_verify_token(_: str) -> IdentityClaims:
        return IdentityClaims(uid="alice", email="alice@example.com", name="Alice", picture=None)

    def fake_upsert_user(_: IdentityClaims) -> tuple[dict[str, str | None], bool]:
        return {
            "user_id": "alice",
            "email": "alice@example.com",
            "name": "Alice",
            "picture": None,
            "username": "alice",
            "bio": None,
        }, True

    monkeypatch.setattr(main_module, "verify_token", fake_verify_token)
    monkeypatch.setattr(main_module, "upsert_user", fake_upsert_user)

    with TestClient(app) as client:
        response = client.post("/auth/verify", json={"id_token": "dev:alice:alice@example.com:Alice"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == "alice"
    assert payload["email"] == "alice@example.com"
    assert payload["username"] == "alice"
    assert payload["is_new"] is True
