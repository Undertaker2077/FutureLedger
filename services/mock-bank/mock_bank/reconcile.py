from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import Settings
from .db import create_engine_from_settings


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    valid: bool
    checks: dict[str, bool]
    issues: list[str]


def reconcile(session: Session) -> ReconciliationReport:
    checks: dict[str, bool] = {}
    issues: list[str] = []

    check_queries = {
        "journal_balance": """
            SELECT NOT EXISTS (
              SELECT je.id
              FROM bank.journal_entries je
              LEFT JOIN bank.journal_lines jl ON jl.entry_id = je.id
              GROUP BY je.id
              HAVING COUNT(jl.id) <> 2 OR COALESCE(SUM(jl.signed_cents), 0) <> 0
            )
        """,
        "transfer_evidence": """
            SELECT NOT EXISTS (
              SELECT 1 FROM bank.transfers tr
              WHERE
                (tr.status = 'SUCCEEDED' AND (
                  (SELECT COUNT(*) FROM bank.transactions tx
                   WHERE tx.transfer_id = tr.id
                     AND tx.user_id = tr.user_id
                     AND tx.account_id = tr.account_id
                     AND tx.amount_cents = tr.amount_cents + tr.fee_cents
                     AND tx.direction = 'OUT'
                     AND tx.kind = 'transfer'
                     AND tx.status = 'POSTED') <> 1
                  OR (SELECT COUNT(*) FROM bank.journal_entries je
                      WHERE je.business_ref = tr.id) <> 1
                  OR (SELECT COUNT(*) FROM bank.journal_entries je
                      JOIN bank.journal_lines jl ON jl.entry_id = je.id
                      WHERE je.business_ref = tr.id) <> 2
                  OR NOT EXISTS (
                      SELECT 1 FROM bank.journal_entries je
                      JOIN bank.journal_lines jl ON jl.entry_id = je.id
                      WHERE je.business_ref = tr.id
                        AND jl.ledger_account_ref = 'account:' || tr.account_id
                        AND jl.signed_cents = -(tr.amount_cents + tr.fee_cents)
                  )
                  OR NOT EXISTS (
                      SELECT 1 FROM bank.journal_entries je
                      JOIN bank.journal_lines jl ON jl.entry_id = je.id
                      WHERE je.business_ref = tr.id
                        AND jl.ledger_account_ref = 'clearing:external'
                        AND jl.signed_cents = tr.amount_cents + tr.fee_cents
                  )
                ))
                OR (tr.status <> 'SUCCEEDED' AND (
                  EXISTS (SELECT 1 FROM bank.transactions tx WHERE tx.transfer_id = tr.id)
                  OR EXISTS (SELECT 1 FROM bank.journal_entries je WHERE je.business_ref = tr.id)
                ))
            )
        """,
        "account_derived_balance": """
            SELECT NOT EXISTS (
              SELECT 1 FROM bank.accounts a
              WHERE a.balance_cents <> a.opening_balance_cents + COALESCE((
                SELECT SUM(CASE WHEN t.direction = 'IN' THEN t.amount_cents
                                ELSE -t.amount_cents END)
                FROM bank.transactions t
                WHERE t.account_id = a.id AND t.status = 'POSTED'
              ), 0)
            )
        """,
        "idempotency_hash_uniqueness": """
            SELECT NOT EXISTS (
              SELECT user_id, idempotency_key FROM bank.transfers
              GROUP BY user_id, idempotency_key HAVING COUNT(DISTINCT params_hash) > 1
            )
        """,
        "mandate_action_agreement": """
            SELECT NOT EXISTS (
              SELECT 1 FROM bank.mandate_actions ma
              JOIN bank.mandates m ON m.user_id = ma.user_id AND m.id = ma.mandate_id
              WHERE ma.result_status = 'CANCELLED' AND m.status <> 'CANCELLED'
            )
        """,
    }
    for name, query in check_queries.items():
        passed = bool(session.execute(text(query)).scalar_one())
        checks[name] = passed
        if not passed:
            issues.append(name)
    return ReconciliationReport(valid=all(checks.values()), checks=checks, issues=issues)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile mock-bank facts")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    engine = create_engine_from_settings(Settings.from_env())
    with Session(engine) as session:
        report = reconcile(session)
    engine.dispose()
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    else:
        print(report)
    if not report.valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

