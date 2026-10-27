from __future__ import annotations

import pytest

from mock_bank.config import Settings


def test_settings_requires_explicit_internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FUTURELEDGER_INTERNAL_TOKEN", raising=False)
    monkeypatch.delenv("BANK_SERVICE_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="INTERNAL_TOKEN"):
        Settings.from_env()
