"""Project application service (F01).

Every operation takes an authenticated actor. Ownership is re-checked on each
call; a project belonging to another actor surfaces as a uniform 404.
"""
from __future__ import annotations

from datetime import datetime, timezone

from server.application.ports import ScopeFactory
from server.domain.shared.errors import Conflict, ValidationFailure
from server.domain.shared.ids import new_id
from server.domain.projects import Brief, BriefRevision, Project


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectService:
    def __init__(self, uow: ScopeFactory) -> None:
        self._uow = uow

    async def create(self, actor_id: str, name: str, brief: Brief) -> Project:
        project = Project(
            id=new_id(),
            owner_id=actor_id,
            name=name,
            brief=brief,
            created_at=_now(),
            updated_at=_now(),
        )
        async with self._uow() as uow:
            created = await uow.projects.create(project)
            await uow.projects.append_brief_revision(
                BriefRevision(project_id=project.id, revision=1, brief=brief, note="初始简报", created_at=project.created_at)
            )
            await uow.commit()
        return created

    async def get(self, actor_id: str, project_id: str) -> Project:
        async with self._uow() as uow:
            project = await uow.projects.get(project_id)
        if project is None:
            from server.domain.shared.errors import NotFound

            raise NotFound(object_id=project_id)
        project.assert_owned_by(actor_id)
        return project

    async def list(self, actor_id: str, cursor: str | None = None, limit: int = 20) -> tuple[list[Project], str | None]:
        if not 1 <= limit <= 50:
            raise ValidationFailure("INVALID_LIMIT", "limit 必须在 1—50 之间。")
        async with self._uow() as uow:
            return await uow.projects.list_for_owner(actor_id, cursor, limit)

    async def update_brief(self, actor_id: str, project_id: str, brief: Brief, expected_revision: int, note: str = "") -> Project:
        async with self._uow() as uow:
            project = await uow.projects.get(project_id)
            if project is None:
                from server.domain.shared.errors import NotFound

                raise NotFound(object_id=project_id)
            project.assert_owned_by(actor_id)
            if project.brief_revision != expected_revision:
                raise Conflict(
                    "BRIEF_REVISION_CONFLICT",
                    "简报已被修改，请重新加载。",
                    object_id=project.id,
                )
            if project.active_revision_run_id is not None:
                raise Conflict("ACTIVE_RUN", "项目有正在运行的任务，暂不能修改简报。", object_id=project.active_revision_run_id)
            project.brief = brief
            project.brief_revision += 1
            project.updated_at = _now()
            saved = await uow.projects.save(project)
            await uow.projects.append_brief_revision(
                BriefRevision(
                    project_id=project.id,
                    revision=project.brief_revision,
                    brief=brief,
                    note=note,
                    created_at=project.updated_at,
                )
            )
            await uow.commit()
        return saved

    async def rename(self, actor_id: str, project_id: str, name: str) -> Project:
        async with self._uow() as uow:
            project = await uow.projects.get(project_id)
            if project is None:
                from server.domain.shared.errors import NotFound

                raise NotFound(object_id=project_id)
            project.assert_owned_by(actor_id)
            project.rename(name)
            project.updated_at = _now()
            saved = await uow.projects.save(project)
            await uow.commit()
        return saved
