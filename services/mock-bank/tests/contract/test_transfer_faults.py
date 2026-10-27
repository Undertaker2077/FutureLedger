from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.api import create_app
from mock_bank.config import Settings
from mock_bank.models import Account, JournalEntry, Transaction, Transfer


def headers(fault: str | None = None) -> dict[str, str]:
    value = {
        "Authorization": "Bearer test-service-token",
        "X-Authenticated-User": "test_user",
        "Idempotency-Key": "fault-transfer-key",
    }
    if fault:
        value["X-Mock-Fault"] = fault
    return value


def request_quote(client: TestClient) -> dict[str, object]:
    return client.post(
        "/bank/v1/transfers/quotes",
        headers=headers(),
        json={
            "account_id": "acc_daily",
            "recipient_id": "rec_1",
            "amount_cents": 50_000,
            "currency": "CNY",
        },
    ).json()["data"]


def body(quote: dict[str, object]) -> dict[str, object]:
    return {"quote_id": quote["quote_id"], "params_hash": quote["params_hash"]}


def test_before_commit_fault_rolls_back_all_transfer_facts(
    bank_settings: Settings, seeded_session_factory: sessionmaker[Session]
) -> None:
    with TestClient(create_app(bank_settings, seeded_session_factory)) as client:
        transfer_quote = request_quote(client)
        with pytest.raises(RuntimeError, match="before_commit"):
            client.post(
                "/bank/v1/transfers",
                headers=headers("before_commit"),
                json=body(transfer_quote),
            )
    with seeded_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Transfer)) == 0
        assert session.scalar(select(func.count()).select_from(JournalEntry)) == 0
        assert session.scalar(
            select(func.count()).select_from(Transaction).where(
                Transaction.transfer_id.is_not(None)
            )
        ) == 0
        assert session.get(Account, "acc_daily").balance_cents == 900_000


def test_dropped_response_recovers_by_replay_and_status(
    bank_settings: Settings, seeded_session_factory: sessionmaker[Session]
) -> None:
    with TestClient(create_app(bank_settings, seeded_session_factory)) as client:
        transfer_quote = request_quote(client)
        with pytest.raises(RuntimeError, match="dropped response"):
            client.post(
                "/bank/v1/transfers",
                headers=headers("drop_response_after_commit"),
                json=body(transfer_quote),
            )
        replay = client.post(
            "/bank/v1/transfers", headers=headers(), json=body(transfer_quote)
        )
        assert replay.status_code == 200
        transfer = replay.json()["data"]
        status = client.get(
            f"/bank/v1/transfers/{transfer['transfer_id']}", headers=headers()
        )
        assert status.json()["data"]["status"] == "SUCCEEDED"
    with seeded_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Transfer)) == 1
        assert session.scalar(select(func.count()).select_from(JournalEntry)) == 1


def test_fault_header_is_rejected_outside_test_mode(
    bank_settings: Settings, seeded_session_factory: sessionmaker[Session]
) -> None:
    production = replace(bank_settings, environment="production")
    with TestClient(create_app(production, seeded_session_factory)) as client:
        transfer_quote = request_quote(client)
        response = client.post(
            "/bank/v1/transfers",
            headers=headers("before_commit"),
            json=body(transfer_quote),
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED"
