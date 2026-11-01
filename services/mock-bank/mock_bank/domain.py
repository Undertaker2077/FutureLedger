from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .contracts import TransferRequest


class BankError(Exception):
    """A stable, transport-independent bank business error."""

    def __init__(
        self,
        code: str,
        message: str,
        recoverable: bool = False,
        next_action: str | None = None,
        http_status: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.recoverable = recoverable
        self.next_action = next_action
        self.http_status = http_status

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
            "next_action": self.next_action,
        }


def canonical_transfer_hash(
    subject: str, request: TransferRequest, fee_cents: int
) -> str:
    if isinstance(fee_cents, bool) or not isinstance(fee_cents, int) or fee_cents < 0:
        raise ValueError("fee_cents must be a non-negative integer")

    payload = {
        "account_id": request.account_id,
        "amount_cents": request.amount_cents,
        "currency": request.currency,
        "fee_cents": fee_cents,
        "recipient_id": request.recipient_id,
        "reference": request.reference,
        "subject": subject,
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


_IDEMPOTENCY_KEY = re.compile(r"^[!-~]{8,128}$")


def validate_idempotency_key(key: str) -> str:
    if not isinstance(key, str) or _IDEMPOTENCY_KEY.fullmatch(key) is None:
        raise ValueError(
            "idempotency key must contain 8-128 visible ASCII characters"
        )
    return key
