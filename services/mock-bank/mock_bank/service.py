from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .contracts import TransactionQuery
from .domain import BankError
from .models import Mandate
from .repository import BankRepository


class BankService:
    def __init__(self, repository: BankRepository) -> None:
        self.repository = repository

    @staticmethod
    def _iso_hong_kong(value: datetime) -> str:
        return value.astimezone(ZoneInfo("Asia/Hong_Kong")).isoformat()

    def get_balance(self, subject: str, account_id: str) -> dict[str, object]:
        account = self.repository.get_account(subject, account_id)
        return {
            "account_id": account.id,
            "balance_cents": account.balance_cents,
            "currency": account.currency,
            "as_of": self._iso_hong_kong(account.as_of),
        }

    def resolve_recipient(self, subject: str, recipient_id: str) -> dict[str, object]:
        recipient = self.repository.get_recipient(subject, recipient_id)
        return {
            "recipient_id": recipient.id,
            "name": recipient.name,
            "alias": recipient.alias,
            "bank_ref": recipient.bank_ref,
            "tail4": recipient.tail4,
            "verified": recipient.verified,
        }

    def list_transactions(
        self, subject: str, query: TransactionQuery
    ) -> dict[str, object]:
        if query.start is not None and query.end_exclusive is not None:
            if query.start >= query.end_exclusive:
                raise BankError(
                    "INVALID_QUERY", "start must be before end_exclusive", http_status=400
                )
        if query.kind is not None and query.kind not in {
            "expense",
            "refund",
            "income",
            "transfer",
        }:
            raise BankError("INVALID_QUERY", "unknown transaction kind", http_status=400)
        if query.status is not None and query.status not in {"POSTED", "PENDING", "FAILED"}:
            raise BankError("INVALID_QUERY", "unknown transaction status", http_status=400)

        rows, next_cursor = self.repository.list_transactions(subject, query)
        items = [
            {
                "transaction_id": transaction.id,
                "account_id": transaction.account_id,
                "amount_cents": transaction.amount_cents,
                "currency": currency,
                "direction": transaction.direction,
                "kind": transaction.kind,
                "status": transaction.status,
                "category": transaction.category,
                "merchant": transaction.merchant,
                "posted_at": transaction.posted_at.isoformat(),
                "refund_of": transaction.refund_of,
            }
            for transaction, currency in rows
        ]
        return {"items": items, "next_cursor": next_cursor}

    @staticmethod
    def _mandate(mandate: Mandate) -> dict[str, object]:
        return {
            "mandate_id": mandate.id,
            "account_id": mandate.account_id,
            "merchant_name": mandate.merchant,
            "amount_cents": mandate.amount_cents,
            "period": mandate.period,
            "next_due": mandate.next_due.isoformat() if mandate.next_due else None,
            "status": mandate.status,
            "cancellable": mandate.can_cancel,
            "cancelled_at": mandate.cancelled_at.isoformat()
            if mandate.cancelled_at
            else None,
            "updated_at": mandate.updated_at.isoformat(),
        }

    def list_mandates(
        self, subject: str, account_id: str | None = None
    ) -> list[dict[str, object]]:
        return [
            self._mandate(mandate)
            for mandate in self.repository.list_mandates(subject, account_id)
        ]

    def get_mandate_status(self, subject: str, mandate_id: str) -> dict[str, object]:
        return self._mandate(self.repository.get_mandate(subject, mandate_id))

