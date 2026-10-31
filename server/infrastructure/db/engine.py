"""Database engine construction and schema bootstrap.

Production uses PostgreSQL (``postgresql+asyncpg``). Unit tests use SQLite with
``aiosqlite`` so domain and application tests stay fast; concurrency tests that
need row locks are marked ``db`` and only run against PostgreSQL.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from server.infrastructure.db.tables import Base
from server.infrastructure.db.uow import ScopeFactory, UnitOfWorkScope, scope_factory


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    kwargs: dict[str, object] = {"echo": echo, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs.pop("pool_pre_ping")
    return create_async_engine(url, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


def make_uow_factory(engine: AsyncEngine) -> ScopeFactory:
    return scope_factory(create_session_factory(engine))


async def create_all(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def drop_all(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@asynccontextmanager
async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session
