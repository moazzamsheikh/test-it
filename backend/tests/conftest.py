"""Shared fixtures: a real DB connection wrapped in a rolled-back transaction.

Tests run against the same Postgres used by `make ingest` (real Wiltz +
Luxembourg City data), not a separate throwaway DB — the mandatory stack asks
for an end-to-end test against a real parcel, which only means something if
the data underneath it is real. Anything a test writes is wrapped in a
transaction rolled back at teardown, so schema-constraint tests never mutate
the real ingested dataset.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import Session

from app.core.config import settings


@pytest.fixture(scope="session")
def engine() -> Engine:
    return create_engine(settings.database_url)


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(scope="session")
def async_engine() -> AsyncEngine:
    # Same URL works for both drivers — see app/core/db.py.
    return create_async_engine(settings.database_url)


@pytest.fixture
async def async_db_session(async_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    connection = await async_engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection)
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
