from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.contracts import TransferRequest
from mock_bank.domain import BankError
from mock_bank.models import Account, TransferQuote
from mock_bank.repository import BankRepository
from mock_bank.service import BankService


@pytest.fixture()
def service(seeded_session_factory: sessionmaker[Session]) -> BankService:
    return BankService(BankRepository(seeded_session_factory, "test-internal-token"))


def request(amount: int = 50_000) -> TransferRequest:
    return TransferRequest(
        account_id="acc_daily",
        recipient_id="rec_1",
        amount_cents=amount,
        currency="CNY",
        reference="idempotency test",
    )


def test_identical_submission_replays_same_transfer(service: BankService) -> None:
    quote = service.quote_transfer("test_user", request(), datetime.now(timezone.utc))
    first = service.submit_transfer("test_user", quote.quote_id, quote.params_hash, "same-key-500")
    replay = service.submit_transfer("test_user", quote.quote_id, quote.params_hash, "same-key-500")
    assert replay.transfer_id == first.transfer_id
    assert replay.bank_reference == first.bank_reference
    assert getattr(first, "__replayed__") is False
    assert getattr(replay, "__replayed__") is True
    assert service.get_balance("test_user", "acc_daily")["balance_cents"] == 850_000


def test_same_key_with_changed_parameters_conflicts(service: BankService) -> None:
    first_quote = service.quote_transfer("test_user", request(), datetime.now(timezone.utc))
    service.submit_transfer("test_user", first_quote.quote_id, first_quote.params_hash, "conflict-key")
    changed_quote = service.quote_transfer("test_user", request(60_000), datetime.now(timezone.utc))
    with pytest.raises(BankError) as raised:
        service.submit_transfer(
            "test_user", changed_quote.quote_id, changed_quote.params_hash, "conflict-key"
        )
    assert raised.value.code == "IDEMPOTENCY_CONFLICT"


def test_replacement_quote_accepts_same_unbound_key(service: BankService) -> None:
    expired = service.quote_transfer(
        "test_user", request(), datetime.now(timezone.utc) - timedelta(minutes=6)
    )
    with pytest.raises(BankError) as raised:
        service.submit_transfer(
            "test_user", expired.quote_id, expired.params_hash, "replacement-key"
        )
    assert raised.value.code == "QUOTE_EXPIRED"

    replacement = service.quote_transfer("test_user", request(), datetime.now(timezone.utc))
    assert replacement.params_hash == expired.params_hash
    result = service.submit_transfer(
        "test_user", replacement.quote_id, replacement.params_hash, "replacement-key"
    )
    assert result.status == "SUCCEEDED"


def test_insufficient_funds_is_stable_after_later_deposit(
    service: BankService, seeded_session_factory: sessionmaker[Session]
) -> None:
    quote = service.quote_transfer("test_user", request(950_000), datetime.now(timezone.utc))
    failed = service.submit_transfer(
        "test_user", quote.quote_id, quote.params_hash, "stable-insufficient-key"
    )
    assert failed.status == "FAILED"
    assert failed.failure_code == "INSUFFICIENT_FUNDS"

    with seeded_session_factory.begin() as session:
        account = session.scalar(
            select(Account).where(Account.id == "acc_daily").with_for_update()
        )
        account.balance_cents += 100_000

    replay = service.submit_transfer(
        "test_user", quote.quote_id, quote.params_hash, "stable-insufficient-key"
    )
    assert replay.transfer_id == failed.transfer_id
    assert replay.status == "FAILED"
    assert replay.failure_code == "INSUFFICIENT_FUNDS"
    assert service.get_balance("test_user", "acc_daily")["balance_cents"] == 1_000_000


@pytest.mark.parametrize("amount", [50_000, 950_000])
def test_bound_key_replays_after_quote_expires(
    service: BankService,
    seeded_session_factory: sessionmaker[Session],
    amount: int,
) -> None:
    quote = service.quote_transfer("test_user", request(amount), datetime.now(timezone.utc))
    first = service.submit_transfer(
        "test_user", quote.quote_id, quote.params_hash, f"expiry-replay-{amount}"
    )
    with seeded_session_factory.begin() as session:
        stored_quote = session.get(TransferQuote, quote.quote_id)
        stored_quote.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    replay = service.submit_transfer(
        "test_user", quote.quote_id, quote.params_hash, f"expiry-replay-{amount}"
    )
    assert replay.transfer_id == first.transfer_id
    assert replay.status == first.status
    assert getattr(replay, "__replayed__") is True

