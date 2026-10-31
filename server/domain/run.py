"""Run lifecycle, stage ids and the generation budget (F06, state-machines).

The lifetime transitions are exhaustive here; persistence adapters may only
perform the transitions this module allows. Cost accounting keeps
actual/estimated/unknown apart and never writes an unknown cost as zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from .errors import Conflict, ValidationFailure

DEFAULT_LEASE_SECONDS = 30
MAX_MODEL_CALLS = 12
MAX_REPAIR_ROUNDS = 2


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES: frozenset[RunStatus] = frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED})
ACTIVE_STATUSES: frozenset[RunStatus] = frozenset({RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING_INPUT})

ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset(
        {RunStatus.RUNNING, RunStatus.WAITING_INPUT, RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
    ),
    RunStatus.WAITING_INPUT: frozenset({RunStatus.QUEUED, RunStatus.CANCELLED}),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


class Stage(StrEnum):
    PARSE = "parse"
    EXTRACT = "extract"
    PLAN = "plan"
    GENERATE = "generate"
    VALIDATE = "validate"
    PLAYTEST = "playtest"
    REPAIR = "repair"
    ASSEMBLE = "assemble"


class CostStatus(StrEnum):
    ACTUAL = "actual"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_transition(current: RunStatus, target: RunStatus) -> None:
    if target == current and current is RunStatus.RUNNING:
        return  # lease takeover keeps a running row running
    if target not in ALLOWED_TRANSITIONS[current]:
        raise Conflict(
            "INVALID_RUN_TRANSITION",
            f"任务状态不能从 {current} 变为 {target}。",
        )


@dataclass(slots=True)
class BudgetLedger:
    """Generation budget shared by every agent in one run (F10-R04).

    Reserving locks a slot before the provider call; settlement records the
    actual/estimated/unknown cost. A reservation can be released only when the
    call provably did not happen.
    """

    max_calls: int = MAX_MODEL_CALLS
    max_repair_rounds: int = MAX_REPAIR_ROUNDS
    calls_reserved: int = 0
    calls_settled: int = 0
    repair_rounds: int = 0

    @property
    def calls_in_flight(self) -> int:
        return self.calls_reserved - self.calls_settled

    @property
    def calls_available(self) -> int:
        return self.max_calls - self.calls_reserved

    def reserve_call(self, count: int = 1) -> None:
        if count < 1:
            raise ValidationFailure("INVALID_RESERVATION", "预留次数必须为正整数。")
        if self.calls_reserved + count > self.max_calls:
            raise Conflict(
                "BUDGET_EXHAUSTED",
                f"生成预算不足：已预留 {self.calls_reserved}/{self.max_calls} 次模型调用。",
            )
        self.calls_reserved += count

    def release_call(self, count: int = 1) -> None:
        if count < 1 or count > self.calls_in_flight:
            raise ValidationFailure("INVALID_RELEASE", "释放次数超出未结算的预留区间。")
        self.calls_reserved -= count

    def settle_call(self, count: int = 1) -> None:
        """Mark in-flight reservations as spent. Unknown outcomes still settle."""
        if count < 1 or count > self.calls_in_flight:
            raise ValidationFailure("INVALID_SETTLEMENT", "结算次数超出未结算的预留区间。")
        self.calls_settled += count

    def begin_repair_round(self) -> None:
        if self.repair_rounds >= self.max_repair_rounds:
            raise Conflict("REPAIR_LIMIT_REACHED", "已用尽两轮修复额度。")
        self.repair_rounds += 1


@dataclass(slots=True)
class Run:
    id: str
    project_id: str
    kind: str
    status: RunStatus
    stage: Stage
    input_hash: str
    source_snapshot_id: str | None = None
    base_version_id: str | None = None
    attempt: int = 1
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    fencing_token: int = 0
    last_sequence: int = 0
    budget: BudgetLedger = field(default_factory=BudgetLedger)
    error_code: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None

    def transition(self, target: RunStatus) -> None:
        ensure_transition(self.status, target)
        self.status = target
        if target in TERMINAL_STATUSES:
            self.finished_at = utcnow()
            self.lease_owner = None
            self.lease_expires_at = None

    def grant_lease(self, owner: str, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> int:
        """Take or renew the lease and return the new fencing token."""
        if self.status in TERMINAL_STATUSES:
            raise Conflict("RUN_TERMINAL", "任务已结束，不能占用租约。", object_id=self.id)
        self.lease_owner = owner
        self.lease_expires_at = utcnow() + timedelta(seconds=lease_seconds)
        self.fencing_token += 1
        return self.fencing_token

    def lease_is_valid(self, token: int, owner: str, now: datetime | None = None) -> bool:
        moment = now or utcnow()
        return (
            self.fencing_token == token
            and self.lease_owner == owner
            and self.lease_expires_at is not None
            and self.lease_expires_at > moment
            and self.status is RunStatus.RUNNING
        )

    def require_active_writer(self, token: int, owner: str, now: datetime | None = None) -> None:
        if self.status in TERMINAL_STATUSES:
            raise Conflict("RUN_TERMINAL", "任务已结束，迟到结果被拒绝。", object_id=self.id)
        if not self.lease_is_valid(token, owner, now):
            raise Conflict(
                "STALE_FENCING_TOKEN",
                "租约已失效或 token 过期，结果不得提交。",
                object_id=self.id,
            )


@dataclass(frozen=True, slots=True)
class ModelCall:
    id: str
    run_id: str | None
    agent_task_id: str | None
    provider: str
    model: str
    provider_request_id: str | None
    attempt: int
    status: str
    input_tokens: int | None
    output_tokens: int | None
    currency: str | None
    cost_micros: int | None
    cost_status: CostStatus
    started_at: datetime | None
    finished_at: datetime | None

    def __post_init__(self) -> None:
        if self.cost_status is CostStatus.UNKNOWN and self.cost_micros is not None:
            raise ValidationFailure("INVALID_COST", "未知费用不得填写具体金额。")
        if self.cost_status is CostStatus.ACTUAL and self.cost_micros is None:
            raise ValidationFailure("INVALID_COST", "实际费用必须包含金额。")
