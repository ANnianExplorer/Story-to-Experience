"""Version reads, review, stable promotion, shares and exports (F07/F08)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from server.domain.shared.errors import NotFound, ValidationFailure
from xujing_api.core.errors import envelope
from xujing_api.deps import ActorDep, DeliveryDep, ProjectsDep
from xujing_api.schemas.requests import ExportRequest, ReviewRequest, ShareRequest, StableRequest

router = APIRouter(prefix="/api/v1", tags=["delivery"])


async def _owned_version(request: Request, actor_id: str, version_id: str) -> dict[str, Any]:
    async with request.app.state.uow_factory() as uow:
        version = await uow.versions.get(version_id)
        if version is None:
            raise NotFound(object_id=version_id)
        project = await uow.projects.get(version["project_id"])
        if project is None or project.owner_id != actor_id:
            raise NotFound(object_id=version_id)
    return version


@router.get("/versions/{version_id}")
async def get_version(version_id: str, request: Request, actor: ActorDep) -> dict[str, Any]:
    return envelope(await _owned_version(request, actor.id, version_id), request)


@router.get("/projects/{project_id}/versions")
async def list_versions(project_id: str, request: Request, actor: ActorDep, projects: ProjectsDep) -> dict[str, Any]:
    project = await projects.get(actor.id, project_id)
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


@router.post("/versions/{version_id}/reviews", status_code=201)
async def submit_review(
    version_id: str, body: ReviewRequest, request: Request, actor: ActorDep, delivery: DeliveryDep
) -> dict[str, Any]:
    review = await delivery.submit_review(
        actor.id,
        version_id,
        decision=body.decision,
        notes=body.notes,
        coverage_claim_ids=body.coverage_claim_ids,
        expected_semantic_hash=body.expected_semantic_hash,
        actor_kind=actor.kind,
    )
    return envelope({"id": review.id, "decision": review.decision}, request)


@router.post("/projects/{project_id}/stable")
async def promote(project_id: str, body: StableRequest, request: Request, actor: ActorDep, delivery: DeliveryDep) -> dict[str, Any]:
    return envelope(await delivery.promote_stable(actor.id, project_id, body.version_id), request)


@router.post("/versions/{version_id}/shares", status_code=201)
async def create_share(version_id: str, body: ShareRequest, request: Request, actor: ActorDep, delivery: DeliveryDep) -> dict[str, Any]:
    if body.version_id != version_id:
        raise ValidationFailure("VERSION_MISMATCH", "路径与请求体的版本不一致。")
    version = await _owned_version(request, actor.id, version_id)
    share, token = await delivery.create_share(
        actor.id, version["project_id"], version_id=version_id, license_ack=body.license_ack, hours=body.hours
    )
    return envelope({"share_id": share.id, "token": token, "expires_at": share.expires_at.isoformat()}, request)


@router.delete("/shares/{share_id}", status_code=204)
async def revoke_share(share_id: str, request: Request, actor: ActorDep, delivery: DeliveryDep) -> None:
    await delivery.revoke_share(actor.id, share_id)


@router.get("/share/{token}/manifest")
async def share_manifest(token: str, request: Request, delivery: DeliveryDep) -> dict[str, Any]:
    resolved = await delivery.resolve_share(token)
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


@router.post("/share/{token}/sessions", status_code=201)
async def share_session(token: str, request: Request, actor: ActorDep, delivery: DeliveryDep) -> dict[str, Any]:
    return envelope(await delivery.create_experience_session(token, actor.id), request)


@router.post("/versions/{version_id}/exports", status_code=202)
async def export_version(
    version_id: str, body: ExportRequest, request: Request, actor: ActorDep, delivery: DeliveryDep
) -> dict[str, Any]:
    return envelope(await delivery.export_bundle(actor.id, version_id, mode=body.mode), request)
