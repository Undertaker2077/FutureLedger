from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings


def create_engine_from_settings(settings: Settings) -> Engine:
    return create_engine(settings.database_url, pool_pre_ping=True)


def create_session_factory(settings: Settings) -> sessionmaker[Session]:
    return sessionmaker(
        bind=create_engine_from_settings(settings),
        class_=Session,
        expire_on_commit=False,
    )


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory.begin() as session:
        yield session
