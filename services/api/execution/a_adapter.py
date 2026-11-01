"""Bridge Role B's execution gate to Role A's mock-bank adapter.

The execution gate owns confirmation, password verification, quotas and the
outbox.  This bridge only translates the final bank call to A's contract; it
does not bypass B's authorization checks.  ``recipient_user_id`` is the
recipient identifier accepted by the configured A adapter (the demo fixture
uses values such as ``rec_1``).
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Protocol

from .service import ExecutionError, UnknownBankResult


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
        self._owned_store = sqlite3.connect(':memory:', check_same_thread=False)
        self.attach_store(self._owned_store)

    def attach_store(self, connection):
        """Retain subject/key bindings with B, before any possible bank commit."""
        self.db = connection
        self.db.execute('''CREATE TABLE IF NOT EXISTS bank_transfer_bindings (
            operation_id TEXT PRIMARY KEY, subject TEXT NOT NULL, idempotency_key TEXT NOT NULL,
            params_hash TEXT NOT NULL, transfer_id TEXT, bank_ref TEXT)''')
        self.db.commit()

    def _binding(self, operation_id, idempotency_key):
        row = self.db.execute('SELECT subject,transfer_id,bank_ref FROM bank_transfer_bindings WHERE operation_id=? AND idempotency_key=?',
                              (operation_id, idempotency_key)).fetchone()
        return tuple(row) if row else None

    def get_bank_reference(self, *, operation_id, idempotency_key):
        stored = self._binding(operation_id, idempotency_key)
        return stored[2] if stored else None

    def _remember(self, operation_id, result):
        self.db.execute('UPDATE bank_transfer_bindings SET transfer_id=?,bank_ref=? WHERE operation_id=?',
                        (str(self._value(result, 'transfer_id')), self._value(result, 'bank_reference'), operation_id))
        self.db.commit()

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
        canonical = hashlib.sha256(json.dumps([user_id, account_id, recipient_user_id, amount_cents],
                                              separators=(',', ':')).encode()).hexdigest()
        existing = self.db.execute('SELECT subject,idempotency_key,params_hash FROM bank_transfer_bindings WHERE operation_id=?', (operation_id,)).fetchone()
        if existing and tuple(existing) != (user_id, idempotency_key, canonical):
            raise ExecutionError('IDEMPOTENCY_CONFLICT', '操作参数与原银行提交不一致。', status='FAILED')
        self.db.execute('INSERT OR IGNORE INTO bank_transfer_bindings(operation_id,subject,idempotency_key,params_hash) VALUES(?,?,?,?)',
                        (operation_id, user_id, idempotency_key, canonical))
        self.db.commit()
        submitted = False
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
            submitted = True
            result = self.bank.submit_transfer(
                user_id,
                self._value(quote, "quote_id"),
                self._value(quote, "params_hash"),
                idempotency_key,
            )
            transfer_id = str(self._value(result, "transfer_id"))
            self._remember(operation_id, result)
            status = str(self._value(result, "status"))
            if status == "FAILED":
                raise ExecutionError(
                    str(self._value(result, "failure_code") or "BANK_FAILED"),
                    "Role A rejected the transfer.",
                    status="FAILED",
                )
            if status != 'SUCCEEDED':
                raise UnknownBankResult('银行尚未确认最终结果。')
            return str(self._value(result, "bank_reference") or transfer_id)
        except ExecutionError:
            raise
        except UnknownBankResult:
            raise
        except Exception as exc:  # translate A's stable error contract to B
            if submitted:
                raise UnknownBankResult('银行提交结果未确认，请按原幂等键查证。') from exc
            raise self._error(exc) from exc

    def get_transfer_status(self, *, operation_id: str, idempotency_key: str) -> str:
        stored = self._binding(operation_id, idempotency_key)
        if stored is None:
            return "NOT_FOUND"
        subject, transfer_id, _ = stored
        try:
            if transfer_id:
                result = self.bank.get_transfer_status(subject, transfer_id)
            elif hasattr(self.bank, 'get_transfer_by_key'):
                result = self.bank.get_transfer_by_key(subject, idempotency_key)
            else:
                return 'PENDING_UNKNOWN'
            if not transfer_id:
                self._remember(operation_id, result)
        except Exception as exc:
            if getattr(exc, 'code', None) == 'NOT_FOUND':
                return 'NOT_FOUND'
            return 'PENDING_UNKNOWN'
        return str(self._value(result, "status"))
