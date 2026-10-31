"""Multi-agent orchestration (F10, F03).

Flow: Coordinator plan → Evidence → Designer → Builder → (Review ∥ Validator) →
optional Repair → candidate version.

Every sub-task records its own envelope (agent_id, task_id, tools, input hash,
fencing token), its own artifact and its own usage. The whole run shares one
12-call budget. Deterministic validation always runs through the TypeScript
validator; the model's review is advisory and can never approve content.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from server.application.agent_roles import (
    BLUEPRINT_SCHEMA,
    CANDIDATE_SCHEMA,
    EVIDENCE_SCHEMA,
    PLAN_SCHEMA,
    REPAIR_SCHEMA,
    REVIEW_SCHEMA,
    ROLE_PROMPTS,
    extract_json,
    validate_payload,
)
from server.application.ports import ModelProvider, ScopeFactory, ValidatorPort
from server.domain.agents import (
    AGENT_PROTOCOL_VERSION,
    PROFILES,
    AgentRole,
    AgentTaskEnvelope,
    Plan,
    PlanTask,
    TOOL_MATRIX,
)
from server.domain.canonical_json import canonical_sha256
from server.domain.conversation import DialogueProfile
from server.domain.errors import Conflict, DomainError, NotConfigured, ValidationFailure
from server.domain.evidence import Claim, SourceSnapshot
from server.domain.ids import new_id
from server.domain.run import CostStatus, ModelCall, Run, RunStatus, Stage, utcnow


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class AgentTrace:
    task_id: str
    role: str
    objective: str
    status: str
    agent_id: str
    allowed_tools: list[str]
    started_at: datetime
    finished_at: datetime | None = None
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    artifact_id: str | None = None
    issues: list[dict[str, Any]] = field(default_factory=list)
    error_code: str | None = None


@dataclass(slots=True)
class GenerationOutcome:
    run_id: str
    status: str
    version_id: str | None
    plan: dict[str, Any] | None
    trace: list[AgentTrace]
    validation: dict[str, Any] | None
    review: dict[str, Any] | None
    dialogue_profile: dict[str, Any] | None
    gaps: list[str]
    error_code: str | None = None
    error_message: str | None = None


class OrchestrationService:
    def __init__(
        self,
        uow: ScopeFactory,
        provider: ModelProvider,
        validator: ValidatorPort,
        *,
        provider_is_mock: bool = False,
    ) -> None:
        self._uow = uow
        self._provider = provider
        self._validator = validator
        self._mock = provider_is_mock

    # ------------------------------------------------------------------ plan

    async def build_plan(
        self,
        run: Run,
        *,
        brief: dict[str, Any],
        actor_instruction: str,
        snapshot: SourceSnapshot,
        claims: list[Claim],
    ) -> tuple[Plan, dict[str, Any], AgentTrace, list[ModelCall]]:
        """Coordinator call. Returns a validated dependency graph plus its artifact."""
        if run.budget.calls_available < 5:
            raise Conflict("BUDGET_EXHAUSTED", "生成预算不足以完成规划与专业子任务。")
        agent_id = f"coordinator:{run.id[:8]}"
        task_id = new_id()
        envelope = AgentTaskEnvelope(
            protocol_version=AGENT_PROTOCOL_VERSION,
            agent_id=agent_id,
            task_id=task_id,
            parent_task_id=None,
            project_id=run.project_id,
            run_id=run.id,
            role=AgentRole.COORDINATOR,
            profile_version=PROFILES[AgentRole.COORDINATOR],
            input_refs=(f"snapshot:{snapshot.id}", f"brief:{brief.get('audience', '')}"),
            input_hash=run.input_hash,
            allowed_tools=TOOL_MATRIX[AgentRole.COORDINATOR],
            budget_ref=f"run:{run.id}",
            fencing_token=run.fencing_token,
            objective="制定有依赖的专业子任务计划",
        )
        prompt = (
            f"创作者简报：{json.dumps(brief, ensure_ascii=False)}\n"
            f"创作者补充要求：{actor_instruction or '（无）'}\n"
            f"可用事实数量：{len(claims)}\n"
            f"事实摘要：{json.dumps([c.statement for c in claims[:12]], ensure_ascii=False)}\n"
            "请输出计划 JSON。"
        )
        started = _now()
        response = await self._provider.complete(
            role=AgentRole.COORDINATOR.value,
            system=ROLE_PROMPTS[AgentRole.COORDINATOR],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1600,
            budget=run.budget,
            json_schema=PLAN_SCHEMA,
        )
        payload = validate_payload(extract_json(response.text), PLAN_SCHEMA, "Coordinator")
        plan = self._plan_from_payload(run, payload)
        plan.ensure_required_chain()

        trace = AgentTrace(
            task_id=task_id,
            role=AgentRole.COORDINATOR.value,
            objective=envelope.objective,
            status="succeeded",
            agent_id=agent_id,
            allowed_tools=list(envelope.allowed_tools),
            started_at=started,
            finished_at=_now(),
            model_calls=1,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            artifact_id=task_id,
        )
        call = self._call(run, task_id, AgentRole.COORDINATOR, response, prompt)
        return plan, payload, trace, [call]

    def _plan_from_payload(self, run: Run, payload: dict[str, Any]) -> Plan:
        tasks: list[PlanTask] = []
        for item in payload["tasks"]:
            role = AgentRole(item["role"])
            tasks.append(
                PlanTask(
                    task_id=f"plan_{item['task_id']}",
                    role=role,
                    objective=item["objective"],
                    depends_on=tuple(f"plan_{dep}" for dep in item["depends_on"]),
                    input_refs=(f"snapshot:{run.source_snapshot_id}",),
                    allowed_tools=tuple(sorted(TOOL_MATRIX[role])),
                    expected_output=item["expected_output"],
                )
            )
        plan = Plan(
            protocol_version=AGENT_PROTOCOL_VERSION,
            project_id=run.project_id,
            run_id=run.id,
            tasks=tuple(tasks),
            notes=str(payload.get("summary", ""))[:600],
            created_at=_now(),
        )
        plan.topological_order()  # raises on cycles before anything is persisted
        return plan

    # -------------------------------------------------------------- execution

    async def execute(
        self,
        run_id: str,
        *,
        actor_instruction: str = "",
    ) -> GenerationOutcome:
        """Run the full generation DAG for a claimed run. Never raises on model errors."""
        async with self._uow() as uow:
            run = await uow.runs.get_for_update(run_id)
            if run is None:
                raise ValidationFailure("RUN_NOT_FOUND", "任务不存在。", {"run_id": run_id})
            if run.status is not RunStatus.RUNNING:
                raise Conflict("RUN_NOT_RUNNING", "只有运行中的任务可以执行。", object_id=run_id)
            project = await uow.projects.get(run.project_id)
            if project is None:
                raise ValidationFailure("PROJECT_NOT_FOUND", "项目不存在。")
            snapshot = await uow.evidence.get_snapshot(run.source_snapshot_id or "")
            if snapshot is None:
                raise ValidationFailure("SNAPSHOT_REQUIRED", "缺少冻结来源快照。")
            claims = await uow.evidence.latest_claims(run.project_id)
            brief = project.brief.to_payload()
            token = run.fencing_token
            owner = run.lease_owner or "worker"
            base_version_id = project.revision_head_id

        trace: list[AgentTrace] = []
        calls: list[ModelCall] = []
        gaps: list[str] = []
        review_payload: dict[str, Any] | None = None
        validation_report: dict[str, Any] | None = None
        dialogue_payload: dict[str, Any] | None = None
        plan_payload: dict[str, Any] | None = None
        version_id: str | None = None
        error_code: str | None = None
        error_message: str | None = None
        evidence_payload: dict[str, Any] = {"claims": [], "gaps": [], "ordering_facts": []}
        blueprint_payload: dict[str, Any] | None = None
        candidate_payload: dict[str, Any] | None = None

        try:
            plan, plan_payload, plan_trace, plan_calls = await self.build_plan(
                run, brief=brief, actor_instruction=actor_instruction, snapshot=snapshot, claims=claims
            )
            trace.append(plan_trace)
            calls.extend(plan_calls)
            async with self._uow() as uow:
                await uow.agents.save_plan(plan, plan.hash())
                await uow.commit()
            await self._record_calls(run_id, plan_calls)

            evidence_payload, evidence_trace, evidence_calls = await self._run_evidence(
                run, owner, snapshot, claims, plan, gaps
            )
            trace.append(evidence_trace)
            calls.extend(evidence_calls)
            await self._record_calls(run_id, evidence_calls)

            blueprint_payload, blueprint_trace, blueprint_calls = await self._run_designer(
                run, owner, snapshot, evidence_payload, plan, brief, actor_instruction
            )
            trace.append(blueprint_trace)
            calls.extend(blueprint_calls)
            await self._record_calls(run_id, blueprint_calls)

            candidate_payload, builder_trace, builder_calls = await self._run_builder(
                run, owner, snapshot, blueprint_payload, evidence_payload, brief, plan
            )
            trace.append(builder_trace)
            calls.extend(builder_calls)
            await self._record_calls(run_id, builder_calls)

            dialogue_payload = candidate_payload["dialogue"]
            spec = candidate_payload["spec"]

            # Review (model) and validation (deterministic) run concurrently and
            # must both finish before the candidate is committed (F10-R03).
            review_task = asyncio.create_task(
                self._run_review(run, owner, snapshot, spec, blueprint_payload, evidence_payload, plan)
            )
            validation_task = asyncio.create_task(
                self._run_validation(run.project_id, spec, snapshot, evidence_payload)
            )
            review_result, validation_result = await asyncio.gather(
                review_task, validation_task, return_exceptions=True
            )

            if isinstance(review_result, BaseException):
                raise review_result
            review_payload, review_trace, review_calls = review_result
            trace.append(review_trace)
            calls.extend(review_calls)
            await self._record_calls(run_id, review_calls)

            if isinstance(validation_result, BaseException):
                raise validation_result
            validation_report = validation_result

            repair_rounds = 0
            while (
                validation_report.get("status") == "failed"
                and repair_rounds < 2
                and run.budget.repair_rounds + repair_rounds < 2
                and run.budget.calls_available >= 2
            ):
                repair_rounds += 1
                candidate_payload, repair_trace, repair_calls = await self._run_repair(
                    run, owner, snapshot, candidate_payload, validation_report, review_payload, blueprint_payload, repair_rounds
                )
                trace.append(repair_trace)
                calls.extend(repair_calls)
                await self._record_calls(run_id, repair_calls)
                spec = candidate_payload["spec"]
                validation_report = await self._run_validation(
                    run.project_id, spec, snapshot, evidence_payload
                )
            async with self._uow() as uow:
                current = await uow.runs.get_for_update(run_id)
                if current is None:
                    raise ValidationFailure("RUN_NOT_FOUND", "任务不存在。")
                current.require_active_writer(token, owner)
                # The in-memory ledger accumulated every reservation and settlement;
                # the freshly loaded row only has the counters from before this run.
                current.budget.calls_reserved = run.budget.calls_reserved
                current.budget.calls_settled = run.budget.calls_settled
                current.budget.repair_rounds += repair_rounds
                version = await self._commit_candidate(
                    uow,
                    run=current,
                    project_id=current.project_id,
                    base_version_id=base_version_id,
                    spec=spec,
                    dialogue=dialogue_payload,
                    validation_report=validation_report,
                    review_payload=review_payload,
                    evidence_payload=evidence_payload,
                )
                version_id = version["id"]
                current.stage = Stage.ASSEMBLE
                current.status = RunStatus.SUCCEEDED
                current.finished_at = _now()
                current.error_code = None
                await uow.runs.save(current)
                await uow.runs.append_event(
                    run_id,
                    "terminal",
                    {"status": "succeeded", "version_id": version_id, "validation_status": validation_report.get("status")},
                )
                await uow.runs.append_event(
                    run_id,
                    "usage",
                    {
                        "model_calls": len(calls),
                        "repair_rounds": current.budget.repair_rounds,
                        "cost_status": self._cost_status(calls),
                    },
                )
                await uow.commit()

            async with self._uow() as uow:
                project = await uow.projects.get(run.project_id)
                if project is not None:
                    project.revision_head_id = version_id
                    project.latest_candidate_version_id = version_id
                    project.selected_version_id = version_id
                    await uow.projects.save(project)
                    await uow.commit()

        except NotConfigured as error:
            error_code = error.code
            error_message = error.message
        except DomainError as error:
            error_code = error.code
            error_message = error.message
        except Exception as error:  # pragma: no cover - last-resort reporting
            import traceback

            error_code = "INTERNAL"
            error_message = f"{type(error).__name__}: {error}"[:300]
            traceback.print_exc()

        if error_code is not None:
            async with self._uow() as uow:
                current = await uow.runs.get_for_update(run_id)
                if current is not None and current.status not in (RunStatus.SUCCEEDED, RunStatus.CANCELLED):
                    current.status = RunStatus.FAILED
                    current.error_code = error_code
                    current.finished_at = _now()
                    await uow.runs.save(current)
                    await uow.runs.append_event(
                        run_id, "terminal", {"status": "failed", "error_code": error_code}
                    )
                    await uow.commit()

        return GenerationOutcome(
            run_id=run_id,
            status="succeeded" if error_code is None else "failed",
            version_id=version_id,
            plan=plan_payload,
            trace=trace,
            validation=validation_report,
            review=review_payload,
            dialogue_profile=dialogue_payload,
            gaps=gaps,
            error_code=error_code,
            error_message=error_message,
        )

    # ------------------------------------------------------------- sub-agents

    def _envelope(
        self,
        run: Run,
        *,
        role: AgentRole,
        objective: str,
        parent_task_id: str,
        input_refs: tuple[str, ...],
        input_hash: str,
    ) -> AgentTaskEnvelope:
        return AgentTaskEnvelope(
            protocol_version=AGENT_PROTOCOL_VERSION,
            agent_id=f"{role.value}:{new_id()[:8]}",
            task_id=new_id(),
            parent_task_id=parent_task_id,
            project_id=run.project_id,
            run_id=run.id,
            role=role,
            profile_version=PROFILES[role],
            input_refs=input_refs,
            input_hash=input_hash,
            allowed_tools=tuple(sorted(TOOL_MATRIX[role])),
            budget_ref=f"run:{run.id}",
            fencing_token=run.fencing_token,
            objective=objective,
        )

    async def _run_evidence(
        self,
        run: Run,
        owner: str,
        snapshot: SourceSnapshot,
        claims: list[Claim],
        plan: Plan,
        gaps: list[str],
    ) -> tuple[dict[str, Any], AgentTrace, list[ModelCall]]:
        spans = await self._snapshot_spans(snapshot)
        outline = [
            {"span_id": span_id, "quote": quote[:400]}
            for span_id, quote in spans
        ]
        envelope = self._envelope(
            run,
            role=AgentRole.EVIDENCE,
            objective="提取可核对事实与缺口",
            parent_task_id=plan.tasks[0].task_id if plan.tasks else "",
            input_refs=(f"snapshot:{snapshot.id}",),
            input_hash=canonical_sha256({"snapshot": snapshot.sha256, "spans": sorted(span_id for span_id, _ in spans)}),
        )
        prompt = (
            f"资料片段（JSON，含 span_id 与原文）：\n{json.dumps(outline, ensure_ascii=False)}\n"
            f"已有人工事实（供参考，可为空）：{json.dumps([c.statement for c in claims], ensure_ascii=False)}\n"
            "请输出事实抽取 JSON。"
        )
        started = _now()
        response = await self._provider.complete(
            role=AgentRole.EVIDENCE.value,
            system=ROLE_PROMPTS[AgentRole.EVIDENCE],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            budget=run.budget,
            json_schema=EVIDENCE_SCHEMA,
        )
        payload = validate_payload(extract_json(response.text), EVIDENCE_SCHEMA, "Evidence")
        valid_spans = {span_id for span_id, _ in spans}
        for claim in payload["claims"]:
            claim["evidence_span_ids"] = [span_id for span_id in claim["evidence_span_ids"] if span_id in valid_spans]
        gaps.extend(payload["gaps"])
        trace = self._trace_from(envelope, "succeeded", started, response, payload)
        return payload, trace, [self._call(run, envelope.task_id, AgentRole.EVIDENCE, response, prompt)]

    async def _run_designer(
        self,
        run: Run,
        owner: str,
        snapshot: SourceSnapshot,
        evidence: dict[str, Any],
        plan: Plan,
        brief: dict[str, Any],
        actor_instruction: str,
    ) -> tuple[dict[str, Any], AgentTrace, list[ModelCall]]:
        envelope = self._envelope(
            run,
            role=AgentRole.DESIGNER,
            objective="设计场景、机制与对话角色",
            parent_task_id=plan.tasks[0].task_id if plan.tasks else "",
            input_refs=(f"snapshot:{snapshot.id}", "evidence:latest"),
            input_hash=canonical_sha256(evidence),
        )
        facts = [
            {
                "index": index,
                "statement": claim["statement"],
                "content_type": claim["content_type"],
                "evidence_span_ids": claim["evidence_span_ids"],
            }
            for index, claim in enumerate(evidence["claims"])
        ]
        prompt = (
            f"创作者简报：{json.dumps(brief, ensure_ascii=False)}\n"
            f"补充要求：{actor_instruction or '（无）'}\n"
            f"事实（下标从 0 开始）：{json.dumps(facts, ensure_ascii=False)}\n"
            f"资料明确写出的先后关系：{json.dumps(evidence['ordering_facts'], ensure_ascii=False)}\n"
            f"已知缺口：{json.dumps(evidence['gaps'], ensure_ascii=False)}\n"
            "请输出蓝图 JSON。"
        )
        started = _now()
        response = await self._provider.complete(
            role=AgentRole.DESIGNER.value,
            system=ROLE_PROMPTS[AgentRole.DESIGNER],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2600,
            budget=run.budget,
            json_schema=BLUEPRINT_SCHEMA,
        )
        payload = validate_payload(extract_json(response.text), BLUEPRINT_SCHEMA, "Designer")
        trace = self._trace_from(envelope, "succeeded", started, response, payload)
        return payload, trace, [self._call(run, envelope.task_id, AgentRole.DESIGNER, response, prompt)]

    async def _run_builder(
        self,
        run: Run,
        owner: str,
        snapshot: SourceSnapshot,
        blueprint: dict[str, Any],
        evidence: dict[str, Any],
        brief: dict[str, Any],
        plan: Plan,
    ) -> tuple[dict[str, Any], AgentTrace, list[ModelCall]]:
        envelope = self._envelope(
            run,
            role=AgentRole.BUILDER,
            objective="构建 ExperienceSpec 与对话配置候选",
            parent_task_id=plan.tasks[0].task_id if plan.tasks else "",
            input_refs=(f"snapshot:{snapshot.id}", "blueprint:latest"),
            input_hash=canonical_sha256({"blueprint": blueprint, "evidence": evidence}),
        )
        claims = [
            {
                "index": index,
                "statement": claim["statement"],
                "content_type": claim["content_type"],
                "evidence_span_ids": claim["evidence_span_ids"],
            }
            for index, claim in enumerate(evidence["claims"])
        ]
        mechanism = {
            "runtime_version": "1.0.0",
            "schema_version": "1.0.0",
            "conditions": "all/any/not/flag_equals；不得使用空 all",
            "effects": "仅 set_flag=true；任务 completion_flag 由引擎设置",
            "scenes": "4—6 个；完成场景无任务无外跳",
            "tasks": "hotspot/choice/sequence；sequence 至少 1 条偏序边",
        }
        prompt = (
            f"创作者简报：{json.dumps(brief, ensure_ascii=False)}\n"
            f"冻结蓝图：{json.dumps(blueprint, ensure_ascii=False)}\n"
            f"事实（下标从 0 开始，source_claim_id 请使用对应 UUID）：{json.dumps(claims, ensure_ascii=False)}\n"
            f"source_snapshot_id：{snapshot.id}\n"
            f"运行时约束：{json.dumps(mechanism, ensure_ascii=False)}\n"
            "请输出 candidate JSON：{\"spec\": ExperienceSpec, \"dialogue\": {...}}。"
        )
        started = _now()
        response = await self._provider.complete(
            role=AgentRole.BUILDER.value,
            system=ROLE_PROMPTS[AgentRole.BUILDER],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            budget=run.budget,
            json_schema=CANDIDATE_SCHEMA,
        )
        payload = validate_payload(extract_json(response.text), CANDIDATE_SCHEMA, "Builder")
        trace = self._trace_from(envelope, "succeeded", started, response, {"keys": list(payload["spec"].keys())})
        return payload, trace, [self._call(run, envelope.task_id, AgentRole.BUILDER, response, prompt)]

    async def _run_review(
        self,
        run: Run,
        owner: str,
        snapshot: SourceSnapshot,
        spec: dict[str, Any],
        blueprint: dict[str, Any],
        evidence: dict[str, Any],
        plan: Plan,
    ) -> tuple[dict[str, Any], AgentTrace, list[ModelCall]]:
        envelope = self._envelope(
            run,
            role=AgentRole.REVIEW,
            objective="检查表述、来源与目标覆盖",
            parent_task_id=plan.tasks[0].task_id if plan.tasks else "",
            input_refs=(f"snapshot:{snapshot.id}", "candidate:latest"),
            input_hash=canonical_sha256({"spec": spec, "blueprint": blueprint}),
        )
        prompt = (
            f"事实：{json.dumps(evidence['claims'], ensure_ascii=False)}\n"
            f"蓝图：{json.dumps(blueprint, ensure_ascii=False)}\n"
            f"候选规格：{json.dumps(spec, ensure_ascii=False)}\n"
            "请输出审校 JSON。"
        )
        started = _now()
        response = await self._provider.complete(
            role=AgentRole.REVIEW.value,
            system=ROLE_PROMPTS[AgentRole.REVIEW],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1800,
            budget=run.budget,
            json_schema=REVIEW_SCHEMA,
        )
        payload = validate_payload(extract_json(response.text), REVIEW_SCHEMA, "Review")
        trace = self._trace_from(envelope, "succeeded", started, response, payload)
        trace.issues = list(payload["findings"])
        return payload, trace, [self._call(run, envelope.task_id, AgentRole.REVIEW, response, prompt)]

    async def _run_repair(
        self,
        run: Run,
        owner: str,
        snapshot: SourceSnapshot,
        candidate: dict[str, Any],
        validation: dict[str, Any],
        review: dict[str, Any],
        blueprint: dict[str, Any],
        round_number: int,
    ) -> tuple[dict[str, Any], AgentTrace, list[ModelCall]]:
        envelope = self._envelope(
            run,
            role=AgentRole.REPAIR,
            objective=f"第 {round_number} 轮局部修复",
            parent_task_id="",
            input_refs=(f"snapshot:{snapshot.id}", "candidate:latest", "validation:latest"),
            input_hash=canonical_sha256({"spec": candidate["spec"], "validation": validation}),
        )
        problems = {
            "validation": validation.get("findings", []),
            "review": review.get("findings", []),
        }
        prompt = (
            f"当前规格：{json.dumps(candidate['spec'], ensure_ascii=False)}\n"
            f"问题清单：{json.dumps(problems, ensure_ascii=False)}\n"
            "只输出最小 JSON Patch 数组。"
        )
        started = _now()
        response = await self._provider.complete(
            role=AgentRole.REPAIR.value,
            system=ROLE_PROMPTS[AgentRole.REPAIR],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1600,
            budget=run.budget,
            json_schema=REPAIR_SCHEMA,
        )
        payload = validate_payload(extract_json(response.text), REPAIR_SCHEMA, "Repair")
        patched = apply_patch(candidate["spec"], payload["patches"])
        trace = self._trace_from(envelope, "succeeded", started, response, {"patches": len(payload["patches"])})
        return (
            {"spec": patched, "dialogue": candidate["dialogue"]},
            trace,
            [self._call(run, envelope.task_id, AgentRole.REPAIR, response, prompt)],
        )

    # -------------------------------------------------------------- validation

    async def _run_validation(
        self,
        project_id: str,
        spec: dict[str, Any],
        snapshot: SourceSnapshot,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        span_ids = sorted({span for claim in evidence["claims"] for span in claim["evidence_span_ids"]})
        spec_hash = canonical_sha256(spec)
        semantic_hash = canonical_sha256(semantic_projection(spec))
        return await self._validator.validate(
            spec,
            evidence_span_ids=span_ids,
            spec_hash=spec_hash,
            semantic_hash=semantic_hash,
        )

    async def _snapshot_spans(self, snapshot: SourceSnapshot) -> list[tuple[str, str]]:
        """Resolve snapshot span ids to quotes from the frozen documents."""
        spans: list[tuple[str, str]] = []
        async with self._uow() as uow:
            for entry in snapshot.manifest.documents:
                rows = await uow.evidence.spans_for(entry.source_id, entry.parse_version)
                allowed = {part.split(":", 1)[0] for part in entry.span_hashes}
                for row in rows:
                    if row.id in allowed:
                        spans.append((row.id, row.quote))
        return spans

    # ---------------------------------------------------------------- commits

    async def _commit_candidate(
        self,
        uow: Any,
        *,
        run: Run,
        project_id: str,
        base_version_id: str | None,
        spec: dict[str, Any],
        dialogue: dict[str, Any],
        validation_report: dict[str, Any],
        review_payload: dict[str, Any],
        evidence_payload: dict[str, Any],
    ) -> dict[str, Any]:
        profile = DialogueProfile(
            id="guide_main",
            profile_version="1.0.0",
            persona_name=dialogue["persona_name"],
            persona_role=dialogue["persona_role"],
            adaptation_note=dialogue["adaptation_note"],
            source_scope=tuple(
                sorted({span for claim in evidence_payload["claims"] for span in claim["evidence_span_ids"]})
            ) or ("none",),
            objective_ids=tuple(sorted({str(objective["id"]) for objective in spec.get("objectives", [])})),
            hint_policy=dialogue["hint_policy"],
            max_hint_level={"none": 0, "gentle": 1, "progressive": 3}[dialogue["hint_policy"]],
            allowed_actions=("open_source_card", "highlight_claim", "suggest_hint", "navigate_scene"),
            model_policy_ref="conversation-default",
        )
        spec_hash = canonical_sha256(spec)
        semantic_hash = canonical_sha256(semantic_projection(spec))
        manifest = {
            "spec_hash": spec_hash,
            "dialogue_profile_hash": profile.hash(),
            "source_snapshot_hash": run.source_snapshot_id,
            "mock": self._mock,
            "validation_status": validation_report.get("status"),
        }
        manifest_hash = canonical_sha256(manifest)
        version = await uow.versions.add(
            version_id=new_id(),
            project_id=project_id,
            parent_id=base_version_id,
            run_id=run.id,
            step_key=f"candidate:{run.id}",
            spec=spec,
            dialogue_profile=profile.to_payload(),
            spec_hash=spec_hash,
            semantic_hash=semantic_hash,
            manifest_hash=manifest_hash,
            dialogue_profile_hash=profile.hash(),
            runtime_version=str(spec.get("runtime_version", "1.0.0")),
        )
        await uow.runs.append_event(
            run.id,
            "quality",
            {
                "validation_status": validation_report.get("status"),
                "review_findings": len(review_payload.get("findings", [])),
                "spec_hash": spec_hash,
                "semantic_hash": semantic_hash,
                "manifest_hash": manifest_hash,
            },
        )
        return version

    async def _record_calls(self, run_id: str, calls: list[ModelCall]) -> None:
        async with self._uow() as uow:
            for call in calls:
                await uow.runs.record_call(call)
            await uow.commit()

    def _call(
        self,
        run: Run,
        agent_task_id: str,
        role: AgentRole,
        response: Any,
        prompt: str,
    ) -> ModelCall:
        return ModelCall(
            id=new_id(),
            run_id=run.id,
            agent_task_id=agent_task_id,
            provider=getattr(response, "provider", self._provider.name),
            model=getattr(response, "model", "unknown"),
            provider_request_id=getattr(response, "provider_request_id", None),
            attempt=1,
            status="succeeded",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            currency=response.currency,
            cost_micros=response.cost_micros,
            cost_status=response.cost_status,
            started_at=_now(),
            finished_at=_now(),
        )

    def _trace_from(self, envelope: AgentTaskEnvelope, status: str, started: datetime, response: Any, payload: Any) -> AgentTrace:
        return AgentTrace(
            task_id=envelope.task_id,
            role=envelope.role.value,
            objective=envelope.objective,
            status=status,
            agent_id=envelope.agent_id,
            allowed_tools=list(envelope.allowed_tools),
            started_at=started,
            finished_at=_now(),
            model_calls=1,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            artifact_id=envelope.task_id,
        )

    @staticmethod
    def _cost_status(calls: list[ModelCall]) -> str:
        statuses = {call.cost_status for call in calls}
        if CostStatus.UNKNOWN in statuses:
            return CostStatus.UNKNOWN.value
        if CostStatus.ESTIMATED in statuses:
            return CostStatus.ESTIMATED.value
        return CostStatus.ACTUAL.value


def semantic_projection(spec: dict[str, Any]) -> dict[str, Any]:
    """Fields that carry meaning for review (data-model §文本与哈希).

    Topic/theme styling and asset presentation are excluded; every narrative,
    feedback, hint, task and rule field is included.
    """
    return {
        "schema_version": spec.get("schema_version"),
        "runtime_version": spec.get("runtime_version"),
        "brief": spec.get("brief"),
        "source_snapshot_id": spec.get("source_snapshot_id"),
        "entry_scene": spec.get("entry_scene"),
        "completion": spec.get("completion"),
        "claims": [
            {
                "id": claim.get("id"),
                "statement": claim.get("statement"),
                "content_type": claim.get("content_type"),
                "evidence_span_ids": claim.get("evidence_span_ids"),
                "source_claim_id": claim.get("source_claim_id"),
                "source_claim_revision": claim.get("source_claim_revision"),
            }
            for claim in spec.get("claims", [])
        ],
        "objectives": spec.get("objectives"),
        "scenes": [
            {
                "id": scene.get("id"),
                "title": scene.get("title"),
                "text": scene.get("text"),
                "content_type": scene.get("content_type"),
                "claim_ids": scene.get("claim_ids"),
                "tasks": scene.get("tasks"),
                "transitions": scene.get("transitions"),
            }
            for scene in spec.get("scenes", [])
        ],
        "flags": spec.get("flags"),
    }


def apply_patch(spec: dict[str, Any], patches: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply whitelisted ``replace`` operations by parsed JSON Pointer segments."""
    from server.domain.version import check_patch_path

    patched = json.loads(json.dumps(spec))
    for patch in patches:
        check_patch_path(patch["path"])
        segments = [part.replace("~1", "/").replace("~0", "~") for part in patch["path"].split("/")[1:]]
        cursor: Any = patched
        for segment in segments[:-1]:
            if isinstance(cursor, list):
                cursor = cursor[int(segment)]
            elif isinstance(cursor, dict) and segment in cursor:
                cursor = cursor[segment]
            else:
                raise ValidationFailure("PATCH_PATH_NOT_FOUND", "补丁路径不存在。", {"path": patch["path"]})
        last = segments[-1]
        if isinstance(cursor, list):
            cursor[int(last)] = patch["value"]
        elif isinstance(cursor, dict) and last in cursor:
            cursor[last] = patch["value"]
        else:
            raise ValidationFailure("PATCH_PATH_NOT_FOUND", "补丁路径不存在。", {"path": patch["path"]})
    return patched
