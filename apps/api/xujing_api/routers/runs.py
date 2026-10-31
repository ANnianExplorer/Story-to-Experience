"""Run submission, event streaming, cancellation and agent trace routes (F06/F10)."""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.responses import StreamingResponse

from server.application.generation.orchestration import OrchestrationService
from server.domain.shared.errors import ValidationFailure
from xujing_api.core.errors import envelope
from xujing_api.deps import ActorDep, OrchestrationDep, RunsDep
from xujing_api.schemas.requests import RunRequest

router = APIRouter(prefix="/api/v1", tags=["runs"])


async def _run_in_background(service: OrchestrationService, run_id: str, instruction: str) -> None:
    """Execute a generation run. Failures are already persisted on the run row."""
    try:
        await service.execute(run_id, actor_instruction=instruction)
    except Exception:  # pragma: no cover - the run row carries the failure state
        pass


@router.post("/projects/{project_id}/runs", status_code=202)
async def submit_run(
    project_id: str,
    body: RunRequest,
    request: Request,
    background: BackgroundTasks,
    actor: ActorDep,
    runs: RunsDep,
    orchestration: OrchestrationDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    if not idempotency_key:
        raise ValidationFailure("IDEMPOTENCY_KEY_REQUIRED", "提交生成必须携带 Idempotency-Key。")
    submission = await runs.submit_generation(
        actor.id,
        project_id,
        source_snapshot_id=body.source_snapshot_id,
        brief_revision=body.brief_revision,
        idempotency_key=idempotency_key,
    )
    if submission.created and body.auto_continue:
        background.add_task(_run_in_background, orchestration, submission.run_id, body.instruction)
    return envelope({"run_id": submission.run_id, "created": submission.created}, request)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request, actor: ActorDep, runs: RunsDep) -> dict[str, Any]:
    run = await runs.get(actor.id, run_id)
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


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, actor: ActorDep, runs: RunsDep, after: int = 0) -> StreamingResponse:
    events = await runs.events(actor.id, run_id, after)

    async def stream() -> AsyncIterator[bytes]:
        for event in events:
            yield (
                f"id: {event['sequence']}\n"
                f"event: stage\n"
                f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            ).encode("utf-8")
            await asyncio.sleep(0)
        yield b": heartbeat\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, request: Request, actor: ActorDep, runs: RunsDep) -> dict[str, Any]:
    run = await runs.cancel(actor.id, run_id)
    return envelope({"id": run.id, "status": run.status.value}, request)


@router.get("/runs/{run_id}/agent-tasks")
async def agent_tasks(run_id: str, request: Request, actor: ActorDep, runs: RunsDep) -> dict[str, Any]:
    await runs.get(actor.id, run_id)  # authorization first
    async with request.app.state.uow_factory() as uow:
        tasks = await uow.agents.tasks_for(run_id)
        plan = await uow.agents.get_plan(run_id)
    return envelope({"plan": plan, "tasks": tasks}, request)
