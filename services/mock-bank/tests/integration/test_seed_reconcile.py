from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from mock_bank.config import Settings
from mock_bank.contracts import TransferRequest
from mock_bank.models import Account, Mandate, Recipient, Transaction
from mock_bank.reconcile import reconcile
from mock_bank.repository import BankRepository
from mock_bank.seed import reset_database
from mock_bank.service import BankService


def test_reset_is_refused_outside_test_or_development(
    bank_settings: Settings, fixture_root: Path
) -> None:
    with pytest.raises(RuntimeError, match="refused"):
        reset_database(replace(bank_settings, environment="production"), fixture_root)


def test_reset_loads_the_deterministic_bank_fixture(
    bank_settings: Settings, fixture_root: Path, bank_session: Session
) -> None:
    report = reset_database(bank_settings, fixture_root)
    bank_session.expire_all()

    assert report.accounts == 3
    assert report.recipients == 5
    assert report.mandates == 4
    assert report.transactions == 3_839
    assert bank_session.scalar(select(func.count()).select_from(Account)) == 3
    assert bank_session.scalar(select(func.count()).select_from(Recipient)) == 5
    assert bank_session.scalar(select(func.count()).select_from(Mandate)) == 4
    assert bank_session.scalar(select(func.count()).select_from(Transaction)) == 3_839
    assert bank_session.get(Account, "acc_daily").balance_cents == 900_000


def test_fresh_reset_reconciles_cleanly(
    bank_settings: Settings, fixture_root: Path, bank_session: Session
) -> None:
    reset_database(bank_settings, fixture_root)
    bank_session.expire_all()

    report = reconcile(bank_session)

    assert report.valid is True
    assert report.issues == []
    assert report.checks["journal_balance"] is True
    assert report.checks["transfer_evidence"] is True
    assert report.checks["account_derived_balance"] is True
    assert report.checks["idempotency_hash_uniqueness"] is True
    assert report.checks["mandate_action_agreement"] is True


def test_migration_creates_least_privilege_roles(bank_session: Session) -> None:
    roles = set(
        bank_session.scalars(
            text(
                "SELECT rolname FROM pg_roles "
                "WHERE rolname IN ('futureledger_bank_runtime', 'futureledger_bank_read')"
            )
        )
    )
    assert roles == {"futureledger_bank_runtime", "futureledger_bank_read"}


def test_deferred_trigger_rejects_unbalanced_journal(bank_session: Session) -> None:
    bank_session.execute(
        text(
            "INSERT INTO bank.journal_entries(id, business_ref) "
            "VALUES ('je_unbalanced_test', 'unbalanced-test')"
        )
    )
    bank_session.execute(
        text(
            "INSERT INTO bank.journal_lines(id, entry_id, ledger_account_ref, signed_cents) "
            "VALUES ('jl_unbalanced_test', 'je_unbalanced_test', 'account:test', -500)"
        )
    )

    with pytest.raises(ProgrammingError, match="not balanced"):
        bank_session.commit()


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO bank.transfer_quotes(id,user_id,account_id,recipient_id,amount_cents,fee_cents,currency,params_hash,expires_at) VALUES ('bad_quote','test_user','acc_daily','rec_1',1,0,'USD',repeat('a',64),now())",
        "INSERT INTO bank.transactions(id,user_id,account_id,external_id,amount_cents,direction,kind,status,category,merchant,posted_at) VALUES ('bad_tx','test_user','acc_daily','bad_tx',1,'OUT','unknown','POSTED','x','x',now())",
    ],
)
def test_database_rejects_invalid_currency_and_transaction_kind(
    bank_settings: Settings, fixture_root: Path, bank_session: Session, statement: str
) -> None:
    reset_database(bank_settings, fixture_root)
    with pytest.raises(Exception):
        bank_session.execute(text(statement))
        bank_session.commit()


def test_reconcile_detects_orphan_journal(
    bank_settings: Settings, fixture_root: Path, bank_session: Session
) -> None:
    reset_database(bank_settings, fixture_root)
    bank_session.execute(
        text(
            "INSERT INTO bank.journal_entries(id,business_ref) "
            "VALUES ('orphan_entry','orphan-business')"
        )
    )
    bank_session.commit()
    report = reconcile(bank_session)
    assert report.valid is False
    assert report.checks["journal_balance"] is False


def test_reconcile_detects_semantically_corrupt_transfer_evidence(
    bank_settings: Settings, fixture_root: Path, seeded_session_factory
) -> None:
    reset_database(bank_settings, fixture_root)
    service = BankService(
        BankRepository(seeded_session_factory, "test-internal-token")
    )
    quote = service.quote_transfer(
        "test_user",
        TransferRequest(
            account_id="acc_daily",
            recipient_id="rec_1",
            amount_cents=50_000,
            currency="CNY",
            reference="reconciliation corruption probe",
        ),
        datetime.now(timezone.utc),
    )
    transfer = service.submit_transfer(
        "test_user", quote.quote_id, quote.params_hash, "reconcile-corrupt-transfer"
    )
    with seeded_session_factory.begin() as session:
        transaction = session.scalar(
            select(Transaction).where(Transaction.transfer_id == transfer.transfer_id)
        )
        assert transaction is not None
        transaction.direction = "IN"

    with seeded_session_factory() as session:
        report = reconcile(session)
    assert report.valid is False
    assert report.checks["transfer_evidence"] is False


def test_runtime_login_cannot_modify_app_schema(
    bank_settings: Settings, fixture_root: Path
) -> None:
    reset_database(bank_settings, fixture_root)
    runtime_url = (
        "postgresql+psycopg://futureledger_runtime:futureledger-runtime@"
        "localhost:55432/futureledger_bank"
    )
    engine = create_engine(runtime_url)
    with Session(engine) as session:
        assert session.scalar(text("SELECT count(*) FROM bank.accounts")) == 3
        with pytest.raises(Exception):
            session.execute(
                text(
                    "UPDATE app.users SET role='admin' WHERE id='test_user'"
                )
            )
            session.commit()
    engine.dispose()


def test_postgresql_18_6_is_running(bank_session: Session) -> None:
    version = str(bank_session.scalar(text("SHOW server_version")))
    assert version.startswith("18.6")
