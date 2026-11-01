from __future__ import annotations

import hmac

from fastapi import Header

from .config import Settings
from .domain import BankError


def authenticate(
    settings: Settings,
    authorization: str | None,
    subject: str | None,
) -> str:
    expected = f"Bearer {settings.service_token}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise BankError(
            "UNAUTHENTICATED",
            "valid internal service token is required",
            http_status=401,
        )
    if subject is None or not subject.strip():
        raise BankError(
            "UNAUTHENTICATED", "authenticated subject is required", http_status=401
        )
    return subject

