from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.api import create_app
from mock_bank.config import Settings


@pytest.fixture()
def client(
    bank_settings: Settings, seeded_session_factory: sessionmaker[Session]
) -> TestClient:
    with TestClient(create_app(bank_settings, seeded_session_factory)) as value:
        yield value


def headers(key: str | None = None) -> dict[str, str]:
    value = {
        "Authorization": "Bearer test-service-token",
        "X-Authenticated-User": "test_user",
    }
    if key:
        value["Idempotency-Key"] = key
    return value


def test_cancel_route_updates_list_and_status(client: TestClient) -> None:
    cancelled = client.post(
        "/bank/v1/mandates/mandate_2/cancel", headers=headers("api-cancel-video")
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    status = client.get("/bank/v1/mandates/mandate_2", headers=headers())
    assert status.json()["data"]["status"] == "CANCELLED"
    listed = client.get("/bank/v1/mandates", headers=headers()).json()["data"]
    assert next(row for row in listed if row["mandate_id"] == "mandate_2")["status"] == "CANCELLED"


def test_cancel_requires_valid_idempotency_key(client: TestClient) -> None:
    response = client.post(
        "/bank/v1/mandates/mandate_1/cancel", headers=headers()
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_IDEMPOTENCY_KEY"


def test_non_cancellable_returns_unsupported_and_remains_active(client: TestClient) -> None:
    response = client.post(
        "/bank/v1/mandates/mandate_4/cancel", headers=headers("api-cancel-fitness")
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "UNSUPPORTED"
    status = client.get("/bank/v1/mandates/mandate_4", headers=headers())
    assert status.json()["data"]["status"] == "ACTIVE"


def test_cross_user_cancel_is_public_not_found(client: TestClient) -> None:
    response = client.post(
        "/bank/v1/mandates/mandate_1/cancel",
        headers={
            "Authorization": "Bearer test-service-token",
            "X-Authenticated-User": "isolation_user",
            "Idempotency-Key": "cross-user-cancel",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_restore_is_explicitly_unsupported(client: TestClient) -> None:
    capabilities = client.get("/bank/v1/capabilities", headers=headers()).json()["data"]
    assert capabilities["mandate_restore"] is False
    response = client.post(
        "/bank/v1/mandates/mandate_1/restore", headers=headers("restore-key")
    )
    assert response.status_code == 404
