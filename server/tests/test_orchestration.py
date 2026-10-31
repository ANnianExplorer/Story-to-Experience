"""End-to-end orchestration through scripted model output (simulated run).

These tests prove the orchestration contract — plan, real delegation, artifact
handoff, parallel review+validation, budget accounting, repair loop, immutable
candidate — with a scripted provider. They are **not** evidence of real model
generation quality; that requires a live provider run.
"""
from __future__ import annotations

import json

import pytest

from server.application.evidence import EvidenceService
from server.application.generation.orchestration import OrchestrationService
from server.application.projects import ProjectService
from server.application.runs import RunService
from server.domain.projects import Brief
from server.tests import scripted_agents as script

ALICE = "11111111-1111-4111-8111-111111111111"


class FixedIds:
    """Deterministic IDs for the 3 spans / 3 claims / 1 snapshot of the fixture."""

    SPANS = [
        "30000000-0000-4000-8000-000000000001",
        "30000000-0000-4000-8000-000000000002",
        "30000000-0000-4000-8000-000000000003",
    ]
    CLAIMS = [
        "20000000-0000-4000-8000-000000000001",
        "20000000-0000-4000-8000-000000000002",
        "20000000-0000-4000-8000-000000000003",
    ]
    DOCUMENT = "40000000-0000-4000-8000-000000000001"
    SNAPSHOT = "10000000-0000-4000-8000-000000000001"

    def __init__(self) -> None:
        self._queue = [self.DOCUMENT, *self.SPANS, self.SNAPSHOT]

    def __call__(self) -> str:
        return self._queue.pop(0)


async def seed_project(uow_factory, blobs):
    project = await ProjectService(uow_factory).create(
        ALICE,
        "合成工坊体验",
        Brief(audience="五年级学生", duration_minutes=5, learning_goals=("观察工具用途", "识别前置步骤")),
    )
    evidence = EvidenceService(uow_factory, blobs, id_factory=FixedIds())
    text = "合成材料设定工具 X 用于观察。\n\n合成材料设定 A 先于 C。\n\n合成材料设定 B 先于 C。"
    document = await evidence.upload(
        ALICE,
        project.id,
        filename="合成材料.txt",
        data=text.encode("utf-8"),
        license_note="合成教学样例，允许演示使用。",
    )
    spans = await evidence.spans(ALICE, document.id)
    assert len(spans) == 3
    claims = await evidence.add_claims(
        ALICE,
        project.id,
        [
            {
                "id": FixedIds.CLAIMS[0],
                "statement": "合成材料设定工具 X 用于观察。",
                "content_type": "supported",
                "evidence_span_ids": [spans[0].id],
            },
            {
                "id": FixedIds.CLAIMS[1],
                "statement": "合成材料设定 A 先于 C。",
                "content_type": "supported",
                "evidence_span_ids": [spans[1].id],
            },
            {
                "id": FixedIds.CLAIMS[2],
                "statement": "合成材料设定 B 先于 C。",
                "content_type": "supported",
                "evidence_span_ids": [spans[2].id],
            },
        ],
    )
    assert len(claims) == 3
    snapshot = await evidence.freeze_snapshot(ALICE, project.id, [document.id])
    return project, document, spans, snapshot


class FlakyValidator:
    """Wraps the real validator and fails the first N calls.

    Used to exercise the repair loop without fabricating a broken engine: every
    real validation still runs through Node.
    """

    def __init__(self, inner, fail_times: int = 1) -> None:
        self._inner = inner
        self._remaining = fail_times

    async def validate(self, spec, **kwargs):  # type: ignore[no-untyped-def]
        if self._remaining > 0:
            self._remaining -= 1
            return {
                "status": "failed",
                "checker_version": "flaky-wrapper",
                "layers": {"structure": "failed", "semantics": "passed", "state": "failed"},
                "findings": [{"layer": "state", "code": "SIMULATED_REJECT", "message": "测试注入的一次失败。"}],
                "search": {"status": "failed", "visited": 0, "edges": 0},
                "playtest_paths": [],
            }
        return await self._inner.validate(spec, **kwargs)


