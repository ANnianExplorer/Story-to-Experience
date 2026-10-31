"""API composition root and routes.

Routes are thin: they authenticate, translate HTTP into application calls and
map domain errors to the documented envelope. Business rules never live here.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, Request, UploadFile
from fastapi.responses import StreamingResponse

from server.application.conversations import ConversationService
from server.application.delivery import DeliveryService
from server.application.evidence import EvidenceService
from server.application.orchestration import OrchestrationService
from server.application.projects import ProjectService
from server.application.runs import RunService
from server.domain.conversation import DialogueProfile
from server.domain.errors import NotFound, ValidationFailure
from server.domain.project import Brief, Project
from server.infrastructure.blobs import LocalBlobStore
from server.infrastructure.db.engine import create_engine, make_uow_factory
from server.infrastructure.llm.gateway import AnthropicGatewayProvider, MockProvider
from server.infrastructure.validation.node_validator import NodeValidator
from xujing_api.config import Settings, get_settings
from xujing_api.errors import envelope, install_error_handlers
from xujing_api.identity import Actor, DevIdentity
from xujing_api.schemas import (
    ClaimInput,
    ClaimsRequest,
    ConversationCreate,
    ExportRequest,
    GuideConversationCreate,
    ProjectCreate,
    ProjectPatch,
    ReviewRequest,
    RunRequest,
    ShareRequest,
    SnapshotRequest,
    StableRequest,
    TurnRequest,
)


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


def brief_from(payload: Any) -> Brief:
    return Brief(
        audience=payload.audience,
        duration_minutes=payload.duration_minutes,
        learning_goals=tuple(payload.learning_goals),
    )


def build_provider(settings: Settings) -> Any:
    if settings.model_provider == "mock":
        return MockProvider()
    return AnthropicGatewayProvider(
        base_url=settings.model_base_url,
        api_key=settings.model_api_key,
        model=settings.model_name,
    )


def create_app(
    settings: Settings | None = None,
    *,
    uow_factory: Any | None = None,
    identity: Any | None = None,
    provider: Any | None = None,
    validator: Any | None = None,
    blob_store: Any | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    engine = None
    if uow_factory is None:
        engine = create_engine(resolved.database_url)
        uow_factory = make_uow_factory(engine)
    resolved_identity = identity or DevIdentity(enabled=resolved.identity_mode == "dev")
    resolved_provider = provider or build_provider(resolved)
    resolved_validator = validator or NodeValidator(
        package_root=__import__("pathlib").Path(__file__).resolve().parents[3] / "packages" / "validator"
    )
    resolved_blobs = blob_store or LocalBlobStore(resolved.storage_root)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title="叙境 API", version="0.3.0", lifespan=lifespan)
    install_error_handlers(app)
    app.state.settings = resolved
    app.state.uow_factory = uow_factory
    app.state.identity = resolved_identity
    app.state.provider = resolved_provider
    app.state.validator = resolved_validator
    app.state.blobs = resolved_blobs

    def projects(request: Request) -> ProjectService:
        return ProjectService(request.app.state.uow_factory)

    def evidence(request: Request) -> EvidenceService:
        return EvidenceService(request.app.state.uow_factory, request.app.state.blobs)

    def runs(request: Request) -> RunService:
        return RunService(request.app.state.uow_factory)

    def orchestration(request: Request) -> OrchestrationService:
        return OrchestrationService(
            request.app.state.uow_factory,
            request.app.state.provider,
            request.app.state.validator,
            provider_is_mock=getattr(request.app.state.provider, "is_mock", False),
        )

    def conversations(request: Request) -> ConversationService:
        return ConversationService(
            request.app.state.uow_factory,
            request.app.state.provider,
            provider_is_mock=getattr(request.app.state.provider, "is_mock", False),
        )

    def delivery(request: Request) -> DeliveryService:
        return DeliveryService(request.app.state.uow_factory)

    async def actor_of(request: Request) -> Actor:
        return await request.app.state.identity.actor_from_request(request)

    # ------------------------------------------------------------------ meta

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        provider = request_provider = app.state.provider
        return {
            "status": "ok",
            "environment": resolved.environment,
            "model_provider": getattr(provider, "name", "unknown"),
            "model_configured": getattr(provider, "configured", True),
            "simulated": bool(getattr(provider, "is_mock", False)),
            "validator_available": bool(getattr(app.state.validator, "script_exists", True)),
        }

    # -------------------------------------------------------------- projects

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
        return envelope(project_payload(await projects(request).get(actor.id, project_id)), request)

    @app.patch("/api/v1/projects/{project_id}")
    async def patch_project(project_id: str, body: ProjectPatch, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        service = projects(request)
        current = await service.get(actor.id, project_id)
        if body.name is not None:
            current = await service.rename(actor.id, project_id, body.name)
        if body.brief is not None:
            if body.expected_revision is None:
                raise ValidationFailure(
                    "EXPECTED_REVISION_REQUIRED", "修改简报必须提交 expected_revision。", {"field": "expected_revision"}
                )
            current = await service.update_brief(
                actor.id, project_id, brief_from(body.brief), body.expected_revision
            )
        return envelope(project_payload(current), request)

    # --------------------------------------------------------------- sources

    @app.post("/api/v1/projects/{project_id}/sources", status_code=202)
    async def upload_source(
        project_id: str,
        request: Request,
        file: UploadFile = File(...),
        license_note: str = Form(...),
    ) -> dict[str, Any]:
        actor = await actor_of(request)
        data = await file.read()
        document = await evidence(request).upload(
            actor.id,
            project_id,
            filename=file.filename or "未命名资料",
            data=data,
            license_note=license_note,
            declared_content_type=file.content_type,
        )
        return envelope(
            {
                "source_id": document.id,
                "parse_status": document.parse_status,
                "sha256": document.sha256,
                "error_code": document.error_code,
            },
            request,
        )

    @app.post("/api/v1/projects/{project_id}/sources/text", status_code=202)
    async def upload_text(project_id: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        actor = await actor_of(request)
        text = str(body.get("text") or "")
        if not text.strip():
            raise ValidationFailure("EMPTY_SOURCE", "正文不能为空。")
        document = await evidence(request).upload(
            actor.id,
            project_id,
            filename=str(body.get("title") or "粘贴资料"),
            data=text.encode("utf-8"),
            license_note=str(body.get("license_note") or ""),
        )
        return envelope(
            {
                "source_id": document.id,
                "parse_status": document.parse_status,
                "sha256": document.sha256,
                "error_code": document.error_code,
            },
            request,
        )

    @app.get("/api/v1/sources/{source_id}")
    async def get_source(source_id: str, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        document = await evidence(request).get_document(actor.id, source_id)
        return envelope(
            {
                "id": document.id,
                "title": document.title,
                "mime_type": document.mime_type,
                "sha256": document.sha256,
                "parse_status": document.parse_status,
                "parse_version": document.parse_version,
                "error_code": document.error_code,
            },
            request,
        )

    @app.get("/api/v1/sources/{source_id}/spans")
    async def get_spans(source_id: str, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        spans = await evidence(request).spans(actor.id, source_id)
        return envelope(
            [
                {
                    "id": span.id,
                    "page": span.page,
                    "paragraph": span.paragraph,
                    "start_cp": span.start_cp,
                    "end_cp": span.end_cp,
                    "quote": span.quote,
                    "text_hash": span.text_hash,
                }
                for span in spans
            ],
            request,
        )

    @app.get("/api/v1/projects/{project_id}/claims")
    async def get_claims(project_id: str, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        claims = await evidence(request).claims(actor.id, project_id)
        return envelope(
            [
                {
                    "id": claim.id,
                    "revision": claim.revision,
                    "statement": claim.statement,
                    "content_type": claim.content_type,
                    "evidence_span_ids": list(claim.evidence_span_ids),
                    "qualifier": claim.qualifier,
                }
                for claim in claims
            ],
            request,
        )

    @app.post("/api/v1/projects/{project_id}/claims", status_code=201)
    async def add_claims(project_id: str, body: ClaimsRequest, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        claims = await evidence(request).add_claims(
            actor.id, project_id, [claim.model_dump() for claim in body.claims]
        )
        return envelope(
            [{"id": claim.id, "revision": claim.revision, "content_type": claim.content_type} for claim in claims],
            request,
        )

    @app.post("/api/v1/projects/{project_id}/source-snapshots", status_code=201)
    async def create_snapshot(project_id: str, body: SnapshotRequest, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        snapshot = await evidence(request).freeze_snapshot(actor.id, project_id, body.source_ids)
        return envelope({"id": snapshot.id, "sha256": snapshot.sha256}, request)

    # ------------------------------------------------------------------ runs

    @app.post("/api/v1/projects/{project_id}/runs", status_code=202)
    async def submit_run(
        project_id: str,
        body: RunRequest,
        request: Request,
        background: BackgroundTasks,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        actor = await actor_of(request)
        if not idempotency_key:
            raise ValidationFailure("IDEMPOTENCY_KEY_REQUIRED", "提交生成必须携带 Idempotency-Key。")
        submission = await runs(request).submit_generation(
            actor.id,
            project_id,
            source_snapshot_id=body.source_snapshot_id,
            brief_revision=body.brief_revision,
            idempotency_key=idempotency_key,
        )
        if submission.created and body.auto_continue:
            service = orchestration(request)
            background.add_task(_run_in_background, service, submission.run_id, body.instruction)
        return envelope({"run_id": submission.run_id, "created": submission.created}, request)

    @app.get("/api/v1/runs/{run_id}")
    async def get_run(run_id: str, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        run = await runs(request).get(actor.id, run_id)
        return envelope(
            {
                "id": run.id,
                "status": run.status.value,
                "stage": run.stage.value,
                "input_hash": run.input_hash,
                "attempt": run.attempt,
                "last_sequence": run.last_sequence,
                "budget": {
                    "max_calls": run.budget.max_calls,
                    "calls_reserved": run.budget.calls_reserved,
                    "calls_settled": run.budget.calls_settled,
                    "repair_rounds": run.budget.repair_rounds,
                },
                "error_code": run.error_code,
            },
            request,
        )

    @app.get("/api/v1/runs/{run_id}/events")
    async def run_events(run_id: str, request: Request, after: int = 0) -> StreamingResponse:
        actor = await actor_of(request)
        events = await runs(request).events(actor.id, run_id, after)

        async def stream() -> AsyncIterator[bytes]:
            for event in events:
                chunk = (
                    f"id: {event['sequence']}\n"
                    f"event: stage\n"
                    f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                )
                yield chunk.encode("utf-8")
                await asyncio.sleep(0)
            yield b": heartbeat\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/v1/runs/{run_id}/cancel")
    async def cancel_run(run_id: str, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        run = await runs(request).cancel(actor.id, run_id)
        return envelope({"id": run.id, "status": run.status.value}, request)

    @app.get("/api/v1/runs/{run_id}/agent-tasks")
    async def agent_tasks(run_id: str, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        await runs(request).get(actor.id, run_id)  # authorization first
        async with request.app.state.uow_factory() as uow:
            tasks = await uow.agents.tasks_for(run_id)
            plan = await uow.agents.get_plan(run_id)
        return envelope({"plan": plan, "tasks": tasks}, request)

    # --------------------------------------------------------------- versions

    @app.get("/api/v1/versions/{version_id}")
    async def get_version(version_id: str, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        async with request.app.state.uow_factory() as uow:
            version = await uow.versions.get(version_id)
            if version is None:
                raise NotFound(object_id=version_id)
            project = await uow.projects.get(version["project_id"])
            if project is None or project.owner_id != actor.id:
                raise NotFound(object_id=version_id)
        return envelope(version, request)

    @app.get("/api/v1/projects/{project_id}/versions")
    async def list_versions(project_id: str, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        project = await projects(request).get(actor.id, project_id)
        async with request.app.state.uow_factory() as uow:
            versions = await uow.versions.list_for(project.id)
        return envelope(
            [
                {
                    "id": item["id"],
                    "parent_id": item["parent_id"],
                    "spec_hash": item["spec_hash"],
                    "semantic_hash": item["semantic_hash"],
                    "created_at": item["created_at"],
                }
                for item in versions
            ],
            request,
        )

    @app.post("/api/v1/versions/{version_id}/reviews", status_code=201)
    async def submit_review(version_id: str, body: ReviewRequest, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        review = await delivery(request).submit_review(
            actor.id,
            version_id,
            decision=body.decision,
            notes=body.notes,
            coverage_claim_ids=body.coverage_claim_ids,
            expected_semantic_hash=body.expected_semantic_hash,
            actor_kind=actor.kind,
        )
        return envelope({"id": review.id, "decision": review.decision}, request)

    @app.post("/api/v1/projects/{project_id}/stable")
    async def promote(project_id: str, body: StableRequest, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        result = await delivery(request).promote_stable(actor.id, project_id, body.version_id)
        return envelope(result, request)

    @app.post("/api/v1/versions/{version_id}/shares", status_code=201)
    async def create_share(version_id: str, body: ShareRequest, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        if body.version_id != version_id:
            raise ValidationFailure("VERSION_MISMATCH", "路径与请求体的版本不一致。")
        async with request.app.state.uow_factory() as uow:
            version = await uow.versions.get(version_id)
        if version is None:
            raise NotFound(object_id=version_id)
        share, token = await delivery(request).create_share(
            actor.id,
            version["project_id"],
            version_id=version_id,
            license_ack=body.license_ack,
            hours=body.hours,
        )
        return envelope(
            {"share_id": share.id, "token": token, "expires_at": share.expires_at.isoformat()},
            request,
        )

    @app.delete("/api/v1/shares/{share_id}", status_code=204)
    async def revoke_share(share_id: str, request: Request) -> None:
        actor = await actor_of(request)
        await delivery(request).revoke_share(actor.id, share_id)

    @app.get("/api/v1/share/{token}/manifest")
    async def share_manifest(token: str, request: Request) -> dict[str, Any]:
        resolved = await delivery(request).resolve_share(token)
        version = resolved["version"]
        return envelope(
            {
                "version_id": version["id"],
                "spec": version["spec"],
                "dialogue_profile": version["dialogue_profile"],
                "spec_hash": version["spec_hash"],
            },
            request,
        )

    @app.post("/api/v1/share/{token}/sessions", status_code=201)
    async def share_session(token: str, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        session = await delivery(request).create_experience_session(token, actor.id)
        return envelope(session, request)

    @app.post("/api/v1/versions/{version_id}/exports", status_code=202)
    async def export_version(version_id: str, body: ExportRequest, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        bundle = await delivery(request).export_bundle(actor.id, version_id, mode=body.mode)
        return envelope(bundle, request)

    # ---------------------------------------------------------- conversations

    @app.post("/api/v1/projects/{project_id}/conversations", status_code=201)
    async def create_conversation(project_id: str, body: ConversationCreate, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        session = await conversations(request).create_creator_session(
            actor.id, project_id, base_version_id=body.base_version_id
        )
        return envelope({"conversation_id": session.id, "kind": session.kind.value}, request)

    @app.get("/api/v1/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        session = await conversations(request).get_session(actor.id, conversation_id)
        return envelope(
            {
                "id": session.id,
                "kind": session.kind.value,
                "project_id": session.project_id,
                "version_id": session.version_id,
                "status": session.status,
            },
            request,
        )

    @app.post("/api/v1/conversations/{conversation_id}/turns", status_code=202)
    async def submit_turn(conversation_id: str, body: TurnRequest, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        service = conversations(request)
        turn, reused = await service.submit_turn(
            actor.id,
            conversation_id,
            client_turn_id=body.client_turn_id,
            message=body.message,
            scene_id=body.scene_id,
            flags=body.flags,
        )
        return envelope({"turn_id": turn.id, "status": turn.status.value, "reused": reused}, request)

    @app.post("/api/v1/conversation-turns/{turn_id}/run")
    async def execute_turn(turn_id: str, request: Request, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a queued turn (development/synchronous path).

        In production the API streams from a background task and the worker
        owns execution; this endpoint keeps the contract observable end-to-end.
        """
        actor = await actor_of(request)
        service = conversations(request)
        async with request.app.state.uow_factory() as uow:
            turn = await uow.conversations.get_turn(turn_id)
            if turn is None:
                raise NotFound(object_id=turn_id)
            session = await uow.conversations.get_session(turn.session_id)
            if session is None or session.actor_id != actor.id:
                raise NotFound(object_id=turn_id)
        execution = await service.execute_turn(
            turn_id,
            scene_id=(body or {}).get("scene_id"),
            flags=(body or {}).get("flags"),
        )
        turn_model = execution.turn
        return envelope(
            {
                "turn_id": turn_model.id,
                "status": turn_model.status.value,
                "final_text": turn_model.final_text,
                "answerability": turn_model.answerability.value if turn_model.answerability else None,
                "citations": [citation.to_payload() for citation in turn_model.citations],
                "suggested_actions": [action.to_payload() for action in turn_model.suggested_actions],
                "cost_status": turn_model.cost_status,
                "events": [
                    {"sequence": event.sequence, "type": event.type, "payload": event.payload}
                    for event in execution.events
                ],
            },
            request,
        )

    @app.get("/api/v1/conversation-turns/{turn_id}/events")
    async def turn_events(turn_id: str, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        async with request.app.state.uow_factory() as uow:
            turn = await uow.conversations.get_turn(turn_id)
            if turn is None:
                raise NotFound(object_id=turn_id)
            session = await uow.conversations.get_session(turn.session_id)
            if session is None or session.actor_id != actor.id:
                raise NotFound(object_id=turn_id)
        if turn.status.value not in ("succeeded", "failed", "cancelled"):
            raise ValidationFailure("TURN_INCOMPLETE", "turn 尚未结束，部分输出不是最终答案。")
        return envelope(
            {
                "turn_id": turn.id,
                "status": turn.status.value,
                "final_text": turn.final_text,
                "citations": [citation.to_payload() for citation in turn.citations],
            },
            request,
        )

    @app.post("/api/v1/conversation-turns/{turn_id}/cancel")
    async def cancel_turn(turn_id: str, request: Request) -> dict[str, Any]:
        actor = await actor_of(request)
        turn = await conversations(request).cancel_turn(actor.id, turn_id)
        return envelope({"turn_id": turn.id, "status": turn.status.value}, request)

    return app


async def _run_in_background(service: OrchestrationService, run_id: str, instruction: str) -> None:
    try:
        await service.execute(run_id, actor_instruction=instruction)
    except Exception:  # the run row already carries the failure state
        pass


from xujing_api.schemas import (  # noqa: E402  (kept for the route signatures below)
    BriefModel,
)
