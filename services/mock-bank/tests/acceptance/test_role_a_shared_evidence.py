from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from mock_bank.acceptance import run_role_a_acceptance
from mock_bank.adapter import RecordingBankAdapter, ServiceBankAdapter
from mock_bank.config import Settings
from mock_bank.contracts import TransferRequest
from mock_bank.repository import BankRepository
from mock_bank.service import BankService


ZERO_CALL_CASES = {
    "transfer_02",
    "transfer_03",
    "transfer_08",
    "transfer_10",
    "mandate_01",
    "mandate_04",
    "mandate_05",
    "mandate_10",
}


def test_recording_adapter_snapshots_are_immutable_and_redacted(
    seeded_session_factory: sessionmaker[Session],
) -> None:
    service = BankService(BankRepository(seeded_session_factory, "secret-token-never-record"))
    recorder = RecordingBankAdapter(ServiceBankAdapter(service))
    before = recorder.snapshot()
    assert before.calls == ()

    quote = recorder.quote_transfer(
        "test_user",
        TransferRequest(
            account_id="acc_daily",
            recipient_id="rec_1",
            amount_cents=50_000,
            currency="CNY",
        ),
        datetime.now(timezone.utc),
    )
    recorder.submit_transfer(
        "test_user", quote.quote_id, quote.params_hash, "recording-key"
    )
    after = recorder.snapshot()
    assert len(after.calls) == 2
    assert "secret-token-never-record" not in after.model_dump_json()
    assert before.calls == ()


def test_shared_cases_have_a_side_evidence_and_named_prerequisites(
    bank_settings: Settings, fixture_root: Path
) -> None:
    catalog = fixture_root.parent / "benchmark" / "acceptance_cases.json"
    report = run_role_a_acceptance(bank_settings, fixture_root, catalog)
    shared = {case.case_id: case for case in report.cases if case.status == "A_SIDE_PASS"}
    assert ZERO_CALL_CASES <= shared.keys()
    assert {"transfer_07", "transfer_09", "mandate_07"} <= shared.keys()
    for case in shared.values():
        assert case.remaining_prerequisite
        assert case.evidence
    for case_id in ZERO_CALL_CASES:
        assert shared[case_id].evidence["adapter_call_count"] == 0
    assert shared["transfer_07"].evidence["submit_call_count"] == 1
    assert shared["transfer_09"].evidence["status_after"] == "SUCCEEDED"
    assert shared["mandate_07"].evidence["matching_mandate"] is False
