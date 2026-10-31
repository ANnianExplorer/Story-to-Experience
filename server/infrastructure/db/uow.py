"""Unit of work: one AsyncSession per application use case.

Repositories share the same session so a use case commits atomically. Exiting
without ``commit()`` rolls back, which prevents partially written business
state on error paths.
"""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.infrastructure.db import repositories as repo


class UnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = repo.ProjectRepository(session)
        self.evidence = repo.EvidenceRepository(session)
        self.runs = repo.RunRepository(session)
        self.agents = repo.AgentRepository(session)
        self.versions = repo.VersionRepository(session)
        self.conversations = repo.ConversationRepository(session)
        self.idempotency = repo.IdempotencyRepository(session)
        self.shares = repo.SharesRepository(session)
        self.reviews = repo.ReviewRepository(session)
        self.experience_sessions = repo.ExperienceSessionRepository(session)
        self.committed = False

    async def commit(self) -> None:
        await self.session.commit()
        self.committed = True

    async def rollback(self) -> None:
        await self.session.rollback()


class UnitOfWorkScope:
    """Async context manager producing a fresh ``UnitOfWork``."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory
        self._uow: UnitOfWork | None = None

    async def __aenter__(self) -> UnitOfWork:
        session = self._factory()
        self._uow = UnitOfWork(session)
        return self._uow

    async def __aexit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> None:
        assert self._uow is not None
        if exc_type is not None or not self._uow.committed:
            await self._uow.session.rollback()
        await self._uow.session.close()


ScopeFactory = Callable[[], UnitOfWorkScope]


def scope_factory(session_factory: async_sessionmaker[AsyncSession]) -> ScopeFactory:
    """Return a callable that creates an independent scope per use case."""
    return lambda: UnitOfWorkScope(session_factory)
