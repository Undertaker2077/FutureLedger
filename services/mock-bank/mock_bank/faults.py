from __future__ import annotations

from enum import Enum


class FaultPoint(str, Enum):
    BEFORE_COMMIT = "before_commit"
    DROP_RESPONSE_AFTER_COMMIT = "drop_response_after_commit"
    TEMPORARY_UNAVAILABLE = "temporary_unavailable"


class InjectedBankFault(RuntimeError):
    pass


class DroppedBankResponse(RuntimeError):
    pass
