from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from mock_bank.config import Settings


@pytest.fixture(scope="session")
def fixture_root() -> Path:
    return Path(__file__).resolve().parents[3] / "data"


@pytest.fixture(scope="session")
def bank_settings() -> Settings:
    return Settings(
        database_url=os.environ.get(
            "BANK_TEST_DATABASE_URL",
            "postgresql+psycopg://futureledger:futureledger@localhost:55432/futureledger_bank",
        ),
        service_token="test-service-token",
        environment="test",
    )


@pytest.fixture()
def bank_session(bank_settings: Settings) -> Session:
    engine = create_engine(bank_settings.database_url)
    with Session(engine) as session:
        yield session
    engine.dispose()

