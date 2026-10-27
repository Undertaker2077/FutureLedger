from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict

from .contracts import (
    MandateResult,
    TransactionQuery,
    TransferQuote,
    TransferRequest,
    TransferResult,
)
from .domain import BankError
from .service import BankService


class BankAdapter(Protocol):
    def get_balance(self, subject: str, account_id: str) -> dict[str, object]: ...
    def list_transactions(self, subject: str, query: TransactionQuery) -> dict[str, object]: ...
    def resolve_recipient(self, subject: str, recipient_id: str) -> dict[str, object]: ...
    def quote_transfer(
        self, subject: str, request: TransferRequest, now: datetime
    ) -> TransferQuote: ...
    def submit_transfer(
        self, subject: str, quote_id: str, params_hash: str, idempotency_key: str
    ) -> TransferResult: ...
    def get_transfer_status(self, subject: str, transfer_id: str) -> TransferResult: ...
    def list_mandates(
        self, subject: str, account_id: str | None = None
    ) -> list[dict[str, object]]: ...
    def cancel_mandate(
        self, subject: str, mandate_id: str, idempotency_key: str, now: datetime
    ) -> MandateResult: ...
    def get_mandate_status(self, subject: str, mandate_id: str) -> dict[str, object]: ...


class ServiceBankAdapter:
    def __init__(self, service: BankService) -> None:
        self.service = service

    def get_balance(self, subject: str, account_id: str) -> dict[str, object]:
        return self.service.get_balance(subject, account_id)

    def list_transactions(self, subject: str, query: TransactionQuery) -> dict[str, object]:
        return self.service.list_transactions(subject, query)

    def resolve_recipient(self, subject: str, recipient_id: str) -> dict[str, object]:
        return self.service.resolve_recipient(subject, recipient_id)

    def quote_transfer(
        self, subject: str, request: TransferRequest, now: datetime
    ) -> TransferQuote:
        return self.service.quote_transfer(subject, request, now)

    def submit_transfer(
        self, subject: str, quote_id: str, params_hash: str, idempotency_key: str
    ) -> TransferResult:
        return self.service.submit_transfer(
            subject, quote_id, params_hash, idempotency_key
        )

    def get_transfer_status(self, subject: str, transfer_id: str) -> TransferResult:
        return self.service.get_transfer_status(subject, transfer_id)

    def list_mandates(
        self, subject: str, account_id: str | None = None
    ) -> list[dict[str, object]]:
        return self.service.list_mandates(subject, account_id)

    def cancel_mandate(
        self, subject: str, mandate_id: str, idempotency_key: str, now: datetime
    ) -> MandateResult:
        return self.service.cancel_mandate(
            subject, mandate_id, idempotency_key, now
        )

    def get_mandate_status(self, subject: str, mandate_id: str) -> dict[str, object]:
        return self.service.get_mandate_status(subject, mandate_id)


class HttpBankAdapter:
    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        client: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._client = client or httpx.Client(base_url=self.base_url, timeout=10)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        subject: str,
        *,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> Any:
        headers = {
            "Authorization": f"Bearer {self._service_token}",
            "X-Authenticated-User": subject,
        }
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        response = self._client.request(method, path, headers=headers, **kwargs)
        payload = response.json()
        if response.is_error:
            error = payload.get("error") or {}
            raise BankError(
                str(error.get("code", "UPSTREAM_UNAVAILABLE")),
                str(error.get("message", "bank request failed")),
                bool(error.get("recoverable", False)),
                error.get("next_action"),
                response.status_code,
            )
        return payload["data"]

    def get_balance(self, subject: str, account_id: str) -> dict[str, object]:
        return self._request("GET", f"/bank/v1/accounts/{account_id}/balance", subject)

    def list_transactions(self, subject: str, query: TransactionQuery) -> dict[str, object]:
        params = query.model_dump(mode="json", exclude_none=True)
        return self._request("GET", "/bank/v1/transactions", subject, params=params)

    def resolve_recipient(self, subject: str, recipient_id: str) -> dict[str, object]:
        return self._request("GET", f"/bank/v1/recipients/{recipient_id}", subject)

    def quote_transfer(
        self, subject: str, request: TransferRequest, now: datetime
    ) -> TransferQuote:
        del now
        data = self._request(
            "POST",
            "/bank/v1/transfers/quotes",
            subject,
            json=request.model_dump(mode="json"),
        )
        return TransferQuote.model_validate(data, strict=False)

    def submit_transfer(
        self, subject: str, quote_id: str, params_hash: str, idempotency_key: str
    ) -> TransferResult:
        data = self._request(
            "POST",
            "/bank/v1/transfers",
            subject,
            idempotency_key=idempotency_key,
            json={"quote_id": quote_id, "params_hash": params_hash},
        )
        return TransferResult.model_validate(data, strict=False)

    def get_transfer_status(self, subject: str, transfer_id: str) -> TransferResult:
        return TransferResult.model_validate(
            self._request("GET", f"/bank/v1/transfers/{transfer_id}", subject),
            strict=False,
        )

    def list_mandates(
        self, subject: str, account_id: str | None = None
    ) -> list[dict[str, object]]:
        params = {} if account_id is None else {"account_id": account_id}
        return self._request("GET", "/bank/v1/mandates", subject, params=params)

    def cancel_mandate(
        self, subject: str, mandate_id: str, idempotency_key: str, now: datetime
    ) -> MandateResult:
        del now
        return MandateResult.model_validate(
            self._request(
                "POST",
                f"/bank/v1/mandates/{mandate_id}/cancel",
                subject,
                idempotency_key=idempotency_key,
            ),
            strict=False,
        )

    def get_mandate_status(self, subject: str, mandate_id: str) -> dict[str, object]:
        return self._request("GET", f"/bank/v1/mandates/{mandate_id}", subject)


