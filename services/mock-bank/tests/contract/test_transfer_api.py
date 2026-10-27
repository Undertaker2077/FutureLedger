from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.api import create_app
from mock_bank.config import Settings
from mock_bank.models import JournalEntry, Transaction, Transfer


@pytest.fixture()
def client(
    bank_settings: Settings, seeded_session_factory: sessionmaker[Session]
) -> TestClient:
    with TestClient(create_app(bank_settings, seeded_session_factory)) as test_client:
        yield test_client


def headers(**updates: str) -> dict[str, str]:
    value = {
        "Authorization": "Bearer test-service-token",
        "X-Authenticated-User": "test_user",
    }
    value.update(updates)
    return value


def valid_request() -> dict[str, object]:
    return {
        "account_id": "acc_daily",
        "recipient_id": "rec_1",
        "amount_cents": 50_000,
        "currency": "CNY",
        "reference": "manual 500 transfer",
    }


def bank_write_counts(factory: sessionmaker[Session]) -> tuple[int, int, int]:
    with factory() as session:
        return (
            session.scalar(select(func.count()).select_from(Transfer)) or 0,
            session.scalar(select(func.count()).select_from(JournalEntry)) or 0,
            session.scalar(
                select(func.count()).select_from(Transaction).where(
                    Transaction.kind == "transfer"
                )
            )
            or 0,
        )


def test_quote_submit_and_status_contract(client: TestClient) -> None:
    quote_response = client.post(
        "/bank/v1/transfers/quotes", headers=headers(), json=valid_request()
    )
    assert quote_response.status_code == 201
    quote = quote_response.json()["data"]
    assert quote["amount_cents"] == 50_000
    assert quote["fee_cents"] == 0

    submit_response = client.post(
        "/bank/v1/transfers",
        headers=headers(**{"Idempotency-Key": "api-manual-transfer-500"}),
        json={"quote_id": quote["quote_id"], "params_hash": quote["params_hash"]},
    )
    assert submit_response.status_code == 201
    transfer = submit_response.json()["data"]
    assert transfer["status"] == "SUCCEEDED"

    status_response = client.get(
        f"/bank/v1/transfers/{transfer['transfer_id']}", headers=headers()
    )
    assert status_response.status_code == 200
    assert status_response.json()["data"]["bank_reference"] == transfer["bank_reference"]


@pytest.mark.parametrize(
    ("updates", "code"),
    [
        ({"amount_cents": 0}, "INVALID_AMOUNT"),
        ({"currency": "USD"}, "INVALID_CURRENCY"),
        ({"unexpected": "field"}, "INVALID_REQUEST"),
    ],
)
def test_invalid_quote_bodies_have_structured_errors_and_no_writes(
    client: TestClient,
    seeded_session_factory: sessionmaker[Session],
    updates: dict[str, object],
    code: str,
) -> None:
    payload = {**valid_request(), **updates}
    before = bank_write_counts(seeded_session_factory)
    response = client.post("/bank/v1/transfers/quotes", headers=headers(), json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == code
    assert bank_write_counts(seeded_session_factory) == before


def test_submit_requires_idempotency_key(client: TestClient) -> None:
    quote = client.post(
        "/bank/v1/transfers/quotes", headers=headers(), json=valid_request()
    ).json()["data"]
    response = client.post(
        "/bank/v1/transfers",
        headers=headers(),
        json={"quote_id": quote["quote_id"], "params_hash": quote["params_hash"]},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_IDEMPOTENCY_KEY"
