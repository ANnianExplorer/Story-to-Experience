"""Run use cases: idempotent submission, leases, events, cancellation (F06)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from server.application.ports import ScopeFactory
from server.domain.shared.canonical_json import canonical_sha256
from server.domain.shared.errors import Conflict, NotFound, ValidationFailure
from server.domain.shared.ids import new_id
from server.domain.runs import Run, RunStatus, Stage, utcnow

GENERATION_BUDGET_CALLS = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class RunSubmission:
    run_id: str
    created: bool


class RunService:
    def __init__(self, uow: ScopeFactory) -> None:
        self._uow = uow

    async def submit_generation(
        self,
        actor_id: str,
        project_id: str,
        *,
        source_snapshot_id: str,
        brief_revision: int,
        idempotency_key: str,
    ) -> RunSubmission:
        request_hash = canonical_sha256(
            {
                "kind": "generate",
                "project_id": project_id,
                "source_snapshot_id": source_snapshot_id,
                "brief_revision": brief_revision,
            }
        )
        scope = f"POST:/projects/{project_id}/runs"
        async with self._uow() as uow:
            project = await uow.projects.get(project_id)
            if project is None:
                raise NotFound(object_id=project_id)
            project.assert_owned_by(actor_id)
            if project.brief_revision != brief_revision:
                raise Conflict("BRIEF_REVISION_CONFLICT", "简报版本已变化，请重新加载。", object_id=project_id)

            existing = await uow.idempotency.get(actor_id, scope, idempotency_key)
            if existing is not None:
                if existing["request_hash"] != request_hash:
                    raise Conflict("IDEMPOTENCY_CONFLICT", "相同幂等键不能携带不同请求内容。")
                return RunSubmission(run_id=str(existing["resource_id"]), created=False)

            active = await uow.runs.active_for_project(project_id)
            if active is not None:
                raise Conflict("ACTIVE_RUN", "项目已有进行中的生成任务。", object_id=active.id)

            snapshot = await uow.evidence.get_snapshot(source_snapshot_id)
            if snapshot is None or snapshot.project_id != project_id:
                raise NotFound(object_id=source_snapshot_id)

            run = Run(
                id=new_id(),
                project_id=project_id,
                kind="generate",
                status=RunStatus.QUEUED,
                stage=Stage.PLAN,
                input_hash=canonical_sha256(
                    {"snapshot": snapshot.sha256, "brief": project.brief.to_payload(), "brief_revision": brief_revision}
                ),
                source_snapshot_id=source_snapshot_id,
                created_at=_now(),
            )
            await uow.runs.create(run)
            await uow.idempotency.put(
                actor_id=actor_id,
                scope=scope,
                key=idempotency_key,
                request_hash=request_hash,
                resource_id=run.id,
                response={"run_id": run.id},
            )
            await uow.runs.append_event(run.id, "queued", {"stage": run.stage.value})
            await uow.commit()
        return RunSubmission(run_id=run.id, created=True)

    async def get(self, actor_id: str, run_id: str) -> Run:
        async with self._uow() as uow:
            run = await uow.runs.get(run_id)
            if run is None:
                raise NotFound(object_id=run_id)
            project = await uow.projects.get(run.project_id)
            if project is None or project.owner_id != actor_id:
                raise NotFound(object_id=run_id)
        return run

    async def events(self, actor_id: str, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        await self.get(actor_id, run_id)
        async with self._uow() as uow:
            return await uow.runs.events_since(run_id, after)

    async def cancel(self, actor_id: str, run_id: str) -> Run:
        async with self._uow() as uow:
            run = await uow.runs.get_for_update(run_id)
            if run is None:
                raise NotFound(object_id=run_id)
            project = await uow.projects.get(run.project_id)
            if project is None or project.owner_id != actor_id:
                raise NotFound(object_id=run_id)
            if run.status is RunStatus.CANCELLED:
                return run
            if run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED):
                return run  # idempotent: report the current terminal snapshot
            run.transition(RunStatus.CANCELLED)
            run.fencing_token += 1
            run.lease_owner = None
            run.lease_expires_at = None
            await uow.runs.save(run)
            await uow.runs.append_event(run_id, "cancelled", {"stage": run.stage.value})
            await uow.commit()
        return run

    async def claim(self, run_id: str, owner: str, *, lease_seconds: int = 30) -> Run:
        """Take the lease and return the run. Raises Conflict when not claimable."""
        async with self._uow() as uow:
            run = await uow.runs.get_for_update(run_id)
            if run is None:
                raise NotFound(object_id=run_id)
            if run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
                raise Conflict("RUN_TERMINAL", "任务已结束。", object_id=run_id)
            if run.status is RunStatus.QUEUED:
                run.transition(RunStatus.RUNNING)
            elif run.status is RunStatus.WAITING_INPUT:
                raise Conflict("RUN_WAITING_INPUT", "任务等待补充输入，不能执行。", object_id=run_id)
            token = run.grant_lease(owner, lease_seconds=lease_seconds)
            await uow.runs.save(run)
            await uow.runs.append_event(run_id, "claimed", {"owner": owner, "fencing_token": token})
            await uow.commit()
        return run

    async def renew_lease(self, run_id: str, owner: str, token: int, *, lease_seconds: int = 30) -> int:
        """Heartbeat: extend the lease without advancing the fencing token.

        Only the holder of the current token may renew, so a worker that already
        lost the run cannot keep it alive. The token is unchanged because the
        lease is the same writer's claim, not a takeover.
        """
        async with self._uow() as uow:
            run = await uow.runs.get_for_update(run_id)
            if run is None:
                raise NotFound(object_id=run_id)
            if run.fencing_token != token or run.lease_owner != owner:
                raise Conflict("STALE_FENCING_TOKEN", "租约已被他人接管。", object_id=run_id)
            if run.status is not RunStatus.RUNNING:
                raise Conflict("RUN_NOT_RUNNING", "任务不在运行中，无法续租。", object_id=run_id)
            run.lease_expires_at = utcnow() + timedelta(seconds=lease_seconds)
            await uow.runs.save(run)
            await uow.commit()
        return token

