from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from server.infrastructure.db.engine import create_engine, drop_all, create_all, make_uow_factory

TEST_DATABASE_URL = os.environ.get("XUJING_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    if TEST_DATABASE_URL.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        async_engine = create_engine(TEST_DATABASE_URL)
        # A shared in-memory database needs a static pool across connections.
        async_engine = create_engine_with_pool(TEST_DATABASE_URL)
    else:
        async_engine = create_engine(TEST_DATABASE_URL)
        await drop_all(async_engine)
    await create_all(async_engine)
    try:
        yield async_engine
    finally:
        await drop_all(async_engine)
        await async_engine.dispose()


def create_engine_with_pool(url: str) -> AsyncEngine:
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    return create_async_engine(url, poolclass=StaticPool, connect_args={"check_same_thread": False})


@pytest.fixture
async def uow_factory(engine: AsyncEngine):
    return make_uow_factory(engine)


@pytest.fixture(scope="session")
def node_validator():
    from pathlib import Path

    from server.infrastructure.validation.node_validator import NodeValidator

    root = Path(__file__).resolve().parents[2]
    return NodeValidator(package_root=root / "packages" / "validator")


@pytest.fixture
def blob_store(tmp_path):
    from server.infrastructure.blobs import LocalBlobStore

    return LocalBlobStore(str(tmp_path / "blobs"))


@pytest.fixture
def scripted_provider():
    from server.tests.providers import ScriptedProvider
    from server.tests.scripted_agents import scripted

    return ScriptedProvider(scripted())
