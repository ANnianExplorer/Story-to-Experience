"""FastAPI application factory and the routes implemented so far."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

from server.application.projects import ProjectService
from server.domain.project import Brief, Project
from server.infrastructure.db.engine import create_engine, make_uow_factory
from xujing_api.config import Settings, get_settings
from xujing_api.errors import envelope, install_error_handlers
from xujing_api.identity import Actor, DevIdentity


class BriefModel(BaseModel):
    audience: str = Field(min_length=1, max_length=120)
    duration_minutes: int = Field(ge=1, le=30)
    learning_goals: list[str] = Field(min_length=1, max_length=6)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brief: BriefModel


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    brief: BriefModel | None = None
    expected_revision: int | None = Field(default=None, ge=1)


def project_payload(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "brief": project.brief.to_payload(),
        "brief_revision": project.brief_revision,
        "revision_head_id": project.revision_head_id,
        "latest_candidate_version_id": project.latest_candidate_version_id,
        "selected_version_id": project.selected_version_id,
        "stable_version_id": project.stable_version_id,
        "active_revision_run_id": project.active_revision_run_id,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def brief_from(model: BriefModel) -> Brief:
    return Brief(
        audience=model.audience,
        duration_minutes=model.duration_minutes,
        learning_goals=tuple(model.learning_goals),
    )


def create_app(
    settings: Settings | None = None,
    *,
    uow_factory: Any | None = None,
    identity: Any | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    engine = None
    if uow_factory is None:
        engine = create_engine(resolved.database_url)
        uow_factory = make_uow_factory(engine)
    resolved_identity = identity or DevIdentity(enabled=resolved.identity_mode == "dev")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title="叙境 API", version="0.1.0", lifespan=lifespan)
    install_error_handlers(app)
    app.state.settings = resolved
    app.state.uow_factory = uow_factory
    app.state.identity = resolved_identity

    def projects(request: Request) -> ProjectService:
        return ProjectService(request.app.state.uow_factory)

    async def actor_of(request: Request) -> Actor:
        return await request.app.state.identity.actor_from_request(request)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "environment": resolved.environment}

    @app.post("/api/v1/projects", status_code=201)
    async def create_project(body: ProjectCreate, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        project = await projects(request).create(actor.id, body.name, brief_from(body.brief))
        return envelope(project_payload(project), request)

    @app.get("/api/v1/projects")
    async def list_projects(request: Request, cursor: str | None = None, limit: int = 20) -> dict[str, Any]:
        actor = await actor_of(request)
        items, next_cursor = await projects(request).list(actor.id, cursor, limit)
        return envelope([project_payload(item) for item in items], request, cursor=next_cursor)

    @app.get("/api/v1/projects/{project_id}")
    async def get_project(project_id: str, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        project = await projects(request).get(actor.id, project_id)
        return envelope(project_payload(project), request)

    @app.patch("/api/v1/projects/{project_id}")
    async def patch_project(project_id: str, body: ProjectPatch, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        service = projects(request)
        current = await service.get(actor.id, project_id)
        if body.name is not None:
            current = await service.rename(actor.id, project_id, body.name)
        if body.brief is not None:
            if body.expected_revision is None:
                from server.domain.errors import ValidationFailure

                raise ValidationFailure(
                    "EXPECTED_REVISION_REQUIRED",
                    "修改简报必须提交 expected_revision。",
                    {"field": "expected_revision"},
                )
            current = await service.update_brief(
                actor.id, project_id, brief_from(body.brief), body.expected_revision
            )
        return envelope(project_payload(current), request)

    return app
