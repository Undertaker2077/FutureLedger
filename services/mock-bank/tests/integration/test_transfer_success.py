from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.contracts import TransferRequest
from mock_bank.domain import BankError
from mock_bank.models import (
    Account,
    JournalEntry,
    JournalLine,
    Transaction,
    Transfer,
)
from mock_bank.repository import BankRepository
from mock_bank.service import BankService


@pytest.fixture()
def service(seeded_session_factory: sessionmaker[Session]) -> BankService:
    return BankService(BankRepository(seeded_session_factory, "test-internal-token"))


def transfer_request(**updates: object) -> TransferRequest:
    values: dict[str, object] = {
        "account_id": "acc_daily",
        "recipient_id": "rec_1",
        "amount_cents": 50_000,
        "currency": "CNY",
        "reference": "manual 500 transfer",
    }
    values.update(updates)
    return TransferRequest.model_validate(values)


def counts(factory: sessionmaker[Session]) -> tuple[int, int, int]:
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


def test_manual_500_transfer_is_atomic_and_balanced(
    service: BankService, seeded_session_factory: sessionmaker[Session]
) -> None:
    now = datetime.now(timezone.utc)
    quote = service.quote_transfer("test_user", transfer_request(), now)
    result = service.submit_transfer(
        "test_user", quote.quote_id, quote.params_hash, "manual-transfer-500"
    )

    assert result.status == "SUCCEEDED"
    assert result.amount_cents == 50_000
    assert result.bank_reference
    assert service.get_balance("test_user", "acc_daily")["balance_cents"] == 850_000
    assert service.get_transfer_status("test_user", result.transfer_id).bank_reference == result.bank_reference

    with seeded_session_factory() as session:
        transfer = session.get(Transfer, result.transfer_id)
        transaction = session.scalar(
            select(Transaction).where(Transaction.transfer_id == result.transfer_id)
        )
        entry = session.scalar(
            select(JournalEntry).where(JournalEntry.business_ref == result.transfer_id)
        )
        lines = list(
            session.scalars(select(JournalLine).where(JournalLine.entry_id == entry.id))
        )
        assert transfer.status == "SUCCEEDED"
        assert transaction.status == "POSTED"
        assert transaction.direction == "OUT"
        assert transaction.amount_cents == 50_000
        assert len(lines) == 2
        assert {line.ledger_account_ref for line in lines} == {
            "account:acc_daily",
            "clearing:external",
        }
        assert sum(line.signed_cents for line in lines) == 0


@pytest.mark.parametrize(
    ("request_updates", "expected_code"),
    [
        ({"account_id": "acc_other"}, "FORBIDDEN"),
        ({"recipient_id": "rec_5"}, "RECIPIENT_UNVERIFIED"),
    ],
)
def test_invalid_quote_requests_do_not_mutate_bank_facts(
    service: BankService,
    seeded_session_factory: sessionmaker[Session],
    request_updates: dict[str, object],
    expected_code: str,
) -> None:
    before = counts(seeded_session_factory)
    with pytest.raises(BankError) as raised:
        service.quote_transfer(
            "test_user", transfer_request(**request_updates), datetime.now(timezone.utc)
        )
    assert raised.value.code == expected_code
    assert counts(seeded_session_factory) == before
    assert service.get_balance("test_user", "acc_daily")["balance_cents"] == 900_000


def test_cross_user_recipient_does_not_bind_or_mutate(
    service: BankService, seeded_session_factory: sessionmaker[Session]
) -> None:
    before = counts(seeded_session_factory)
    with pytest.raises(BankError) as raised:
        service.quote_transfer(
            "isolation_user", transfer_request(account_id="acc_other"), datetime.now(timezone.utc)
        )
    assert raised.value.code == "FORBIDDEN"
    assert counts(seeded_session_factory) == before


def test_mismatched_confirmation_hash_leaves_state_unchanged(
    service: BankService, seeded_session_factory: sessionmaker[Session]
) -> None:
    quote = service.quote_transfer(
        "test_user", transfer_request(), datetime.now(timezone.utc)
    )
    before = counts(seeded_session_factory)
    with pytest.raises(BankError) as raised:
        service.submit_transfer(
            "test_user", quote.quote_id, "0" * 64, "mismatch-transfer-500"
        )
    assert raised.value.code == "QUOTE_MISMATCH"
    assert counts(seeded_session_factory) == before


def test_expired_quote_leaves_state_unchanged(
    service: BankService, seeded_session_factory: sessionmaker[Session]
) -> None:
    quote = service.quote_transfer(
        "test_user", transfer_request(), datetime.now(timezone.utc) - timedelta(minutes=6)
    )
    before = counts(seeded_session_factory)
    with pytest.raises(BankError) as raised:
        service.submit_transfer(
            "test_user", quote.quote_id, quote.params_hash, "expired-transfer-500"
        )
    assert raised.value.code == "QUOTE_EXPIRED"
    assert counts(seeded_session_factory) == before


def test_quote_uses_configured_ttl(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    now = datetime.now(timezone.utc)
    service = BankService(
        BankRepository(seeded_session_factory, "test-internal-token"),
        quote_ttl_seconds=17,
    )

    quote = service.quote_transfer("test_user", transfer_request(), now)

    assert quote.expires_at - now == timedelta(seconds=17)

