from __future__ import annotations

import pytest

from server.application.projects import ProjectService
from server.domain.shared.errors import Conflict, NotFound, ValidationFailure
from server.domain.projects import Brief

ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"


def make_brief() -> Brief:
    return Brief(audience="五年级学生", duration_minutes=8, learning_goals=("观察工具用途", "理解前置步骤"))


async def test_create_assigns_owner_from_actor_not_payload(uow_factory) -> None:
    service = ProjectService(uow_factory)
    project = await service.create(ALICE, "工坊体验", make_brief())
    assert project.owner_id == ALICE
    assert project.brief_revision == 1
    assert project.stable_version_id is None


async def test_cross_owner_access_returns_uniform_404(uow_factory) -> None:
    service = ProjectService(uow_factory)
    project = await service.create(ALICE, "工坊体验", make_brief())
    with pytest.raises(NotFound):
        await service.get(BOB, project.id)
    with pytest.raises(NotFound):
        await service.update_brief(BOB, project.id, make_brief(), expected_revision=1)


async def test_list_only_returns_own_projects(uow_factory) -> None:
    service = ProjectService(uow_factory)
    await service.create(ALICE, "A 项目", make_brief())
    await service.create(BOB, "B 项目", make_brief())
    owned, cursor = await service.list(ALICE)
    assert [project.name for project in owned] == ["A 项目"]
    assert cursor is None


async def test_brief_revision_conflict_keeps_old_history(uow_factory) -> None:
    service = ProjectService(uow_factory)
    project = await service.create(ALICE, "工坊体验", make_brief())
    updated = await service.update_brief(
        ALICE, project.id, Brief(audience="六年级", duration_minutes=5, learning_goals=("识别布料",)), expected_revision=1
    )
    assert updated.brief_revision == 2
    with pytest.raises(Conflict) as error:
        await service.update_brief(ALICE, project.id, make_brief(), expected_revision=1)
    assert error.value.code == "BRIEF_REVISION_CONFLICT"
    async with uow_factory() as uow:
        history = await uow.projects.brief_history(project.id)
    assert [entry.revision for entry in history] == [1, 2]
    assert history[1].brief.audience == "六年级"


async def test_invalid_brief_is_rejected_before_persistence(uow_factory) -> None:
    service = ProjectService(uow_factory)
    with pytest.raises(ValidationFailure):
        await service.create(ALICE, "工坊体验", Brief(audience=" ", duration_minutes=5, learning_goals=("目标",)))
    with pytest.raises(ValidationFailure):
        await service.create(ALICE, "工坊体验", Brief(audience="学生", duration_minutes=60, learning_goals=("目标",)))
    owned, _ = await service.list(ALICE)
    assert owned == []
