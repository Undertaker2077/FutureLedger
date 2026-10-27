from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.domain import BankError
from mock_bank.models import MandateAction
from mock_bank.repository import BankRepository
from mock_bank.service import BankService


@pytest.fixture()
def service(seeded_session_factory: sessionmaker[Session]) -> BankService:
    return BankService(BankRepository(seeded_session_factory, "test-internal-token"))


def test_mandate_list_is_user_scoped(service: BankService) -> None:
    assert len(service.list_mandates("test_user")) == 4
    assert service.list_mandates("isolation_user") == []
    with pytest.raises(BankError) as raised:
        service.get_mandate_status("isolation_user", "mandate_1")
    assert raised.value.code == "FORBIDDEN"


def test_video_mandate_cancellation_is_authoritative_and_replayable(
    service: BankService, seeded_session_factory: sessionmaker[Session]
) -> None:
    now = datetime.now(timezone.utc)
    first = service.cancel_mandate("test_user", "mandate_2", "cancel-video-key", now)
    replay = service.cancel_mandate("test_user", "mandate_2", "cancel-video-key", now)
    assert first.status == replay.status == "CANCELLED"
    assert first.cancelled_at == replay.cancelled_at
    assert service.get_mandate_status("test_user", "mandate_2")["status"] == "CANCELLED"
    with seeded_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(MandateAction)) == 1


def test_non_cancellable_fitness_stays_active_and_is_stable(
    service: BankService, seeded_session_factory: sessionmaker[Session]
) -> None:
    for _attempt in range(2):
        with pytest.raises(BankError) as raised:
            service.cancel_mandate(
                "test_user", "mandate_4", "cancel-fitness-key", datetime.now(timezone.utc)
            )
        assert raised.value.code == "UNSUPPORTED"
    assert service.get_mandate_status("test_user", "mandate_4")["status"] == "ACTIVE"
    with seeded_session_factory() as session:
        action = session.scalar(select(MandateAction))
        assert action.result_status == "UNSUPPORTED"


def test_same_key_for_different_mandate_conflicts(service: BankService) -> None:
    now = datetime.now(timezone.utc)
    service.cancel_mandate("test_user", "mandate_1", "shared-mandate-key", now)
    with pytest.raises(BankError) as raised:
        service.cancel_mandate("test_user", "mandate_3", "shared-mandate-key", now)
    assert raised.value.code == "IDEMPOTENCY_CONFLICT"


def test_two_concurrent_keys_cancel_once_and_both_observe_cancelled(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    service = BankService(BankRepository(seeded_session_factory, "test-internal-token"))
    barrier = Barrier(2)

    def cancel(index: int):
        barrier.wait()
        return service.cancel_mandate(
            "test_user",
            "mandate_3",
            f"concurrent-mandate-key-{index}",
            datetime.now(timezone.utc),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(cancel, range(2)))
    assert [result.status for result in results] == ["CANCELLED", "CANCELLED"]
    assert len({result.cancelled_at for result in results}) == 1
    with seeded_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(MandateAction)) == 2


def test_already_cancelled_mandate_never_reopens(service: BankService) -> None:
    first = service.cancel_mandate(
        "test_user", "mandate_1", "first-cancel-key", datetime.now(timezone.utc)
    )
    second = service.cancel_mandate(
        "test_user", "mandate_1", "second-cancel-key", datetime.now(timezone.utc)
    )
    assert first.status == second.status == "CANCELLED"
    assert first.cancelled_at == second.cancelled_at

