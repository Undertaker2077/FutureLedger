from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from zoneinfo import ZoneInfo

from .contracts import (
    MandateResult,
    TransactionQuery,
    TransferQuote,
    TransferRequest,
    TransferResult,
)
from .domain import BankError, canonical_transfer_hash, validate_idempotency_key
from .faults import DroppedBankResponse, FaultPoint
from .models import Mandate, Transfer
from .repository import BankRepository


class BankService:
    def __init__(self, repository: BankRepository, quote_ttl_seconds: int = 300) -> None:
        self.repository = repository
        self.quote_ttl_seconds = quote_ttl_seconds

    @staticmethod
    def _iso_hong_kong(value: datetime) -> str:
        return value.astimezone(ZoneInfo("Asia/Shanghai")).isoformat()

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

    def quote_transfer(
        self, subject: str, request: TransferRequest, now: datetime
    ) -> TransferQuote:
        self.repository.get_account(subject, request.account_id)
        recipient = self.repository.get_recipient(subject, request.recipient_id)
        if not recipient.verified:
            raise BankError(
                "RECIPIENT_UNVERIFIED",
                "recipient is not verified by the bank",
                next_action="verify the recipient before retrying",
                http_status=409,
            )
        params_hash = canonical_transfer_hash(subject, request, 0)
        quote = self.repository.create_transfer_quote(
            subject, request, params_hash, now, self.quote_ttl_seconds
        )
        return TransferQuote(
            quote_id=quote.id,
            account_id=quote.account_id,
            recipient_id=quote.recipient_id,
            amount_cents=quote.amount_cents,
            fee_cents=quote.fee_cents,
            currency=quote.currency,
            reference=quote.reference,
            params_hash=quote.params_hash,
            expires_at=quote.expires_at,
        )

    @staticmethod
    def _transfer(transfer: Transfer) -> TransferResult:
        return TransferResult(
            transfer_id=transfer.id,
            status=transfer.status,
            account_id=transfer.account_id,
            recipient_id=transfer.recipient_id,
            amount_cents=transfer.amount_cents,
            fee_cents=transfer.fee_cents,
            currency=transfer.currency,
            params_hash=transfer.params_hash,
            bank_reference=transfer.bank_reference,
            failure_code=transfer.failure_code,
            created_at=transfer.created_at,
            updated_at=transfer.updated_at,
        )

    def submit_transfer(
        self,
        subject: str,
        quote_id: str,
        params_hash: str,
        idempotency_key: str | None,
        fault: FaultPoint | None = None,
    ) -> TransferResult:
        try:
            key = validate_idempotency_key(idempotency_key)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise BankError(
                "INVALID_IDEMPOTENCY_KEY",
                "a valid Idempotency-Key header is required",
                http_status=400,
            ) from exc
        transfer, replayed = self.repository.submit_transfer(
            subject, quote_id, params_hash, key, datetime.now(timezone.utc), fault
        )
        result = self._transfer(transfer)
        object.__setattr__(result, "__replayed__", replayed)
        if fault == FaultPoint.DROP_RESPONSE_AFTER_COMMIT and not replayed:
            raise DroppedBankResponse("injected dropped response after commit")
        return result

    def get_transfer_status(self, subject: str, transfer_id: str) -> TransferResult:
        return self._transfer(self.repository.get_transfer(subject, transfer_id))

    @staticmethod
    def _mandate_result(mandate: Mandate) -> MandateResult:
        return MandateResult(
            mandate_id=mandate.id,
            account_id=mandate.account_id,
            merchant_name=mandate.merchant,
            status=mandate.status,
            cancellable=mandate.can_cancel,
            cancelled_at=mandate.cancelled_at,
            updated_at=mandate.updated_at,
        )

    def cancel_mandate(
        self,
        subject: str,
        mandate_id: str,
        idempotency_key: str | None,
        now: datetime,
    ) -> MandateResult:
        try:
            key = validate_idempotency_key(idempotency_key)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise BankError(
                "INVALID_IDEMPOTENCY_KEY",
                "a valid Idempotency-Key header is required",
                http_status=400,
            ) from exc
        canonical = json.dumps(
            {"action": "cancel", "mandate_id": mandate_id, "subject": subject},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        params_hash = hashlib.sha256(canonical).hexdigest()
        mandate, result_status, replayed = self.repository.cancel_mandate(
            subject, mandate_id, key, params_hash, now
        )
        if result_status == "UNSUPPORTED":
            raise BankError(
                "UNSUPPORTED",
                "this bank mandate cannot be cancelled",
                next_action="contact the merchant or bank",
                http_status=409,
            )
        result = self._mandate_result(mandate)
        object.__setattr__(result, "__replayed__", replayed)
        return result
