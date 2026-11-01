from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import delete
from sqlalchemy.orm import Session

from .config import Settings
from .db import create_engine_from_settings
from .models import (
    Account,
    JournalEntry,
    JournalLine,
    Mandate,
    MandateAction,
    Recipient,
    Transaction,
    Transfer,
    TransferQuote,
    User,
)


@dataclass(frozen=True, slots=True)
class SeedReport:
    users: int
    accounts: int
    recipients: int
    mandates: int
    transactions: int


def _read_json(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, list):
        raise ValueError(f"expected a JSON list in {path}")
    return value


def _run_migrations(settings: Settings) -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")


def reset_database(settings: Settings, fixture_root: Path) -> SeedReport:
    if settings.environment not in {"test", "development"}:
        raise RuntimeError("database reset refused outside test/development")
    if os.environ.get("FUTURELEDGER_ALLOW_RESET") != "1":
        raise RuntimeError("database reset refused without FUTURELEDGER_ALLOW_RESET=1")

    _run_migrations(settings)
    users = _read_json(fixture_root / "users.json")
    accounts = _read_json(fixture_root / "accounts.json")
    recipients = _read_json(fixture_root / "recipients.json")
    mandates = _read_json(fixture_root / "mandates.json")
    manifest = json.loads((fixture_root / "manifest.json").read_text(encoding="utf-8"))
    as_of = datetime.fromisoformat(str(manifest["as_of"]))

    engine = create_engine_from_settings(settings)
    with Session(engine) as session, session.begin():
        for model in (
            MandateAction,
            JournalLine,
            JournalEntry,
            Transaction,
            Transfer,
            TransferQuote,
            Mandate,
            Recipient,
            Account,
            User,
        ):
            session.execute(delete(model))

        session.add_all(
            User(
                id=str(row["id"]),
                username=str(row["username"]),
                password_hash="!seed-login-disabled!",
                role="customer",
            )
            for row in users
        )
        session.flush()
        session.add_all(
            Account(
                id=str(row["id"]),
                user_id=str(row["user_id"]),
                tail4=str(row["tail4"]),
                currency=str(row["currency"]),
                opening_balance_cents=int(row["opening_balance_cents"]),
                balance_cents=int(row["balance_cents"]),
                as_of=datetime.fromisoformat(str(row["as_of"])),
            )
            for row in accounts
        )
        session.flush()
        session.add_all(
            Recipient(
                id=str(row["id"]),
                user_id=str(row["user_id"]),
                name=str(row["name"]),
                alias=None if row.get("alias") is None else str(row["alias"]),
                bank_ref=str(row["bank_ref"]),
                tail4=str(row["tail4"]),
                verified=bool(row["verified"]),
            )
            for row in recipients
        )
        session.flush()
        session.add_all(
            Mandate(
                id=str(row["id"]),
                user_id=str(row["user_id"]),
                account_id=str(row["account_id"]),
                merchant=str(row["merchant"]),
                amount_cents=int(row["amount_cents"]),
                period=str(row["period"]),
                next_due=date.fromisoformat(str(row["next_due"]))
                if row.get("next_due")
                else None,
                status=str(row["status"]),
                can_cancel=bool(row["can_cancel"]),
                as_of=as_of,
            )
            for row in mandates
        )
        session.flush()

        transaction_count = 0
        with (fixture_root / "transactions.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            batch: list[Transaction] = []
            for row in csv.DictReader(handle):
                batch.append(
                    Transaction(
                        id=row["id"],
                        external_id=row["external_id"],
                        user_id=row["user_id"],
                        account_id=row["account_id"],
                        amount_cents=int(row["amount_cents"]),
                        direction=row["direction"],
                        kind=row["kind"],
                        status=row["status"],
                        category=row["category"],
                        merchant=row["merchant"],
                        posted_at=datetime.fromisoformat(row["posted_at"]),
                        refund_of=row["refund_of"] or None,
                        memo=row["memo"],
                    )
                )
                transaction_count += 1
                if len(batch) == 500:
                    session.add_all(batch)
                    session.flush()
                    batch.clear()
            session.add_all(batch)

    engine.dispose()
    return SeedReport(
        users=len(users),
        accounts=len(accounts),
        recipients=len(recipients),
        mandates=len(mandates),
        transactions=transaction_count,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the mock-bank fixture")
    parser.add_argument("command", choices=["reset"])
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "data",
    )
    args = parser.parse_args()
    if args.command == "reset":
        print(reset_database(Settings.from_env(), args.fixture_root))


if __name__ == "__main__":
    main()
