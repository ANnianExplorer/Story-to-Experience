from __future__ import annotations

import pytest

from server.domain.agents import (
    AGENT_PROTOCOL_VERSION,
    AgentIssue,
    AgentResult,
    AgentRole,
    AgentRunStatus,
    AgentTaskEnvelope,
    AgentUsage,
    Plan,
    PlanTask,
    allowed_tools,
)
from server.domain.errors import Conflict, ValidationFailure


def envelope(**overrides: object) -> AgentTaskEnvelope:
    values: dict[str, object] = {
        "protocol_version": AGENT_PROTOCOL_VERSION,
        "agent_id": "evidence-agent",
        "task_id": "t-evidence",
        "parent_task_id": None,
        "project_id": "p1",
        "run_id": "r1",
        "role": AgentRole.EVIDENCE,
        "profile_version": "1.0.0",
        "input_refs": ("snapshot:abc",),
        "input_hash": "f" * 64,
        "allowed_tools": ("read_snapshot", "retrieve_evidence"),
        "budget_ref": "run:r1",
        "fencing_token": 3,
        "objective": "提取事实与缺口",
    }
    values.update(overrides)
    return AgentTaskEnvelope(**values)  # type: ignore[arg-type]


def test_tool_matrix_rejects_tools_outside_role() -> None:
    with pytest.raises(ValidationFailure) as error:
        allowed_tools(AgentRole.GUIDE, ["apply_patch"])
    assert error.value.code == "TOOL_NOT_ALLOWED"
    with pytest.raises(ValidationFailure):
        allowed_tools(AgentRole.BUILDER, ["read_snapshot", "read_snapshot"])


def test_envelope_rejects_unsupported_protocol_and_cross_scope() -> None:
    with pytest.raises(ValidationFailure) as error:
        envelope(protocol_version="0.9.0")
    assert error.value.code == "PROTOCOL_VERSION_UNSUPPORTED"
    with pytest.raises(Conflict) as scope_error:
        envelope().check_same_scope(project_id="p2", run_id="r1")
    assert scope_error.value.code == "HANDOFF_SCOPE_MISMATCH"


def test_review_agent_cannot_approve_content() -> None:
    with pytest.raises(ValidationFailure) as error:
        AgentResult(
            protocol_version=AGENT_PROTOCOL_VERSION,
            task_id="t-review",
            agent_id="review-agent",
            role=AgentRole.REVIEW,
            status=AgentRunStatus.SUCCEEDED,
            artifact_refs=("artifact-1",),
            citation_refs=(),
            issues=(AgentIssue(code="CONTENT_APPROVED", message="批准"),),
            usage=AgentUsage(model_calls=1, input_tokens=1, output_tokens=1, cost_status="unknown"),
            handoff_to=(),
        )
    assert error.value.code == "REVIEW_CANNOT_APPROVE"


def test_success_requires_artifact_reference() -> None:
    with pytest.raises(ValidationFailure):
        AgentResult(
            protocol_version=AGENT_PROTOCOL_VERSION,
            task_id="t1",
            agent_id="a1",
            role=AgentRole.EVIDENCE,
            status=AgentRunStatus.SUCCEEDED,
            artifact_refs=(),
            citation_refs=(),
            issues=(),
            usage=AgentUsage(model_calls=1, input_tokens=1, output_tokens=1, cost_status="unknown"),
            handoff_to=(),
        )


def make_task(task_id: str, role: AgentRole, depends: tuple[str, ...] = ("t1",)) -> PlanTask:
    return PlanTask(
        task_id=task_id,
        role=role,
        objective=f"{role} 目标",
        depends_on=depends,
        input_refs=("snapshot:abc",),
        allowed_tools=tuple(sorted(__import__("server.domain.agents", fromlist=["TOOL_MATRIX"]).TOOL_MATRIX[role])),
        expected_output=f"{role} 产物",
    )


def test_plan_orders_dependencies_and_hashes_stably() -> None:
    plan = Plan(
        protocol_version=AGENT_PROTOCOL_VERSION,
        project_id="p1",
        run_id="r1",
        tasks=(
            make_task("t1", AgentRole.EVIDENCE, depends=()),
            make_task("t2", AgentRole.DESIGNER, depends=("t1",)),
            make_task("t3", AgentRole.BUILDER, depends=("t2",)),
            make_task("t4", AgentRole.REVIEW, depends=("t3",)),
        ),
    )
    order = [task.task_id for task in plan.topological_order()]
    assert order == ["t1", "t2", "t3", "t4"]
    assert plan.hash() == plan.hash()
    plan.ensure_required_chain()


def test_plan_rejects_cycles_and_missing_chain() -> None:
    with pytest.raises(ValidationFailure) as error:
        Plan(
            protocol_version=AGENT_PROTOCOL_VERSION,
            project_id="p1",
            run_id="r1",
            tasks=(
                make_task("t1", AgentRole.EVIDENCE, depends=("t2",)),
                make_task("t2", AgentRole.DESIGNER, depends=("t1",)),
            ),
        )
    assert error.value.code == "PLAN_CYCLE"
    incomplete = Plan(
        protocol_version=AGENT_PROTOCOL_VERSION,
        project_id="p1",
        run_id="r1",
        tasks=(make_task("t1", AgentRole.EVIDENCE, depends=()),),
    )
    with pytest.raises(ValidationFailure) as incomplete_error:
        incomplete.ensure_required_chain()
    assert incomplete_error.value.code == "PLAN_INCOMPLETE"


def test_plan_dependency_on_unknown_task_is_rejected() -> None:
    with pytest.raises(ValidationFailure):
        Plan(
            protocol_version=AGENT_PROTOCOL_VERSION,
            project_id="p1",
            run_id="r1",
            tasks=(make_task("t1", AgentRole.EVIDENCE, depends=("nope",)),),
        )
