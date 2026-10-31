"""Shared FastAPI dependencies: identity and application services.

Routers receive services through these dependencies; they never construct
adapters themselves. The composition root (``create_app``) puts the built
adapters on ``app.state``, so tests can inject fakes without patching imports.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from server.application.conversations.service import ConversationService
from server.application.delivery import DeliveryService
from server.application.evidence import EvidenceService
from server.application.generation.orchestration import OrchestrationService
from server.application.projects import ProjectService
from server.application.runs import RunService
from xujing_api.core.identity import Actor


async def current_actor(request: Request) -> Actor:
    return await request.app.state.identity.actor_from_request(request)


def project_service(request: Request) -> ProjectService:
    return ProjectService(request.app.state.uow_factory)


def evidence_service(request: Request) -> EvidenceService:
    return EvidenceService(request.app.state.uow_factory, request.app.state.blobs)


def run_service(request: Request) -> RunService:
    return RunService(request.app.state.uow_factory)


def orchestration_service(request: Request) -> OrchestrationService:
    return OrchestrationService(
        request.app.state.uow_factory,
        request.app.state.provider,
        request.app.state.validator,
        provider_is_mock=getattr(request.app.state.provider, "is_mock", False),
    )


def conversation_service(request: Request) -> ConversationService:
    return ConversationService(
        request.app.state.uow_factory,
        request.app.state.provider,
        provider_is_mock=getattr(request.app.state.provider, "is_mock", False),
    )


def delivery_service(request: Request) -> DeliveryService:
    return DeliveryService(request.app.state.uow_factory)


ActorDep = Annotated[Actor, Depends(current_actor)]
ProjectsDep = Annotated[ProjectService, Depends(project_service)]
EvidenceDep = Annotated[EvidenceService, Depends(evidence_service)]
RunsDep = Annotated[RunService, Depends(run_service)]
OrchestrationDep = Annotated[OrchestrationService, Depends(orchestration_service)]
ConversationsDep = Annotated[ConversationService, Depends(conversation_service)]
DeliveryDep = Annotated[DeliveryService, Depends(delivery_service)]
