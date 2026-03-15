from fastapi.testclient import TestClient

from app.main import app


def test_verify_dev_token() -> None:
    with TestClient(app) as client:
        response = client.post("/auth/verify", json={"id_token": "dev:alice:alice@example.com:Alice"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == "alice"
    assert payload["email"] == "alice@example.com"
