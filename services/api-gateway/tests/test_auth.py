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
