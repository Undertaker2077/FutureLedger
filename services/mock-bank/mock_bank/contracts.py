from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TransferRequest(StrictContract):
    account_id: StrictStr = Field(min_length=1)
    recipient_id: StrictStr = Field(min_length=1)
    amount_cents: StrictInt = Field(gt=0)
    currency: Literal["CNY"] = "CNY"
    reference: StrictStr | None = Field(default=None, max_length=140)


class TransferQuote(StrictContract):
    quote_id: StrictStr
    account_id: StrictStr
    recipient_id: StrictStr
    amount_cents: StrictInt = Field(gt=0)
    fee_cents: StrictInt = Field(ge=0)
    currency: Literal["CNY"] = "CNY"
    reference: StrictStr | None = None
    params_hash: StrictStr
    expires_at: datetime


class TransferResult(StrictContract):
    transfer_id: StrictStr
    status: Literal["PENDING", "SUCCEEDED", "FAILED"]
    account_id: StrictStr
    recipient_id: StrictStr
    amount_cents: StrictInt = Field(gt=0)
    fee_cents: StrictInt = Field(ge=0)
    currency: Literal["CNY"] = "CNY"
    params_hash: StrictStr
    bank_reference: StrictStr | None = None
    failure_code: StrictStr | None = None
    created_at: datetime
    updated_at: datetime


class TransactionQuery(StrictContract):
    account_id: StrictStr | None = None
    cursor: StrictStr | None = None
    limit: StrictInt = Field(default=50, ge=1, le=100)
    start: datetime | None = None
    end_exclusive: datetime | None = None
    status: Literal["POSTED", "PENDING", "FAILED"] | None = None
    kind: Literal["expense", "refund", "income", "transfer"] | None = None


class MandateResult(StrictContract):
    mandate_id: StrictStr
    account_id: StrictStr
    merchant_name: StrictStr
    status: Literal["ACTIVE", "CANCELLED", "EXPIRED"]
    cancellable: bool
    cancelled_at: datetime | None = None
    updated_at: datetime


class ErrorBody(StrictContract):
    code: StrictStr
    message: StrictStr
    recoverable: bool
    next_action: StrictStr | None = None


class ResponseEnvelope(StrictContract):
    data: Any | None = None
    error: ErrorBody | None = None
    request_id: StrictStr