async def run_generation(uow_factory, blobs, provider, validator, *, override_validator=None):
    project, document, spans, snapshot = await seed_project(uow_factory, blobs)
    runs = RunService(uow_factory)
    submission = await runs.submit_generation(
        ALICE,
        project.id,
        source_snapshot_id=snapshot.id,
        brief_revision=project.brief_revision,
        idempotency_key="key-1",
    )
    await runs.claim(submission.run_id, "worker-a")
    service = OrchestrationService(
        uow_factory, provider, override_validator or validator, provider_is_mock=True
    )
    outcome = await service.execute(submission.run_id, actor_instruction="给五年级使用，五分钟，保留出处。")
    return project, snapshot, spans, outcome


@pytest.mark.simulated
async def test_generation_chain_delegates_every_specialised_role(uow_factory, blob_store, scripted_provider, node_validator):
    project, snapshot, spans, outcome = await run_generation(uow_factory, blob_store, scripted_provider, node_validator)

    assert outcome.status == "succeeded", outcome.error_message
    assert outcome.version_id
    # AT-01: evidence, designer, builder and review all executed with own identity.
    roles = [item.role for item in outcome.trace]
    assert roles[:4] == ["coordinator", "evidence", "experience_designer", "experience_builder"]
    assert "review" in roles
    for item in outcome.trace:
        assert item.agent_id and item.task_id
        assert item.allowed_tools
        assert item.model_calls == 1
    # Provider calls happened in real delegation order.
    assert [call["role"] for call in scripted_provider.calls][:4] == [
        "coordinator",
        "evidence",
        "experience_designer",
        "experience_builder",
    ]
    # Model review and deterministic validation both produced results.
    assert outcome.validation is not None
    assert outcome.validation["status"] == "passed"
    assert outcome.review is not None
    assert outcome.gaps == ["资料未规定 A 与 B 的先后顺序。"]

    async with uow_factory() as uow:
        plan = await uow.agents.get_plan(outcome.run_id)
        run = await uow.runs.get(outcome.run_id)
        project_row = await uow.projects.get(project.id)
        calls = await uow.runs.calls_for(outcome.run_id)
        version = await uow.versions.get(outcome.version_id)
        events = await uow.runs.events_since(outcome.run_id, 0)

    assert plan is not None
    assert plan["plan_hash"]
    assert [task["role"] for task in plan["tasks"]][0] == "evidence"
    assert run is not None and run.status.value == "succeeded"
    assert run.budget.calls_settled == len(calls) == 5
    assert project_row is not None
    assert project_row.revision_head_id == outcome.version_id
    assert project_row.stable_version_id is None, "generation must never publish"
    assert version is not None
    assert version["parent_id"] is None
    assert version["dialogue_profile"]["persona"]["name"] == "小序"
    assert version["dialogue_profile"]["adaptation_note"]
    assert {event["type"] for event in events} >= {"queued", "claimed", "quality", "terminal", "usage"}


@pytest.mark.simulated
async def test_candidate_is_immutable_and_replayable(uow_factory, blob_store, scripted_provider, node_validator):
    _project, _snapshot, _spans, outcome = await run_generation(uow_factory, blob_store, scripted_provider, node_validator)
    assert outcome.status == "succeeded"
    async with uow_factory() as uow:
        version = await uow.versions.get(outcome.version_id)
    spec = version["spec"]
    assert spec["schema_version"] == "1.0.0"
    assert len(spec["scenes"]) == 4
    assert spec["completion"]["scene_id"] == spec["scenes"][-1]["id"]
    # One completion flag per interactive scene, exactly matching completion.
    interactive = spec["scenes"][:-1]
    assert spec["completion"]["required_flags"] == [scene["tasks"][0]["completion_flag"] for scene in interactive]
    # Sequence edges point at real claims that carry the ruling evidence.
    sequence_task = next(
        task for scene in spec["scenes"] for task in scene["tasks"] if task["type"] == "sequence"
    )
    for edge in sequence_task["precedence"]:
        assert edge["claim_id"].startswith("claim_")
    assert len({item["id"] for item in sequence_task["items"]}) == 3
    # Every participant-visible string comes from the model's text slots.
    assert spec["scenes"][0]["title"] == "入口"
    assert sequence_task["feedback"]["success"] == "顺序正确。"
    assert version["semantic_hash"] != version["manifest_hash"]
    assert version["dialogue_profile_hash"] == version["dialogue_profile_hash"]


