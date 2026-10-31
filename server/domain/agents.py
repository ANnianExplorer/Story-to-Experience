"""Agent identities, plans, envelopes and results (F10).

AgentTaskEnvelope/AgentResult are versioned structured messages. Parameters are
never authorisation: the application service re-checks project, run, budget and
tool scope before dispatching. The protocol version is pinned so a handoff from
an older producer is rejected instead of silently coerced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from .shared.canonical_json import canonical_sha256
from .shared.errors import Conflict, ValidationFailure

AGENT_PROTOCOL_VERSION = "1.0.0"
MAX_PLAN_TASKS = 24
MAX_TOOL_COUNT = 8


class AgentRole(StrEnum):
    COORDINATOR = "coordinator"
    EVIDENCE = "evidence"
    DESIGNER = "experience_designer"
    BUILDER = "experience_builder"
    REVIEW = "review"
    REPAIR = "repair"
    GUIDE = "guide"


# Capability matrix (F10-R01). A missing entry means the tool is not allowed.
TOOL_MATRIX: dict[AgentRole, frozenset[str]] = {
    AgentRole.COORDINATOR: frozenset({"read_project", "read_snapshot"}),
    AgentRole.EVIDENCE: frozenset({"read_snapshot", "retrieve_evidence"}),
    AgentRole.DESIGNER: frozenset({"read_snapshot", "read_blueprint", "retrieve_evidence", "get_mechanic_catalog"}),
    AgentRole.BUILDER: frozenset({"read_blueprint", "get_mechanic_catalog", "validate_spec", "check_reachability"}),
    AgentRole.REVIEW: frozenset({"read_blueprint", "read_candidate", "retrieve_evidence", "validate_spec"}),
    AgentRole.REPAIR: frozenset({"read_candidate", "read_review_issues", "apply_patch", "validate_spec", "check_reachability"}),
    AgentRole.GUIDE: frozenset({"read_published_version", "retrieve_public_evidence", "read_scene_context"}),
}

OUTPUT_KIND: dict[AgentRole, str] = {
    AgentRole.COORDINATOR: "plan",
    AgentRole.EVIDENCE: "evidence_bundle",
    AgentRole.DESIGNER: "blueprint",
    AgentRole.BUILDER: "candidate",
    AgentRole.REVIEW: "review_findings",
    AgentRole.REPAIR: "candidate",
    AgentRole.GUIDE: "conversation_answer",
}

PROFILE_VERSION = "1.0.0"
PROFILES: dict[AgentRole, str] = {
    AgentRole.COORDINATOR: PROFILE_VERSION,
    AgentRole.EVIDENCE: PROFILE_VERSION,
    AgentRole.DESIGNER: PROFILE_VERSION,
    AgentRole.BUILDER: PROFILE_VERSION,
    AgentRole.REVIEW: PROFILE_VERSION,
    AgentRole.REPAIR: PROFILE_VERSION,
    AgentRole.GUIDE: PROFILE_VERSION,
}


class AgentTaskStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_AGENT_STATUSES = frozenset(
    {AgentTaskStatus.SUCCEEDED, AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED}
)


class AgentRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_INPUT = "needs_input"


def allowed_tools(role: AgentRole, requested: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    granted = TOOL_MATRIX[role]
    for tool in requested:
        if tool not in granted:
            raise ValidationFailure(
                "TOOL_NOT_ALLOWED",
                f"{role} 无权使用工具 {tool}。",
                {"role": role.value, "tool": tool},
            )
    if len(set(requested)) != len(requested):
        raise ValidationFailure("TOOL_DUPLICATE", "工具白名单不能重复。")
    if len(requested) > MAX_TOOL_COUNT:
        raise ValidationFailure("TOOL_LIMIT", f"工具白名单最多 {MAX_TOOL_COUNT} 项。")
    return tuple(requested)


@dataclass(frozen=True, slots=True)
class AgentTaskEnvelope:
    protocol_version: str
    agent_id: str
    task_id: str
    parent_task_id: str | None
    project_id: str
    run_id: str
    role: AgentRole
    profile_version: str
    input_refs: tuple[str, ...]
    input_hash: str
    allowed_tools: tuple[str, ...]
    budget_ref: str
    fencing_token: int
    objective: str

    def __post_init__(self) -> None:
        if self.protocol_version != AGENT_PROTOCOL_VERSION:
            raise ValidationFailure(
                "PROTOCOL_VERSION_UNSUPPORTED",
                f"仅支持 agent 协议 {AGENT_PROTOCOL_VERSION}。",
                {"received": self.protocol_version},
            )
        if not self.agent_id or not self.task_id:
            raise ValidationFailure("INVALID_ENVELOPE", "agent_id 和 task_id 不能为空。")
        if not self.input_hash:
            raise ValidationFailure("INVALID_ENVELOPE", "交接必须携带 input_hash。")
        allowed_tools(self.role, self.allowed_tools)
        if not self.objective.strip():
            raise ValidationFailure("INVALID_ENVELOPE", "子任务目标不能为空。")

    def to_payload(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "role": self.role.value,
            "profile_version": self.profile_version,
            "input_refs": list(self.input_refs),
            "input_hash": self.input_hash,
            "allowed_tools": list(self.allowed_tools),
            "budget_ref": self.budget_ref,
            "fencing_token": self.fencing_token,
            "objective": self.objective,
        }

    def check_same_scope(self, *, project_id: str, run_id: str) -> None:
        if self.project_id != project_id or self.run_id != run_id:
            raise Conflict(
                "HANDOFF_SCOPE_MISMATCH",
                "交接消息的项目或任务作用域不匹配。",
                object_id=self.task_id,
            )


@dataclass(frozen=True, slots=True)
class AgentIssue:
    code: str
    message: str
    severity: Literal["error", "warning", "info"] = "error"
    artifact_ref: str | None = None
    claim_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentUsage:
    model_calls: int
    input_tokens: int
    output_tokens: int
    cost_status: str
    cost_micros: int | None = None
    currency: str | None = None


@dataclass(frozen=True, slots=True)
class AgentResult:
    protocol_version: str
    task_id: str
    agent_id: str
    role: AgentRole
    status: AgentRunStatus
    artifact_refs: tuple[str, ...]
    citation_refs: tuple[str, ...]
    issues: tuple[AgentIssue, ...]
    usage: AgentUsage
    handoff_to: tuple[AgentRole, ...]
    reason_code: str | None = None
    artifact_payload: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.protocol_version != AGENT_PROTOCOL_VERSION:
            raise ValidationFailure("PROTOCOL_VERSION_UNSUPPORTED", "结果协议版本不支持。")
        if self.status is AgentRunStatus.SUCCEEDED and not self.artifact_refs:
            raise ValidationFailure("INVALID_RESULT", "成功的子任务必须提交产物引用。")
        if self.role is AgentRole.REVIEW and any(
            issue.code == "CONTENT_APPROVED" for issue in self.issues
        ):
            raise ValidationFailure(
                "REVIEW_CANNOT_APPROVE",
                "审校 Agent 不能给出内容批准，只能提交问题与建议。",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "role": self.role.value,
            "status": self.status.value,
            "artifact_refs": list(self.artifact_refs),
            "citation_refs": list(self.citation_refs),
            "issues": [
                {
                    "code": issue.code,
                    "message": issue.message,
                    "severity": issue.severity,
                    "artifact_ref": issue.artifact_ref,
                    "claim_ids": list(issue.claim_ids),
                }
                for issue in self.issues
            ],
            "usage": {
                "model_calls": self.usage.model_calls,
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "cost_status": self.usage.cost_status,
                "cost_micros": self.usage.cost_micros,
                "currency": self.usage.currency,
            },
            "handoff_to": [role.value for role in self.handoff_to],
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class PlanTask:
    task_id: str
    role: AgentRole
    objective: str
    depends_on: tuple[str, ...]
    input_refs: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    expected_output: str

    def __post_init__(self) -> None:
        if not self.objective.strip():
            raise ValidationFailure("INVALID_PLAN", "计划子任务必须有目标。")
        allowed_tools(self.role, self.allowed_tools)
        if not self.expected_output.strip():
            raise ValidationFailure("INVALID_PLAN", "计划子任务必须声明预期产物。")


@dataclass(frozen=True, slots=True)
class Plan:
    """Dependency-ordered agent plan produced by the Coordinator."""

    protocol_version: str
    project_id: str
    run_id: str
    tasks: tuple[PlanTask, ...]
    notes: str = ""
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.protocol_version != AGENT_PROTOCOL_VERSION:
            raise ValidationFailure("PROTOCOL_VERSION_UNSUPPORTED", "计划协议版本不支持。")
        if not 1 <= len(self.tasks) <= MAX_PLAN_TASKS:
            raise ValidationFailure("INVALID_PLAN", f"计划子任务数量需在 1—{MAX_PLAN_TASKS} 之间。")
        ids = [task.task_id for task in self.tasks]
        if len(set(ids)) != len(ids):
            raise ValidationFailure("INVALID_PLAN", "计划子任务 ID 必须唯一。")
        known = set(ids)
        for task in self.tasks:
            unknown = set(task.depends_on) - known
            if unknown:
                raise ValidationFailure("INVALID_PLAN", "计划依赖了不存在的子任务。", {"unknown": sorted(unknown)})
            if task.task_id in task.depends_on:
                raise ValidationFailure("INVALID_PLAN", "子任务不能依赖自身。")
        if self.has_cycle():
            raise ValidationFailure("PLAN_CYCLE", "计划依赖图存在环。")

    def has_cycle(self) -> bool:
        graph = {task.task_id: task.depends_on for task in self.tasks}
        state: dict[str, int] = {}

        def visit(node: str) -> bool:
            if state.get(node) == 1:
                return True
            if state.get(node) == 2:
                return False
            state[node] = 1
            for dep in graph[node]:
                if visit(dep):
                    return True
            state[node] = 2
            return False

        return any(visit(node) for node in graph)

    def required_roles(self) -> set[AgentRole]:
        return {task.role for task in self.tasks}

    def topological_order(self) -> tuple[PlanTask, ...]:
        by_id = {task.task_id: task for task in self.tasks}
        remaining = dict(by_id)
        ordered: list[PlanTask] = []
        while remaining:
            ready = [task for task in remaining.values() if all(dep not in remaining for dep in task.depends_on)]
            if not ready:
                raise ValidationFailure("PLAN_CYCLE", "计划依赖图存在环。")
            ready.sort(key=lambda task: task.task_id)
            for task in ready:
                ordered.append(task)
                remaining.pop(task.task_id)
        return tuple(ordered)

    def hash(self) -> str:
        return canonical_sha256(
            {
                "protocol_version": self.protocol_version,
                "project_id": self.project_id,
                "run_id": self.run_id,
                "tasks": [
                    {
                        "task_id": task.task_id,
                        "role": task.role.value,
                        "objective": task.objective,
                        "depends_on": sorted(task.depends_on),
                        "input_refs": list(task.input_refs),
                        "allowed_tools": sorted(task.allowed_tools),
                        "expected_output": task.expected_output,
                    }
                    for task in self.tasks
                ],
                "notes": self.notes,
            }
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "role": task.role.value,
                    "objective": task.objective,
                    "depends_on": list(task.depends_on),
                    "input_refs": list(task.input_refs),
                    "allowed_tools": list(task.allowed_tools),
                    "expected_output": task.expected_output,
                }
                for task in self.tasks
            ],
            "notes": self.notes,
            "plan_hash": self.hash(),
        }

    def ensure_required_chain(self) -> None:
        """AT-01: a real generation plan must include the four specialised tasks."""
        required = {AgentRole.EVIDENCE, AgentRole.DESIGNER, AgentRole.BUILDER, AgentRole.REVIEW}
        missing = required - self.required_roles()
        if missing:
            raise ValidationFailure(
                "PLAN_INCOMPLETE",
                "生成计划缺少必需的专业 Agent 子任务。",
                {"missing": sorted(role.value for role in missing)},
            )