class RecordedCall(BaseModel):
    model_config = ConfigDict(frozen=True)
    method: str
    subject: str
    arguments: dict[str, Any]
    outcome: str


class RecordingSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    calls: tuple[RecordedCall, ...]


T = TypeVar("T")


def _json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(word in key.lower() for word in ("token", "authorization")) else _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class RecordingBankAdapter:
    def __init__(self, wrapped: BankAdapter) -> None:
        self.wrapped = wrapped
        self._calls: list[RecordedCall] = []

    def snapshot(self) -> RecordingSnapshot:
        return RecordingSnapshot(calls=tuple(self._calls))

    def _record(self, method: str, subject: str, arguments: dict[str, Any], call):
        try:
            result = call()
        except BankError as exc:
            self._calls.append(
                RecordedCall(
                    method=method,
                    subject=subject,
                    arguments=_json_safe(arguments),
                    outcome=exc.code,
                )
            )
            raise
        self._calls.append(
            RecordedCall(
                method=method,
                subject=subject,
                arguments=_json_safe(arguments),
                outcome="OK",
            )
        )
        return result

    def get_balance(self, subject: str, account_id: str):
        return self._record("get_balance", subject, {"account_id": account_id}, lambda: self.wrapped.get_balance(subject, account_id))

    def list_transactions(self, subject: str, query: TransactionQuery):
        return self._record("list_transactions", subject, {"query": query}, lambda: self.wrapped.list_transactions(subject, query))

    def resolve_recipient(self, subject: str, recipient_id: str):
        return self._record("resolve_recipient", subject, {"recipient_id": recipient_id}, lambda: self.wrapped.resolve_recipient(subject, recipient_id))

    def quote_transfer(self, subject: str, request: TransferRequest, now: datetime):
        return self._record("quote_transfer", subject, {"request": request, "now": now}, lambda: self.wrapped.quote_transfer(subject, request, now))

    def submit_transfer(self, subject: str, quote_id: str, params_hash: str, idempotency_key: str):
        return self._record("submit_transfer", subject, {"quote_id": quote_id, "params_hash": params_hash, "idempotency_key": idempotency_key}, lambda: self.wrapped.submit_transfer(subject, quote_id, params_hash, idempotency_key))

    def get_transfer_status(self, subject: str, transfer_id: str):
        return self._record("get_transfer_status", subject, {"transfer_id": transfer_id}, lambda: self.wrapped.get_transfer_status(subject, transfer_id))

    def list_mandates(self, subject: str, account_id: str | None = None):
        return self._record("list_mandates", subject, {"account_id": account_id}, lambda: self.wrapped.list_mandates(subject, account_id))

    def cancel_mandate(self, subject: str, mandate_id: str, idempotency_key: str, now: datetime):
        return self._record("cancel_mandate", subject, {"mandate_id": mandate_id, "idempotency_key": idempotency_key, "now": now}, lambda: self.wrapped.cancel_mandate(subject, mandate_id, idempotency_key, now))

    def get_mandate_status(self, subject: str, mandate_id: str):
        return self._record("get_mandate_status", subject, {"mandate_id": mandate_id}, lambda: self.wrapped.get_mandate_status(subject, mandate_id))

