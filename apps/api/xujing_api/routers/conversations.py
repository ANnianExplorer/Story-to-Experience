"""Creator and Guide conversation routes (F11)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from server.domain.shared.errors import NotFound, ValidationFailure
from xujing_api.core.errors import envelope
from xujing_api.deps import ActorDep, ConversationsDep
from xujing_api.schemas.requests import ConversationCreate, TurnRequest

router = APIRouter(prefix="/api/v1", tags=["conversations"])


@router.post("/projects/{project_id}/conversations", status_code=201)
async def create_conversation(
    project_id: str, body: ConversationCreate, request: Request, actor: ActorDep, conversations: ConversationsDep
) -> dict[str, Any]:
    session = await conversations.create_creator_session(actor.id, project_id, base_version_id=body.base_version_id)
    return envelope({"conversation_id": session.id, "kind": session.kind.value}, request)


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str, request: Request, actor: ActorDep, conversations: ConversationsDep
) -> dict[str, Any]:
    session = await conversations.get_session(actor.id, conversation_id)
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


@router.post("/conversations/{conversation_id}/turns", status_code=202)
async def submit_turn(
    conversation_id: str, body: TurnRequest, request: Request, actor: ActorDep, conversations: ConversationsDep
) -> dict[str, Any]:
    turn, reused = await conversations.submit_turn(
        actor.id,
        conversation_id,
        client_turn_id=body.client_turn_id,
        message=body.message,
        scene_id=body.scene_id,
        flags=body.flags,
    )
    return envelope({"turn_id": turn.id, "status": turn.status.value, "reused": reused}, request)


@router.post("/conversation-turns/{turn_id}/run")
async def execute_turn(
    turn_id: str, request: Request, actor: ActorDep, conversations: ConversationsDep, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Execute a queued turn synchronously and return its public event log.

    Production deploys stream from a background task; this endpoint keeps the
    documented turn contract observable end-to-end in development.
    """
    async with request.app.state.uow_factory() as uow:
        turn = await uow.conversations.get_turn(turn_id)
        if turn is None:
            raise NotFound(object_id=turn_id)
        session = await uow.conversations.get_session(turn.session_id)
        if session is None or session.actor_id != actor.id:
            raise NotFound(object_id=turn_id)
    execution = await conversations.execute_turn(
        turn_id, scene_id=(body or {}).get("scene_id"), flags=(body or {}).get("flags")
    )
    result = execution.turn
    return envelope(
        {
            "turn_id": result.id,
            "status": result.status.value,
            "final_text": result.final_text,
            "answerability": result.answerability.value if result.answerability else None,
            "citations": [citation.to_payload() for citation in result.citations],
            "suggested_actions": [action.to_payload() for action in result.suggested_actions],
            "cost_status": result.cost_status,
            "events": [
                {"sequence": event.sequence, "type": event.type, "payload": event.payload}
                for event in execution.events
            ],
        },
        request,
    )


@router.post("/experience-sessions/{session_id}/conversations", status_code=201)
async def create_guide_conversation(
    session_id: str, request: Request, actor: ActorDep, conversations: ConversationsDep
) -> dict[str, Any]:
    """Open a Guide conversation bound to one fixed shared version (F11-T03)."""
    session = await conversations.create_guide_session_from_experience(
        experience_session_id=session_id, actor_id=actor.id
    )
    return envelope(
        {
            "conversation_id": session.id,
            "kind": session.kind.value,
            "version_id": session.version_id,
        },
        request,
    )


@router.get("/conversation-turns/{turn_id}/events")
async def turn_events(turn_id: str, request: Request, actor: ActorDep) -> dict[str, Any]:
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


@router.post("/conversation-turns/{turn_id}/cancel")
async def cancel_turn(
    turn_id: str, request: Request, actor: ActorDep, conversations: ConversationsDep
) -> dict[str, Any]:
    turn = await conversations.cancel_turn(actor.id, turn_id)
    return envelope({"turn_id": turn.id, "status": turn.status.value}, request)
