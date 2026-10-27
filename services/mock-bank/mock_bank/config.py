from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    service_token: str
    quote_ttl_seconds: int = 300
    environment: str = "development"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get(
                "BANK_DATABASE_URL",
                "postgresql+psycopg://futureledger:futureledger@localhost:5432/futureledger_bank",
            ),
            service_token=os.environ.get(
                "FUTURELEDGER_INTERNAL_TOKEN",
                os.environ.get("BANK_SERVICE_TOKEN", "local-bank-service-token"),
            ),
            quote_ttl_seconds=int(os.environ.get("BANK_QUOTE_TTL_SECONDS", "300")),
            environment=os.environ.get(
                "FUTURELEDGER_ENV",
                os.environ.get("BANK_ENVIRONMENT", "development"),
            ),
        )

