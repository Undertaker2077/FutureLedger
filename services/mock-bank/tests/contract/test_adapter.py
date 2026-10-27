from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.adapter import HttpBankAdapter, ServiceBankAdapter
from mock_bank.api import create_app
from mock_bank.config import Settings
from mock_bank.contracts import TransactionQuery, TransferRequest
from mock_bank.domain import BankError
from mock_bank.repository import BankRepository
from mock_bank.service import BankService


@pytest.fixture(params=["service", "http"])
def adapter(
    request: pytest.FixtureRequest,
    bank_settings: Settings,
    seeded_session_factory: sessionmaker[Session],
):
    service = BankService(BankRepository(seeded_session_factory, "test-internal-token"))
    if request.param == "service":
        yield ServiceBankAdapter(service)
        return
    with TestClient(create_app(bank_settings, seeded_session_factory)) as client:
        yield HttpBankAdapter(
            "http://testserver", bank_settings.service_token, client=client
        )


def transfer_request() -> TransferRequest:
    return TransferRequest(
        account_id="acc_daily",
        recipient_id="rec_1",
        amount_cents=50_000,
        currency="CNY",
    )


def test_adapter_read_and_transfer_contract(adapter) -> None:
    assert adapter.get_balance("test_user", "acc_daily")["balance_cents"] == 900_000
    assert adapter.list_transactions(
        "test_user", TransactionQuery(account_id="acc_daily", limit=2)
    )["items"]
    assert adapter.resolve_recipient("test_user", "rec_1")["verified"] is True
    quote = adapter.quote_transfer("test_user", transfer_request(), datetime.now(timezone.utc))
    transfer = adapter.submit_transfer(
        "test_user", quote.quote_id, quote.params_hash, "adapter-transfer-key"
    )
    assert transfer.status == "SUCCEEDED"
    assert adapter.get_transfer_status("test_user", transfer.transfer_id) == transfer


def test_adapter_mandate_contract_and_error_codes(adapter) -> None:
    assert len(adapter.list_mandates("test_user")) == 4
    cancelled = adapter.cancel_mandate(
        "test_user", "mandate_2", "adapter-cancel-key", datetime.now(timezone.utc)
    )
    assert cancelled.status == "CANCELLED"
    assert adapter.get_mandate_status("test_user", "mandate_2")["status"] == "CANCELLED"
    with pytest.raises(BankError) as raised:
        adapter.get_balance("test_user", "acc_other")
    assert raised.value.code in {"FORBIDDEN", "NOT_FOUND"}

