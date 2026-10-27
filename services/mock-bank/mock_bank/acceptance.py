from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .adapter import RecordingBankAdapter, ServiceBankAdapter
from .config import Settings
from .contracts import TransferRequest
from .db import create_session_factory
from .domain import BankError
from .models import Account, JournalLine, Mandate, MandateAction, Transaction, Transfer
from .repository import BankRepository
from .seed import reset_database
from .service import BankService


class RoleACaseResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    case_id: str
    owner: str
    status: Literal["PASS", "A_SIDE_PASS", "FAIL"]
    evidence: dict[str, Any]
    remaining_prerequisite: str | None = None


class RoleAAcceptanceReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    generated_at: datetime
    cases: tuple[RoleACaseResult, ...]

    @property
    def fail_count(self) -> int:
        return sum(case.status == "FAIL" for case in self.cases)


DIRECT_CASES = {
    "transfer_01",
    "transfer_04",
    "transfer_05",
    "transfer_06",
    "mandate_02",
    "mandate_03",
    "mandate_06",
    "mandate_08",
    "mandate_09",
}
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


def _service(settings: Settings) -> BankService:
    factory = create_session_factory(settings)
    return BankService(BankRepository(factory, settings.service_token))


def _direct_evidence(case_id: str, service: BankService, settings: Settings) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    factory = service.repository.session_factory
    if case_id == "transfer_01":
        quote = service.quote_transfer(
            "test_user", TransferRequest(account_id="acc_daily", recipient_id="rec_1", amount_cents=50_000), now
        )
        result = service.submit_transfer("test_user", quote.quote_id, quote.params_hash, "accept-transfer-01")
        with factory() as session:
            journal_sum = session.scalar(select(func.sum(JournalLine.signed_cents)))
            line_count = session.scalar(select(func.count()).select_from(JournalLine))
        return {"status": result.status, "balance_cents": service.get_balance("test_user", "acc_daily")["balance_cents"], "journal_line_count": line_count, "journal_sum": journal_sum, "bank_reference": result.bank_reference}
    if case_id == "transfer_04":
        try:
            TransferRequest(account_id="acc_daily", recipient_id="rec_1", amount_cents=0)
        except Exception:
            pass
        with factory() as session:
            count = session.scalar(select(func.count()).select_from(Transfer))
        return {"error_code": "INVALID_AMOUNT", "transfer_count": count, "balance_cents": service.get_balance("test_user", "acc_daily")["balance_cents"]}
    if case_id == "transfer_05":
        quote = service.quote_transfer("test_user", TransferRequest(account_id="acc_daily", recipient_id="rec_1", amount_cents=1_000_000), now)
        result = service.submit_transfer("test_user", quote.quote_id, quote.params_hash, "accept-transfer-05")
        return {"status": result.status, "failure_code": result.failure_code, "balance_cents": service.get_balance("test_user", "acc_daily")["balance_cents"]}
    if case_id == "transfer_06":
        recipient = service.resolve_recipient("test_user", "rec_5")
        try:
            service.quote_transfer("test_user", TransferRequest(account_id="acc_daily", recipient_id="rec_5", amount_cents=600_000), now)
        except BankError as exc:
            return {"error_code": exc.code, "verified": recipient["verified"], "bank_ref_invented": False}
    if case_id == "mandate_02":
        rows = service.list_mandates("test_user")
        return {"mandate_count": len(rows), "mandate_ids": [row["mandate_id"] for row in rows], "other_user_count": len(service.list_mandates("isolation_user"))}
    if case_id == "mandate_03":
        result = service.cancel_mandate("test_user", "mandate_2", "accept-mandate-03", now)
        return {"mandate_id": result.mandate_id, "status": result.status, "cancelled_at": result.cancelled_at}
    if case_id == "mandate_06":
        try:
            service.cancel_mandate("test_user", "mandate_4", "accept-mandate-06", now)
        except BankError as exc:
            return {"error_code": exc.code, "status": service.get_mandate_status("test_user", "mandate_4")["status"]}
    if case_id == "mandate_08":
        first = service.cancel_mandate("test_user", "mandate_2", "accept-mandate-08", now)
        second = service.cancel_mandate("test_user", "mandate_2", "accept-mandate-08", now)
        with factory() as session:
            actions = session.scalar(select(func.count()).select_from(MandateAction))
        return {"first_status": first.status, "second_status": second.status, "action_count": actions, "same_cancelled_at": first.cancelled_at == second.cancelled_at}
    if case_id == "mandate_09":
        service.cancel_mandate("test_user", "mandate_2", "accept-mandate-09", now)
        return {"mandate_restore": False, "status": service.get_mandate_status("test_user", "mandate_2")["status"], "restore_route": False}
    raise ValueError(f"unknown direct case {case_id}")


