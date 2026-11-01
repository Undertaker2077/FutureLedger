"""Bridge Role B's execution gate to Role A's mock-bank adapter.

The execution gate owns confirmation, password verification, quotas and the
outbox.  This bridge only translates the final bank call to A's contract; it
does not bypass B's authorization checks.  ``recipient_user_id`` is the
recipient identifier accepted by the configured A adapter (the demo fixture
uses values such as ``rec_1``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from .service import ExecutionError


class RoleABankPort(Protocol):
    def quote_transfer(self, subject: str, request: Any, now: datetime) -> Any: ...

    def submit_transfer(
        self, subject: str, quote_id: str, params_hash: str, idempotency_key: str
    ) -> Any: ...

    def get_transfer_status(self, subject: str, transfer_id: str) -> Any: ...


class RoleABankAdapter:
    """Adapt A's quote/submit/status API to B's worker-facing bank port."""

    def __init__(self, bank: RoleABankPort, request_factory=None) -> None:
        self.bank = bank
        self.request_factory = request_factory
        self._transfer_ids: dict[str, tuple[str, str]] = {}

    @staticmethod
    def _value(value: Any, name: str) -> Any:
        if isinstance(value, dict):
            return value[name]
        return getattr(value, name)

    @staticmethod
    def _error(exc: Exception) -> ExecutionError:
        code = str(getattr(exc, "code", "UPSTREAM_UNAVAILABLE"))
        status = "FAILED" if code in {"INSUFFICIENT_FUNDS", "RECIPIENT_NOT_FOUND"} else None
        return ExecutionError(code, str(exc), status=status)

    def submit_transfer(
        self,
        *,
        operation_id: str,
        user_id: str,
        account_id: str,
        recipient_user_id: str,
        amount_cents: int,
        idempotency_key: str,
    ) -> str:
        del operation_id
        try:
            from mock_bank.contracts import TransferRequest
        except ModuleNotFoundError:
            TransferRequest = None  # type: ignore[assignment]
        try:
            payload = {
                "account_id": account_id,
                "recipient_id": recipient_user_id,
                "amount_cents": amount_cents,
                "currency": "CNY",
            }
            request = (
                self.request_factory(**payload)
                if self.request_factory is not None
                else TransferRequest(
                    account_id=account_id,
                    recipient_id=recipient_user_id,
                    amount_cents=amount_cents,
                    currency="CNY",
                )
                if TransferRequest is not None
                else payload
            )
            quote = self.bank.quote_transfer(user_id, request, datetime.now(timezone.utc))
            result = self.bank.submit_transfer(
                user_id,
                self._value(quote, "quote_id"),
                self._value(quote, "params_hash"),
                idempotency_key,
            )
            transfer_id = str(self._value(result, "transfer_id"))
            self._transfer_ids[idempotency_key] = (user_id, transfer_id)
            status = str(self._value(result, "status"))
            if status == "FAILED":
                raise ExecutionError(
                    str(self._value(result, "failure_code") or "BANK_FAILED"),
                    "Role A rejected the transfer.",
                    status="FAILED",
                )
            return str(self._value(result, "bank_reference") or transfer_id)
        except ExecutionError:
            raise
        except Exception as exc:  # translate A's stable error contract to B
            raise self._error(exc) from exc

    def get_transfer_status(self, *, operation_id: str, idempotency_key: str) -> str:
        del operation_id
        stored = self._transfer_ids.get(idempotency_key)
        if stored is None:
            return "NOT_FOUND"
        subject, transfer_id = stored
        try:
            result = self.bank.get_transfer_status(subject, transfer_id)
        except Exception as exc:
            raise self._error(exc) from exc
        return str(self._value(result, "status"))
