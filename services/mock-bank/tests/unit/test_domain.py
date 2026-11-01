from __future__ import annotations

import string

import pytest
from pydantic import ValidationError

from mock_bank.contracts import TransferRequest
from mock_bank.domain import canonical_transfer_hash, validate_idempotency_key


def make_request(**overrides: object) -> TransferRequest:
    values: dict[str, object] = {
        "account_id": "acct-alice-cny",
        "recipient_id": "recipient-rent",
        "amount_cents": 50_000,
        "currency": "CNY",
        "reference": "October rent",
    }
    values.update(overrides)
    return TransferRequest.model_validate(values)


@pytest.mark.parametrize("amount", [1, 50_000, 2_147_483_647])
def test_transfer_amount_accepts_positive_integer_cents(amount: int) -> None:
    assert make_request(amount_cents=amount).amount_cents == amount


@pytest.mark.parametrize("amount", [True, 0, -1, 1.5, "500"])
def test_transfer_amount_rejects_non_positive_or_non_integer_cents(amount: object) -> None:
    with pytest.raises(ValidationError):
        make_request(amount_cents=amount)


@pytest.mark.parametrize("currency", ["USD", "cny", "", 156])
def test_transfer_request_accepts_only_literal_cny(currency: object) -> None:
    with pytest.raises(ValidationError):
        make_request(currency=currency)


def test_canonical_hash_is_stable_across_input_order() -> None:
    first = TransferRequest.model_validate(
        {
            "reference": "October rent",
            "currency": "CNY",
            "recipient_id": "recipient-rent",
            "amount_cents": 50_000,
            "account_id": "acct-alice-cny",
        }
    )
    second = TransferRequest.model_validate(
        {
            "account_id": "acct-alice-cny",
            "amount_cents": 50_000,
            "recipient_id": "recipient-rent",
            "currency": "CNY",
            "reference": "October rent",
        }
    )

    assert canonical_transfer_hash("alice", first, 0) == canonical_transfer_hash(
        "alice", second, 0
    )


@pytest.mark.parametrize(
    ("subject", "candidate_request", "fee_cents"),
    [
        ("bob", make_request(), 0),
        ("alice", make_request(account_id="acct-alice-savings"), 0),
        ("alice", make_request(recipient_id="recipient-electricity"), 0),
        ("alice", make_request(amount_cents=50_001), 0),
        ("alice", make_request(), 1),
    ],
)
def test_canonical_hash_changes_for_bank_significant_parameters(
    subject: str, candidate_request: TransferRequest, fee_cents: int
) -> None:
    baseline = canonical_transfer_hash("alice", make_request(), 0)
    assert canonical_transfer_hash(subject, candidate_request, fee_cents) != baseline


@pytest.mark.parametrize(
    "key",
    [
        "transfer-500",
        "A" * 8,
        "z" * 128,
        string.ascii_letters + string.digits + "-_.:/",
    ],
)
def test_idempotency_key_accepts_8_to_128_visible_ascii_characters(key: str) -> None:
    assert validate_idempotency_key(key) == key


@pytest.mark.parametrize(
    "key",
    [
        "short",
        "x" * 129,
        "contains space",
        "contains\ttab",
        "contains\nnewline",
        "unicode-銀行",
    ],
)
def test_idempotency_key_rejects_invalid_length_or_characters(key: str) -> None:
    with pytest.raises(ValueError):
        validate_idempotency_key(key)
