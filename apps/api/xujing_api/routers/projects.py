"""Project, source, claim and snapshot routes (F01/F02)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile

from server.domain.projects import Brief, Project
from server.domain.shared.errors import NotFound, ValidationFailure
from xujing_api.core.errors import envelope
from xujing_api.deps import ActorDep, EvidenceDep, ProjectsDep
from xujing_api.schemas.requests import (
    ClaimsRequest,
    ProjectCreate,
    ProjectPatch,
    SnapshotRequest,
)

router = APIRouter(prefix="/api/v1", tags=["projects"])


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


@router.post("/projects", status_code=201)
async def create_project(body: ProjectCreate, request: Request, actor: ActorDep, projects: ProjectsDep) -> dict[str, Any]:
    project = await projects.create(actor.id, body.name, brief_from(body.brief))
    return envelope(project_payload(project), request)


@router.get("/projects")
async def list_projects(
    request: Request, actor: ActorDep, projects: ProjectsDep, cursor: str | None = None, limit: int = 20
) -> dict[str, Any]:
    items, next_cursor = await projects.list(actor.id, cursor, limit)
    return envelope([project_payload(item) for item in items], request, cursor=next_cursor)


@router.get("/projects/{project_id}")
async def get_project(project_id: str, request: Request, actor: ActorDep, projects: ProjectsDep) -> dict[str, Any]:
    return envelope(project_payload(await projects.get(actor.id, project_id)), request)


@router.patch("/projects/{project_id}")
async def patch_project(
    project_id: str, body: ProjectPatch, request: Request, actor: ActorDep, projects: ProjectsDep
) -> dict[str, Any]:
    current = await projects.get(actor.id, project_id)
    if body.name is not None:
        current = await projects.rename(actor.id, project_id, body.name)
    if body.brief is not None:
        if body.expected_revision is None:
            raise ValidationFailure(
                "EXPECTED_REVISION_REQUIRED", "修改简报必须提交 expected_revision。", {"field": "expected_revision"}
            )
        current = await projects.update_brief(actor.id, project_id, brief_from(body.brief), body.expected_revision)
    return envelope(project_payload(current), request)


@router.post("/projects/{project_id}/sources", status_code=202)
async def upload_source(
    project_id: str,
    request: Request,
    actor: ActorDep,
    evidence: EvidenceDep,
    file: UploadFile = File(...),
    license_note: str = Form(...),
) -> dict[str, Any]:
    data = await file.read()
    document = await evidence.upload(
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


@router.post("/projects/{project_id}/sources/text", status_code=202)
async def upload_text(
    project_id: str, body: dict[str, Any], request: Request, actor: ActorDep, evidence: EvidenceDep
) -> dict[str, Any]:
    text = str(body.get("text") or "")
    if not text.strip():
        raise ValidationFailure("EMPTY_SOURCE", "正文不能为空。")
    document = await evidence.upload(
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


@router.get("/projects/{project_id}/sources")
async def list_sources(
    project_id: str, request: Request, actor: ActorDep, evidence: EvidenceDep
) -> dict[str, Any]:
    documents = await evidence.documents(actor.id, project_id)
    return envelope(
        [
            {
                "source_id": document.id,
                "title": document.title,
                "parse_status": document.parse_status,
                "parse_version": document.parse_version,
                "sha256": document.sha256,
                "error_code": document.error_code,
                "created_at": document.created_at.isoformat() if document.created_at else None,
            }
            for document in documents
        ],
        request,
    )


@router.get("/sources/{source_id}")
async def get_source(source_id: str, request: Request, actor: ActorDep, evidence: EvidenceDep) -> dict[str, Any]:
    document = await evidence.get_document(actor.id, source_id)
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


@router.get("/sources/{source_id}/spans")
async def get_spans(source_id: str, request: Request, actor: ActorDep, evidence: EvidenceDep) -> dict[str, Any]:
    spans = await evidence.spans(actor.id, source_id)
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


@router.post("/projects/{project_id}/source-snapshots/{snapshot_id}/extract-claims", status_code=201)
async def extract_claims(
    project_id: str, snapshot_id: str, request: Request, actor: ActorDep
) -> dict[str, Any]:
    """Let the Evidence agent propose facts so the creator does not type them.

    The result is a *draft*: claims are ordinary project claims the creator can
    still correct, and content approval remains a separate human step.
    """
    from server.application.extraction import ClaimExtractionService

    service = ClaimExtractionService(request.app.state.uow_factory, request.app.state.provider)
    result = await service.extract_and_save(actor.id, project_id, snapshot_id)
    return envelope(
        {
            "claims": [
                {
                    "statement": claim.statement,
                    "content_type": claim.content_type,
                    "evidence_span_ids": list(claim.evidence_span_ids),
                    "qualifier": claim.qualifier,
                }
                for claim in result.claims
            ],
            "gaps": list(result.gaps),
            "ordering_facts": list(result.ordering_facts),
            "model": result.model,
            "cost_status": result.cost_status,
        },
        request,
    )


@router.get("/projects/{project_id}/claims")
async def get_claims(project_id: str, request: Request, actor: ActorDep, evidence: EvidenceDep) -> dict[str, Any]:
    claims = await evidence.claims(actor.id, project_id)
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


@router.post("/projects/{project_id}/claims", status_code=201)
async def add_claims(
    project_id: str, body: ClaimsRequest, request: Request, actor: ActorDep, evidence: EvidenceDep
) -> dict[str, Any]:
    claims = await evidence.add_claims(actor.id, project_id, [claim.model_dump() for claim in body.claims])
    return envelope(
        [{"id": claim.id, "revision": claim.revision, "content_type": claim.content_type} for claim in claims],
        request,
    )


@router.get("/projects/{project_id}/source-snapshots")
async def list_snapshots(
    project_id: str, request: Request, actor: ActorDep, evidence: EvidenceDep
) -> dict[str, Any]:
    snapshots = await evidence.snapshots(actor.id, project_id)
    return envelope(
        [
            {
                "id": snapshot.id,
                "sha256": snapshot.sha256,
                "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
            }
            for snapshot in snapshots
        ],
        request,
    )


@router.post("/projects/{project_id}/source-snapshots", status_code=201)
async def create_snapshot(
    project_id: str, body: SnapshotRequest, request: Request, actor: ActorDep, evidence: EvidenceDep
) -> dict[str, Any]:
    snapshot = await evidence.freeze_snapshot(actor.id, project_id, body.source_ids)
    return envelope({"id": snapshot.id, "sha256": snapshot.sha256}, request)
