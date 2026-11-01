from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.config import Settings
from mock_bank.api import create_app


@pytest.fixture()
def client(
    bank_settings: Settings, seeded_session_factory: sessionmaker[Session]
) -> TestClient:
    app = create_app(bank_settings, seeded_session_factory)
    with TestClient(app) as test_client:
        yield test_client


def auth_headers(**updates: str) -> dict[str, str]:
    headers = {
        "Authorization": "Bearer test-service-token",
        "X-Authenticated-User": "test_user",
    }
    headers.update(updates)
    return headers


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong", "X-Authenticated-User": "test_user"},
        {"Authorization": "Bearer test-service-token"},
    ],
)
def test_bank_routes_require_service_token_and_subject(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.get("/bank/v1/accounts/acc_daily/balance", headers=headers)
    assert response.status_code == 401
    body = response.json()
    assert body["data"] is None
    assert body["error"]["code"] == "UNAUTHENTICATED"
    assert body["request_id"]


def test_success_envelope_and_request_id(client: TestClient) -> None:
    response = client.get(
        "/bank/v1/accounts/acc_daily/balance",
        headers={**auth_headers(), "X-Request-ID": "request-contract-123"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "data": {
            "account_id": "acc_daily",
            "balance_cents": 900_000,
            "currency": "CNY",
            "as_of": "2026-10-01T00:00:00+08:00",
        },
        "error": None,
        "request_id": "request-contract-123",
    }


def test_capabilities_are_explicit(client: TestClient) -> None:
    body = client.get("/bank/v1/capabilities", headers=auth_headers()).json()["data"]
    assert body == {
        "idempotent_transfers": True,
        "transfer_status_query": True,
        "mandate_status_query": True,
        "scheduled_transfers": False,
        "mandate_restore": False,
    }


def test_liveness_and_readiness(client: TestClient) -> None:
    assert client.get("/health/live").json()["status"] == "ok"
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_cross_user_and_unknown_ids_have_same_public_shape(client: TestClient) -> None:
    forbidden = client.get(
        "/bank/v1/accounts/acc_other/balance", headers=auth_headers()
    )
    unknown = client.get(
        "/bank/v1/accounts/does-not-exist/balance", headers=auth_headers()
    )
    assert forbidden.status_code == unknown.status_code == 404
    assert forbidden.json()["error"] == unknown.json()["error"]


def test_transaction_query_and_mandate_routes(client: TestClient) -> None:
    transactions = client.get(
        "/bank/v1/transactions?account_id=acc_daily&limit=2&status=POSTED",
        headers=auth_headers(),
    )
    assert transactions.status_code == 200
    assert len(transactions.json()["data"]["items"]) == 2

    mandates = client.get("/bank/v1/mandates?account_id=acc_daily", headers=auth_headers())
    assert mandates.status_code == 200
    assert len(mandates.json()["data"]) == 4
