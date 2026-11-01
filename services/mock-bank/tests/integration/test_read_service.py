from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.contracts import TransactionQuery
from mock_bank.domain import BankError
from mock_bank.repository import BankRepository
from mock_bank.service import BankService


@pytest.fixture()
def service(seeded_session_factory: sessionmaker[Session]) -> BankService:
    return BankService(BankRepository(seeded_session_factory, "test-internal-token"))


def test_owned_balance_is_bank_fact(service: BankService) -> None:
    assert service.get_balance("test_user", "acc_daily") == {
        "account_id": "acc_daily",
        "balance_cents": 900_000,
        "currency": "CNY",
        "as_of": "2026-10-01T00:00:00+08:00",
    }


def test_cross_user_balance_is_forbidden_in_service(service: BankService) -> None:
    with pytest.raises(BankError) as raised:
        service.get_balance("test_user", "acc_other")
    assert raised.value.code == "FORBIDDEN"


def test_resolve_recipient_returns_verified_and_unverified_facts(
    service: BankService,
) -> None:
    assert service.resolve_recipient("test_user", "rec_1")["verified"] is True
    unverified = service.resolve_recipient("test_user", "rec_5")
    assert unverified["verified"] is False
    assert unverified["tail4"] == "2005"


def test_transaction_filters_order_limit_cursor_and_public_fields(
    service: BankService,
) -> None:
    query = TransactionQuery(
        account_id="acc_daily",
        start=datetime.fromisoformat("2024-10-01T00:00:00+08:00"),
        end_exclusive=datetime.fromisoformat("2024-10-05T00:00:00+08:00"),
        kind="expense",
        status="POSTED",
        limit=2,
    )
    first = service.list_transactions("test_user", query)
    second = service.list_transactions(
        "test_user", query.model_copy(update={"cursor": first["next_cursor"]})
    )

    assert len(first["items"]) == 2
    assert first["items"] == sorted(
        first["items"], key=lambda row: (row["posted_at"], row["transaction_id"]), reverse=True
    )
    assert {row["transaction_id"] for row in first["items"]}.isdisjoint(
        {row["transaction_id"] for row in second["items"]}
    )
    assert "memo" not in first["items"][0]
    assert set(first["items"][0]) == {
        "transaction_id",
        "account_id",
        "amount_cents",
        "currency",
        "direction",
        "kind",
        "status",
        "category",
        "merchant",
        "posted_at",
        "refund_of",
    }


@pytest.mark.parametrize(
    "query",
    [
        TransactionQuery.model_construct(
            start=datetime.fromisoformat("2024-10-05T00:00:00+08:00"),
            end_exclusive=datetime.fromisoformat("2024-10-01T00:00:00+08:00"),
            limit=50,
        ),
        TransactionQuery.model_construct(kind="unknown", limit=50),
        TransactionQuery.model_construct(status="UNKNOWN", limit=50),
    ],
)
def test_invalid_transaction_filters_are_rejected(
    service: BankService, query: TransactionQuery
) -> None:
    with pytest.raises(BankError) as raised:
        service.list_transactions("test_user", query)
    assert raised.value.code == "INVALID_QUERY"


def test_cursor_is_bound_to_subject(service: BankService) -> None:
    page = service.list_transactions("test_user", TransactionQuery(limit=1))
    with pytest.raises(BankError) as raised:
        service.list_transactions(
            "isolation_user", TransactionQuery(limit=1, cursor=page["next_cursor"])
        )
    assert raised.value.code == "INVALID_CURSOR"


def test_mandate_reads_are_subject_scoped(service: BankService) -> None:
    mandates = service.list_mandates("test_user", account_id="acc_daily")
    assert [row["mandate_id"] for row in mandates] == [
        "mandate_1",
        "mandate_2",
        "mandate_3",
        "mandate_4",
    ]
    assert service.get_mandate_status("test_user", "mandate_4")["cancellable"] is False
    with pytest.raises(BankError) as raised:
        service.list_mandates("test_user", account_id="acc_other")
    assert raised.value.code == "FORBIDDEN"