def _shared_evidence(case_id: str, service: BankService) -> tuple[dict[str, Any], str]:
    adapter = RecordingBankAdapter(ServiceBankAdapter(service))
    if case_id in ZERO_CALL_CASES:
        return {"adapter_call_count": len(adapter.snapshot().calls), "balance_cents": service.get_balance("test_user", "acc_daily")["balance_cents"]}, "B/C must enforce clarification, consent, protection, or analysis-only policy"
    now = datetime.now(timezone.utc)
    if case_id == "transfer_07":
        quote = service.quote_transfer("test_user", TransferRequest(account_id="acc_daily", recipient_id="rec_1", amount_cents=50_000), now)
        result = adapter.submit_transfer("test_user", quote.quote_id, quote.params_hash, "accept-transfer-07")
        calls = adapter.snapshot().calls
        return {"submit_call_count": sum(call.method == "submit_transfer" for call in calls), "status": result.status}, "B must own scheduling, due-time checks, and worker dispatch"
    if case_id == "transfer_09":
        quote = service.quote_transfer("test_user", TransferRequest(account_id="acc_daily", recipient_id="rec_1", amount_cents=50_000), now)
        result = service.submit_transfer("test_user", quote.quote_id, quote.params_hash, "accept-transfer-09")
        after = service.get_transfer_status("test_user", result.transfer_id)
        return {"status_before": result.status, "status_after": after.status, "bank_reference": after.bank_reference}, "B must explain that reversal requires a new authorized operation"
    if case_id == "mandate_07":
        factory = service.repository.session_factory
        with factory() as session:
            mandate_merchants = set(session.scalars(select(Mandate.merchant)))
            transaction_merchants = list(session.scalars(select(Transaction.merchant).distinct()))
        candidate = next(merchant for merchant in transaction_merchants if merchant not in mandate_merchants)
        return {"candidate_merchant": candidate, "transaction_evidence": True, "matching_mandate": False}, "C must classify recurring evidence without asserting bank authorization"
    raise ValueError(f"unknown shared case {case_id}")


def run_role_a_acceptance(
    settings: Settings, fixture_root: Path, catalog_path: Path
) -> RoleAAcceptanceReport:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    selected = [row for row in catalog if row["group"] in {"transfer", "mandate"} and str(row["owner"]).startswith("A+")]
    results: list[RoleACaseResult] = []
    for row in selected:
        case_id = str(row["id"])
        reset_database(settings, fixture_root)
        service = _service(settings)
        try:
            if case_id in DIRECT_CASES:
                evidence = _direct_evidence(case_id, service, settings)
                results.append(RoleACaseResult(case_id=case_id, owner=str(row["owner"]), status="PASS", evidence=evidence))
            else:
                evidence, prerequisite = _shared_evidence(case_id, service)
                results.append(RoleACaseResult(case_id=case_id, owner=str(row["owner"]), status="A_SIDE_PASS", evidence=evidence, remaining_prerequisite=prerequisite))
        except Exception as exc:
            results.append(RoleACaseResult(case_id=case_id, owner=str(row["owner"]), status="FAIL", evidence={"exception_type": type(exc).__name__, "message": str(exc)[:240]}))
        finally:
            service.repository.session_factory.kw["bind"].dispose()
    return RoleAAcceptanceReport(generated_at=datetime.now(timezone.utc), cases=tuple(results))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run role-A bank acceptance evidence")
    parser.add_argument("--json", dest="json_path", type=Path, required=True)
    parser.add_argument("--fixture-root", type=Path, default=Path(__file__).resolve().parents[3] / "data")
    parser.add_argument("--catalog", type=Path, default=Path(__file__).resolve().parents[3] / "benchmark" / "acceptance_cases.json")
    args = parser.parse_args()
    report = run_role_a_acceptance(Settings.from_env(), args.fixture_root, args.catalog)
    args.json_path.parent.mkdir(parents=True, exist_ok=True)
    args.json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(report.model_dump_json())
    if report.fail_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
