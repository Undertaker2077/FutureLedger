from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.contracts import TransferRequest
from mock_bank.models import JournalEntry, Transaction, Transfer
from mock_bank.repository import BankRepository
from mock_bank.service import BankService


def make_service(factory: sessionmaker[Session]) -> BankService:
    return BankService(BankRepository(factory, "test-internal-token"))


def quote(service: BankService, amount: int):
    return service.quote_transfer(
        "test_user",
        TransferRequest(
            account_id="acc_daily",
            recipient_id="rec_1",
            amount_cents=amount,
            currency="CNY",
        ),
        datetime.now(timezone.utc),
    )


def test_simultaneous_identical_key_debits_once(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    service = make_service(seeded_session_factory)
    transfer_quote = quote(service, 50_000)
    barrier = Barrier(2)

    def submit():
        barrier.wait()
        return service.submit_transfer(
            "test_user", transfer_quote.quote_id, transfer_quote.params_hash, "concurrent-same-key"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: submit(), range(2)))

    assert len({result.transfer_id for result in results}) == 1
    assert sorted(getattr(result, "__replayed__") for result in results) == [False, True]
    assert service.get_balance("test_user", "acc_daily")["balance_cents"] == 850_000


def test_competing_keys_cannot_overdraw_and_evidence_is_one_to_one(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    service = make_service(seeded_session_factory)
    quotes = [quote(service, 600_000), quote(service, 600_000)]
    barrier = Barrier(2)

    def submit(index: int):
        barrier.wait()
        item = quotes[index]
        return service.submit_transfer(
            "test_user", item.quote_id, item.params_hash, f"competing-key-{index}"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))

    assert sorted(result.status for result in results) == ["FAILED", "SUCCEEDED"]
    assert service.get_balance("test_user", "acc_daily")["balance_cents"] == 300_000
    with seeded_session_factory() as session:
        succeeded = session.scalar(
            select(func.count()).select_from(Transfer).where(Transfer.status == "SUCCEEDED")
        )
        assert succeeded == 1
        assert session.scalar(select(func.count()).select_from(JournalEntry)) == succeeded
        assert session.scalar(
            select(func.count()).select_from(Transaction).where(
                Transaction.transfer_id.is_not(None)
            )
        ) == succeeded
