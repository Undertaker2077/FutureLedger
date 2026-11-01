from pathlib import Path


def test_postgresql_18_uses_major_version_data_mount() -> None:
    compose = (
        Path(__file__).parents[2] / "compose.bank.yml"
    ).read_text(encoding="utf-8")

    assert "futureledger-bank-postgres-18:/var/lib/postgresql" in compose
    assert "/var/lib/postgresql/data" not in compose