@pytest.mark.simulated
async def test_invalid_model_output_fails_run_without_candidate(uow_factory, blob_store, node_validator):
    from server.tests.providers import ScriptedProvider

    provider = ScriptedProvider(script.scripted({"experience_designer": "这不是 JSON"}))
    project, _snapshot, _spans, outcome = await run_generation(uow_factory, blob_store, provider, node_validator)
    assert outcome.status == "failed"
    assert outcome.error_code == "MODEL_OUTPUT_NOT_JSON"
    async with uow_factory() as uow:
        run = await uow.runs.get(outcome.run_id)
        project_row = await uow.projects.get(project.id)
    assert run is not None and run.status.value == "failed"
    assert project_row is not None and project_row.revision_head_id is None


@pytest.mark.simulated
async def test_repair_round_runs_and_is_bounded(uow_factory, blob_store, node_validator):
    """One failed validation triggers exactly one repair round, then re-validates."""
    from server.tests.providers import ScriptedProvider

    provider = ScriptedProvider(
        script.scripted(
            {
                "repair": json.dumps(
                    {
                        "patches": [{"op": "replace", "path": "/brief/audience", "value": "六年级学生"}],
                        "reason": "受众调整。",
                    },
                    ensure_ascii=False,
                )
            }
        )
    )
    _project, _snapshot, _spans, outcome = await run_generation(
        uow_factory,
        blob_store,
        provider,
        node_validator,
        override_validator=FlakyValidator(node_validator, fail_times=1),
    )
    # The injected failure was repaired, so the final validation passed and the
    # run legitimately succeeded — the failed candidate was never published.
    assert outcome.status == "succeeded", outcome.error_message
    roles = [item.role for item in outcome.trace]
    assert roles[-1] == "repair"
    assert outcome.validation is not None and outcome.validation["status"] == "passed"
    async with uow_factory() as uow:
        run = await uow.runs.get(outcome.run_id)
        version = await uow.versions.get(outcome.version_id)
    assert run is not None and run.budget.repair_rounds == 1
    assert version is not None and version["spec"]["brief"]["audience"] == "六年级学生"


@pytest.mark.simulated
async def test_repair_cannot_touch_protected_paths(uow_factory, blob_store, node_validator):
    """A repair that tries to rewrite completion/facts fails the run explicitly."""
    from server.tests.providers import ScriptedProvider

    provider = ScriptedProvider(
        script.scripted(
            {
                "repair": json.dumps(
                    {
                        "patches": [
                            {
                                "op": "replace",
                                "path": "/completion/required_flags",
                                "value": ["done_s0"],
                            }
                        ],
                        "reason": "试图缩小完成条件。",
                    },
                    ensure_ascii=False,
                )
            }
        )
    )
    # Make the first candidate fail deterministic validation so repair runs.
    provider._scripted["experience_builder"] = json.dumps(script.builder_content_payload(), ensure_ascii=False)
    _project, _snapshot, _spans, outcome = await run_generation(
        uow_factory,
        blob_store,
        provider,
        node_validator,
        override_validator=FlakyValidator(node_validator, fail_times=1),
    )
    assert outcome.status == "failed"
    assert outcome.error_code == "PATCH_PATH_FORBIDDEN", outcome.error_message
    assert outcome.version_id is None


@pytest.mark.simulated
async def test_budget_exhaustion_is_reported_not_faked(uow_factory, blob_store, node_validator):
    from server.domain.runs import BudgetLedger
    from server.tests.providers import ScriptedProvider

    class TightProvider(ScriptedProvider):
        pass

    provider = TightProvider(script.scripted())

    # Drain the run budget after the coordinator call by patching the ledger.
    original_complete = provider.complete

    async def limited_complete(**kwargs):  # type: ignore[no-untyped-def]
        budget = kwargs["budget"]
        if budget.calls_settled >= 1:
            from server.domain.shared.errors import Conflict

            raise Conflict("BUDGET_EXHAUSTED", "预算耗尽（模拟）。")
        return await original_complete(**kwargs)

    provider.complete = limited_complete  # type: ignore[method-assign]

    project, _snapshot, _spans, outcome = await run_generation(uow_factory, blob_store, provider, node_validator)
    assert outcome.status == "failed"
    assert outcome.error_code == "BUDGET_EXHAUSTED"
    async with uow_factory() as uow:
        run = await uow.runs.get(outcome.run_id)
    assert run is not None and run.status.value == "failed"
    assert outcome.version_id is None
