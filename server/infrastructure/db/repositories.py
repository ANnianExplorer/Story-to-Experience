"""SQLAlchemy repository implementations for the application ports."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Sequence

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.domain.agents import AgentResult, AgentTaskEnvelope, Plan
from server.domain.conversations import ConversationSession, ConversationTurn, TurnStatus
from server.domain.evidence import (
    Claim,
    SourceDocument,
    SourceSnapshot,
    SourceSpan,
    SnapshotManifest,
    SnapshotManifestEntry,
)
from server.domain.projects import Brief, BriefRevision, Project
from server.domain.runs import BudgetLedger, CostStatus, ModelCall, Run, RunStatus, Stage
from server.infrastructure.db.tables import (
    AgentArtifactRow,
    AgentPlanRow,
    AgentTaskRow,
    BriefRevisionRow,
    ClaimRow,
    ConversationSessionRow,
    ConversationTurnRow,
    IdempotencyRow,
    ModelCallRow,
    ProjectRow,
    RunEventRow,
    RunRow,
    RunStepRow,
    SourceDocumentRow,
    SourceSnapshotRow,
    SourceSpanRow,
    VersionRow,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; all stored timestamps are UTC, so re-attach it."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _encode_cursor(created_at: datetime, row_id: str) -> str:
    raw = f"{created_at.isoformat()}|{row_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    stamp, _, row_id = raw.partition("|")
    return datetime.fromisoformat(stamp), row_id


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, row: ProjectRow) -> Project:
        return Project(
            id=row.id,
            owner_id=row.owner_id,
            name=row.name,
            brief=Brief.from_payload(row.brief_json),
            brief_revision=row.brief_revision,
            revision_head_id=row.revision_head_id,
            latest_candidate_version_id=row.latest_candidate_version_id,
            selected_version_id=row.selected_version_id,
            stable_version_id=row.stable_version_id,
            active_revision_run_id=row.active_revision_run_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def create(self, project: Project) -> Project:
        row = ProjectRow(
            id=project.id,
            owner_id=project.owner_id,
            name=project.name,
            brief_json=project.brief.to_payload(),
            brief_revision=project.brief_revision,
            revision_head_id=project.revision_head_id,
            latest_candidate_version_id=project.latest_candidate_version_id,
            selected_version_id=project.selected_version_id,
            stable_version_id=project.stable_version_id,
            active_revision_run_id=project.active_revision_run_id,
            created_at=project.created_at or _now(),
            updated_at=project.updated_at or _now(),
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_domain(row)

    async def get(self, project_id: str) -> Project | None:
        row = await self._session.get(ProjectRow, project_id)
        return self._to_domain(row) if row else None

    async def get_for_update(self, project_id: str) -> Project | None:
        stmt = select(ProjectRow).where(ProjectRow.id == project_id).with_for_update()
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list_for_owner(
        self, owner_id: str, cursor: str | None, limit: int
    ) -> tuple[list[Project], str | None]:
        stmt = select(ProjectRow).where(ProjectRow.owner_id == owner_id).order_by(
            ProjectRow.created_at.desc(), ProjectRow.id.desc()
        )
        if cursor:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                sa.or_(
                    ProjectRow.created_at < created_at,
                    sa.and_(ProjectRow.created_at == created_at, ProjectRow.id < row_id),
                )
            )
        rows = list((await self._session.execute(stmt.limit(limit + 1))).scalars())
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
        return [self._to_domain(row) for row in rows], next_cursor

    async def save(self, project: Project) -> Project:
        row = await self._session.get(ProjectRow, project.id)
        if row is None:
            from server.domain.shared.errors import NotFound

            raise NotFound(object_id=project.id)
        row.name = project.name
        row.brief_json = project.brief.to_payload()
        row.brief_revision = project.brief_revision
        row.revision_head_id = project.revision_head_id
        row.latest_candidate_version_id = project.latest_candidate_version_id
        row.selected_version_id = project.selected_version_id
        row.stable_version_id = project.stable_version_id
        row.active_revision_run_id = project.active_revision_run_id
        row.updated_at = project.updated_at or _now()
        await self._session.flush()
        return self._to_domain(row)

    async def append_brief_revision(self, revision: BriefRevision) -> BriefRevision:
        self._session.add(
            BriefRevisionRow(
                project_id=revision.project_id,
                revision=revision.revision,
                brief_json=revision.brief.to_payload(),
                note=revision.note,
                created_at=revision.created_at or _now(),
            )
        )
        await self._session.flush()
        return revision

    async def brief_history(self, project_id: str) -> list[BriefRevision]:
        stmt = (
            select(BriefRevisionRow)
            .where(BriefRevisionRow.project_id == project_id)
            .order_by(BriefRevisionRow.revision)
        )
        rows = (await self._session.execute(stmt)).scalars()
        return [
            BriefRevision(
                project_id=row.project_id,
                revision=row.revision,
                brief=Brief.from_payload(row.brief_json),
                note=row.note,
                created_at=row.created_at,
            )
            for row in rows
        ]


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _document(row: SourceDocumentRow) -> SourceDocument:
        return SourceDocument(
            id=row.id,
            project_id=row.project_id,
            sha256=row.sha256,
            storage_key=row.storage_key,
            mime_type=row.mime_type,
            license_note=row.license_note,
            title=row.title,
            parse_status=row.parse_status,  # type: ignore[arg-type]
            parse_version=row.parse_version,
            normalized_text=row.normalized_text,
            error_code=row.error_code,
            created_at=row.created_at,
        )

    async def add_document(self, document: SourceDocument) -> SourceDocument:
        self._session.add(
            SourceDocumentRow(
                id=document.id,
                project_id=document.project_id,
                sha256=document.sha256,
                storage_key=document.storage_key,
                mime_type=document.mime_type,
                license_note=document.license_note,
                title=document.title,
                parse_status=document.parse_status,
                parse_version=document.parse_version,
                normalized_text=document.normalized_text,
                error_code=document.error_code,
                created_at=document.created_at or _now(),
            )
        )
        await self._session.flush()
        return document

    async def get_document(self, source_id: str) -> SourceDocument | None:
        row = await self._session.get(SourceDocumentRow, source_id)
        return self._document(row) if row else None

    async def save_document(self, document: SourceDocument) -> SourceDocument:
        row = await self._session.get(SourceDocumentRow, document.id)
        if row is None:
            from server.domain.shared.errors import NotFound

            raise NotFound(object_id=document.id)
        row.parse_status = document.parse_status
        row.parse_version = document.parse_version
        row.normalized_text = document.normalized_text
        row.error_code = document.error_code
        await self._session.flush()
        return document

    async def add_spans(self, spans: Sequence[SourceSpan]) -> None:
        for span in spans:
            self._session.add(
                SourceSpanRow(
                    id=span.id,
                    source_id=span.source_id,
                    project_id=self._project_of(span.source_id),
                    parse_version=span.parse_version,
                    page=span.page,
                    paragraph=span.paragraph,
                    ordinal=span.ordinal,
                    start_cp=span.start_cp,
                    end_cp=span.end_cp,
                    quote=span.quote,
                    text_hash=span.text_hash,
                )
            )
        await self._session.flush()

    def _project_of(self, source_id: str) -> str:
        # Resolved by the caller through get_document before insert; kept as a
        # lookup table on the instance for bulk inserts.
        cached = getattr(self, "_project_cache", {})
        if source_id not in cached:
            raise RuntimeError("EvidenceRepository.add_spans requires prime_project() first")
        return cached[source_id]

    def prime_project(self, source_id: str, project_id: str) -> None:
        cache = getattr(self, "_project_cache", None)
        if cache is None:
            cache = {}
            self._project_cache = cache
        cache[source_id] = project_id

    async def spans_for(self, source_id: str, parse_version: int) -> list[SourceSpan]:
        stmt = (
            select(SourceSpanRow)
            .where(SourceSpanRow.source_id == source_id, SourceSpanRow.parse_version == parse_version)
            .order_by(SourceSpanRow.ordinal)
        )
        rows = (await self._session.execute(stmt)).scalars()
        return [
            SourceSpan(
                id=row.id,
                source_id=row.source_id,
                parse_version=row.parse_version,
                page=row.page,
                paragraph=row.paragraph,
                start_cp=row.start_cp,
                end_cp=row.end_cp,
                quote=row.quote,
                text_hash=row.text_hash,
                ordinal=row.ordinal,
            )
            for row in rows
        ]

    async def add_claim(self, claim: Claim) -> Claim:
        self._session.add(
            ClaimRow(
                id=claim.id,
                project_id=claim.project_id,
                revision=claim.revision,
                statement=claim.statement,
                content_type=claim.content_type,
                evidence_span_ids=list(claim.evidence_span_ids),
                qualifier=claim.qualifier,
                created_at=claim.created_at or _now(),
            )
        )
        await self._session.flush()
        return claim

    @staticmethod
    def _claim(row: ClaimRow) -> Claim:
        return Claim(
            id=row.id,
            project_id=row.project_id,
            revision=row.revision,
            statement=row.statement,
            content_type=row.content_type,  # type: ignore[arg-type]
            evidence_span_ids=tuple(row.evidence_span_ids or ()),
            qualifier=row.qualifier,
            created_at=row.created_at,
        )

    async def latest_claims(self, project_id: str) -> list[Claim]:
        # Latest revision per claim id.
        sub = (
            select(ClaimRow.id, sa.func.max(ClaimRow.revision).label("revision"))
            .where(ClaimRow.project_id == project_id)
            .group_by(ClaimRow.id)
            .subquery()
        )
        stmt = select(ClaimRow).join(
            sub, sa.and_(ClaimRow.id == sub.c.id, ClaimRow.revision == sub.c.revision)
        )
        rows = (await self._session.execute(stmt)).scalars()
        return [self._claim(row) for row in rows]

    async def get_claim(self, claim_id: str, revision: int) -> Claim | None:
        stmt = select(ClaimRow).where(ClaimRow.id == claim_id, ClaimRow.revision == revision)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._claim(row) if row else None

    async def claims_for_span(self, span_id: str) -> list[Claim]:
        stmt = select(ClaimRow)
        rows = (await self._session.execute(stmt)).scalars()
        return [self._claim(row) for row in rows if span_id in (row.evidence_span_ids or [])]

    async def add_snapshot(self, snapshot: SourceSnapshot) -> SourceSnapshot:
        self._session.add(
            SourceSnapshotRow(
                id=snapshot.id,
                project_id=snapshot.project_id,
                manifest_json=snapshot.manifest.to_payload(),
                sha256=snapshot.sha256,
                created_at=snapshot.created_at or _now(),
            )
        )
        await self._session.flush()
        return snapshot

    async def get_snapshot(self, snapshot_id: str) -> SourceSnapshot | None:
        row = await self._session.get(SourceSnapshotRow, snapshot_id)
        if row is None:
            return None
        payload = row.manifest_json
        manifest = SnapshotManifest(
            project_id=payload["project_id"],
            documents=tuple(
                SnapshotManifestEntry(
                    source_id=entry["source_id"],
                    sha256=entry["sha256"],
                    parse_version=entry["parse_version"],
                    span_hashes=tuple(entry["span_hashes"]),
                )
                for entry in payload["documents"]
            ),
            claims=tuple(payload["claims"]),
        )
        return SourceSnapshot(
            id=row.id, project_id=row.project_id, sha256=row.sha256, manifest=manifest, created_at=row.created_at
        )

    async def get_span(self, span_id: str) -> SourceSpan | None:
        row = await self._session.get(SourceSpanRow, span_id)
        if row is None:
            return None
        return SourceSpan(
            id=row.id,
            source_id=row.source_id,
            parse_version=row.parse_version,
            page=row.page,
            paragraph=row.paragraph,
            start_cp=row.start_cp,
            end_cp=row.end_cp,
            quote=row.quote,
            text_hash=row.text_hash,
            ordinal=row.ordinal,
        )


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _run(row: RunRow) -> Run:
        counters = row.counters or {}
        return Run(
            id=row.id,
            project_id=row.project_id,
            kind=row.kind,
            status=RunStatus(row.status),
            stage=Stage(row.stage),
            input_hash=row.input_hash,
            source_snapshot_id=row.source_snapshot_id,
            base_version_id=row.base_version_id,
            attempt=row.attempt,
            lease_owner=row.lease_owner,
            lease_expires_at=_aware(row.lease_expires_at),
            fencing_token=row.fencing_token,
            last_sequence=row.last_sequence,
            budget=BudgetLedger(
                calls_reserved=counters.get("calls_reserved", 0),
                calls_settled=counters.get("calls_settled", 0),
                repair_rounds=counters.get("repair_rounds", 0),
            ),
            error_code=row.error_code,
            created_at=_aware(row.created_at),
            finished_at=_aware(row.finished_at),
        )

    async def create(self, run: Run) -> Run:
        self._session.add(
            RunRow(
                id=run.id,
                project_id=run.project_id,
                kind=run.kind,
                status=run.status.value,
                stage=run.stage.value,
                input_hash=run.input_hash,
                source_snapshot_id=run.source_snapshot_id,
                base_version_id=run.base_version_id,
                attempt=run.attempt,
                lease_owner=run.lease_owner,
                lease_expires_at=run.lease_expires_at,
                fencing_token=run.fencing_token,
                last_sequence=run.last_sequence,
                counters={
                    "calls_reserved": run.budget.calls_reserved,
                    "calls_settled": run.budget.calls_settled,
                    "repair_rounds": run.budget.repair_rounds,
                },
                error_code=run.error_code,
                created_at=run.created_at or _now(),
                finished_at=run.finished_at,
            )
        )
        await self._session.flush()
        return run

    async def get(self, run_id: str) -> Run | None:
        row = await self._session.get(RunRow, run_id)
        return self._run(row) if row else None

    async def get_for_update(self, run_id: str) -> Run | None:
        stmt = select(RunRow).where(RunRow.id == run_id).with_for_update()
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._run(row) if row else None

    async def save(self, run: Run) -> Run:
        row = await self._session.get(RunRow, run.id)
        if row is None:
            from server.domain.shared.errors import NotFound

            raise NotFound(object_id=run.id)
        row.status = run.status.value
        row.stage = run.stage.value
        row.attempt = run.attempt
        row.lease_owner = run.lease_owner
        row.lease_expires_at = run.lease_expires_at
        row.fencing_token = run.fencing_token
        # ``last_sequence`` is owned by append_event's atomic allocation; writing
        # it back from a stale domain copy would rewind the counter.
        row.counters = {
            "calls_reserved": run.budget.calls_reserved,
            "calls_settled": run.budget.calls_settled,
            "repair_rounds": run.budget.repair_rounds,
        }
        row.error_code = run.error_code
        row.finished_at = run.finished_at
        await self._session.flush()
        return run

    async def active_for_project(self, project_id: str) -> Run | None:
        stmt = (
            select(RunRow)
            .where(
                RunRow.project_id == project_id,
                RunRow.kind.in_(["generate", "revision"]),
                RunRow.status.in_([status.value for status in (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING_INPUT)]),
            )
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._run(row) if row else None

    async def append_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> int:
        # Allocate the sequence atomically in the database. Reading the row and
        # adding one in Python would collide when two appends happen in the same
        # transaction (identity map keeps the stale counter).
        allocate = (
            sa.update(RunRow)
            .where(RunRow.id == run_id)
            .values(last_sequence=RunRow.last_sequence + 1)
            .returning(RunRow.last_sequence)
        )
        sequence = (await self._session.execute(allocate)).scalar_one_or_none()
        if sequence is None:
            from server.domain.shared.errors import NotFound

            raise NotFound(object_id=run_id)
        self._session.add(
            RunEventRow(run_id=run_id, sequence=int(sequence), type=event_type, payload=payload, created_at=_now())
        )
        await self._session.flush()
        return int(sequence)

    async def events_since(self, run_id: str, after: int) -> list[dict[str, Any]]:
        stmt = (
            select(RunEventRow)
            .where(RunEventRow.run_id == run_id, RunEventRow.sequence > after)
            .order_by(RunEventRow.sequence)
        )
        return [
            {"sequence": row.sequence, "type": row.type, "payload": row.payload, "created_at": row.created_at.isoformat()}
            for row in (await self._session.execute(stmt)).scalars()
        ]

    async def record_call(self, call: ModelCall) -> None:
        self._session.add(
            ModelCallRow(
                id=call.id,
                run_id=call.run_id,
                agent_task_id=call.agent_task_id,
                provider=call.provider,
                model=call.model,
                provider_request_id=call.provider_request_id,
                attempt=call.attempt,
                status=call.status,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                currency=call.currency,
                cost_micros=call.cost_micros,
                cost_status=call.cost_status.value,
                started_at=call.started_at,
                finished_at=call.finished_at,
            )
        )
        await self._session.flush()

    async def calls_for(self, run_id: str) -> list[ModelCall]:
        stmt = select(ModelCallRow).where(ModelCallRow.run_id == run_id).order_by(ModelCallRow.started_at)
        return [
            ModelCall(
                id=row.id,
                run_id=row.run_id,
                agent_task_id=row.agent_task_id,
                provider=row.provider,
                model=row.model,
                provider_request_id=row.provider_request_id,
                attempt=row.attempt,
                status=row.status,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                currency=row.currency,
                cost_micros=row.cost_micros,
                cost_status=CostStatus(row.cost_status),
                started_at=row.started_at,
                finished_at=row.finished_at,
            )
            for row in (await self._session.execute(stmt)).scalars()
        ]

    async def record_step(self, run_id: str, step_key: str, input_hash: str, output: dict[str, Any], output_hash: str) -> None:
        self._session.add(
            RunStepRow(
                id=f"{run_id}:{step_key}:{input_hash[:12]}",
                run_id=run_id,
                step_key=step_key,
                input_hash=input_hash,
                stage_version="1",
                output_hash=output_hash,
                payload=output,
                created_at=_now(),
            )
        )
        await self._session.flush()

    async def completed_step(self, run_id: str, step_key: str, input_hash: str) -> dict[str, Any] | None:
        stmt = select(RunStepRow).where(
            RunStepRow.run_id == run_id,
            RunStepRow.step_key == step_key,
            RunStepRow.input_hash == input_hash,
            RunStepRow.stage_version == "1",
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return row.payload if row else None


class AgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_plan(self, plan: Plan, plan_hash: str) -> None:
        """Persist the plan; re-executing the same run replaces it rather than
        violating the run_id primary key (R06 stage idempotency)."""
        existing = await self._session.get(AgentPlanRow, plan.run_id)
        if existing is None:
            self._session.add(
                AgentPlanRow(
                    run_id=plan.run_id, plan_hash=plan_hash, payload=plan.to_payload(), created_at=_now()
                )
            )
        else:
            existing.plan_hash = plan_hash
            existing.payload = plan.to_payload()
        await self._session.flush()

    async def get_plan(self, run_id: str) -> dict[str, Any] | None:
        row = await self._session.get(AgentPlanRow, run_id)
        return row.payload if row else None

    async def create_task(self, envelope: AgentTaskEnvelope) -> None:
        existing = await self._session.get(AgentTaskRow, envelope.task_id)
        if existing is not None:
            return
        now = _now()
        self._session.add(
            AgentTaskRow(
                task_id=envelope.task_id,
                run_id=envelope.run_id,
                project_id=envelope.project_id,
                parent_task_id=envelope.parent_task_id,
                agent_id=envelope.agent_id,
                role=envelope.role.value,
                profile_version=envelope.profile_version,
                status="pending",
                envelope=envelope.to_payload(),
                artifact_refs=[],
                usage={},
                created_at=now,
                updated_at=now,
            )
        )
        await self._session.flush()

    async def mark_running(self, task_id: str) -> None:
        row = await self._session.get(AgentTaskRow, task_id)
        if row is None:
            from server.domain.shared.errors import NotFound

            raise NotFound(object_id=task_id)
        row.status = "running"
        row.updated_at = _now()
        await self._session.flush()

    async def save_result(self, run_id: str, result: AgentResult, artifact: dict[str, Any] | None) -> None:
        row = await self._session.get(AgentTaskRow, result.task_id)
        if row is None:
            from server.domain.shared.errors import NotFound

            raise NotFound(object_id=result.task_id)
        row.status = result.status.value
        row.result_json = result.to_payload()
        row.artifact_refs = list(result.artifact_refs)
        row.usage = {
            "model_calls": result.usage.model_calls,
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "cost_status": result.usage.cost_status,
            "cost_micros": result.usage.cost_micros,
            "currency": result.usage.currency,
        }
        row.updated_at = _now()
        if artifact is not None and result.artifact_refs:
            from server.domain.shared.canonical_json import canonical_sha256

            artifact_id = result.artifact_refs[0]
            self._session.add(
                AgentArtifactRow(
                    id=artifact_id,
                    task_id=result.task_id,
                    project_id=row.project_id,
                    kind=artifact.get("kind", "unknown"),
                    schema_version=str(artifact.get("schema_version", "1.0.0")),
                    artifact_hash=canonical_sha256(artifact.get("payload", {})),
                    payload=artifact.get("payload", {}),
                    citation_refs=list(result.citation_refs),
                    created_at=_now(),
                )
            )
        await self._session.flush()

    async def tasks_for(self, run_id: str) -> list[dict[str, Any]]:
        stmt = select(AgentTaskRow).where(AgentTaskRow.run_id == run_id).order_by(AgentTaskRow.created_at)
        return [
            {
                "task_id": row.task_id,
                "agent_id": row.agent_id,
                "role": row.role,
                "profile_version": row.profile_version,
                "status": row.status,
                "envelope": row.envelope,
                "artifact_refs": row.artifact_refs,
                "usage": row.usage,
                "result": row.result_json,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            }
            for row in (await self._session.execute(stmt)).scalars()
        ]

    async def artifact(self, artifact_id: str) -> dict[str, Any] | None:
        row = await self._session.get(AgentArtifactRow, artifact_id)
        if row is None:
            return None
        return {
            "id": row.id,
            "task_id": row.task_id,
            "kind": row.kind,
            "schema_version": row.schema_version,
            "artifact_hash": row.artifact_hash,
            "payload": row.payload,
            "citation_refs": row.citation_refs,
        }


class VersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        version_id: str,
        project_id: str,
        parent_id: str | None,
        run_id: str | None,
        step_key: str | None,
        spec: dict[str, Any],
        dialogue_profile: dict[str, Any] | None,
        spec_hash: str,
        semantic_hash: str,
        manifest_hash: str,
        dialogue_profile_hash: str | None,
        runtime_version: str,
    ) -> dict[str, Any]:
        row = VersionRow(
            id=version_id,
            project_id=project_id,
            parent_id=parent_id,
            run_id=run_id,
            step_key=step_key,
            content_json=spec,
            dialogue_profile_json=dialogue_profile,
            spec_hash=spec_hash,
            semantic_hash=semantic_hash,
            manifest_hash=manifest_hash,
            dialogue_profile_hash=dialogue_profile_hash,
            runtime_version=runtime_version,
            created_at=_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return self._version(row)

    async def get(self, version_id: str) -> dict[str, Any] | None:
        row = await self._session.get(VersionRow, version_id)
        return self._version(row) if row else None

    async def list_for(self, project_id: str, limit: int = 50) -> list[dict[str, Any]]:
        stmt = (
            select(VersionRow)
            .where(VersionRow.project_id == project_id)
            .order_by(VersionRow.created_at.desc())
            .limit(limit)
        )
        return [self._version(row) for row in (await self._session.execute(stmt)).scalars()]

    @staticmethod
    def _version(row: VersionRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "project_id": row.project_id,
            "parent_id": row.parent_id,
            "run_id": row.run_id,
            "step_key": row.step_key,
            "spec": row.content_json,
            "dialogue_profile": row.dialogue_profile_json,
            "spec_hash": row.spec_hash,
            "semantic_hash": row.semantic_hash,
            "manifest_hash": row.manifest_hash,
            "dialogue_profile_hash": row.dialogue_profile_hash,
            "runtime_version": row.runtime_version,
            "created_at": row.created_at.isoformat(),
        }


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_session(self, session_model: ConversationSession, profile_payload: dict[str, Any] | None = None) -> None:
        self._session.add(
            ConversationSessionRow(
                id=session_model.id,
                kind=session_model.kind.value,
                actor_id=session_model.actor_id,
                project_id=session_model.project_id,
                version_id=session_model.version_id,
                profile_hash=session_model.profile_hash,
                profile_json=profile_payload,
                share_id=session_model.share_id,
                context_hash=session_model.context_hash,
                status=session_model.status,
                expires_at=session_model.expires_at,
                created_at=session_model.created_at or _now(),
            )
        )
        await self._session.flush()

    async def get_session(self, session_id: str) -> ConversationSession | None:
        row = await self._session.get(ConversationSessionRow, session_id)
        if row is None:
            return None
        from server.domain.conversations import SessionKind

        return ConversationSession(
            id=row.id,
            kind=SessionKind(row.kind),
            actor_id=row.actor_id,
            project_id=row.project_id,
            version_id=row.version_id,
            profile_hash=row.profile_hash,
            share_id=row.share_id,
            context_hash=row.context_hash,
            status=row.status,  # type: ignore[arg-type]
            expires_at=_aware(row.expires_at),
            created_at=_aware(row.created_at),
        )

    async def session_profile(self, session_id: str) -> dict[str, Any] | None:
        row = await self._session.get(ConversationSessionRow, session_id)
        return row.profile_json if row else None

    async def revoke_sessions_for_share(self, share_id: str) -> int:
        stmt = select(ConversationSessionRow).where(ConversationSessionRow.share_id == share_id)
        rows = list((await self._session.execute(stmt)).scalars())
        for row in rows:
            row.status = "revoked"
        await self._session.flush()
        return len(rows)

    async def count_turns(self, session_id: str) -> int:
        stmt = select(sa.func.count()).select_from(ConversationTurnRow).where(ConversationTurnRow.session_id == session_id)
        return int((await self._session.execute(stmt)).scalar_one())

    async def active_turn(self, session_id: str) -> ConversationTurn | None:
        stmt = (
            select(ConversationTurnRow)
            .where(
                ConversationTurnRow.session_id == session_id,
                ConversationTurnRow.status.in_(["queued", "streaming"]),
            )
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._turn(row) if row else None

    async def find_turn(self, session_id: str, client_turn_id: str) -> ConversationTurn | None:
        stmt = select(ConversationTurnRow).where(
            ConversationTurnRow.session_id == session_id,
            ConversationTurnRow.client_turn_id == client_turn_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._turn(row) if row else None

    async def add_turn(self, turn: ConversationTurn, context: dict[str, Any]) -> ConversationTurn:
        self._session.add(
            ConversationTurnRow(
                id=turn.id,
                session_id=turn.session_id,
                client_turn_id=turn.client_turn_id,
                request_hash=turn.request_hash,
                context_hash=turn.context_hash,
                sequence=turn.sequence,
                status=turn.status.value,
                user_message=turn.user_message,
                partial_text=turn.partial_text,
                final_text=turn.final_text,
                answerability=turn.answerability.value if turn.answerability else None,
                citations=[c.to_payload() for c in turn.citations],
                suggested_actions=[a.to_payload() for a in turn.suggested_actions],
                context_json=context,
                cost_status=turn.cost_status,
                cost_micros=turn.cost_micros,
                created_at=turn.created_at or _now(),
            )
        )
        await self._session.flush()
        return turn

    async def save_turn(self, turn: ConversationTurn) -> None:
        row = await self._session.get(ConversationTurnRow, turn.id)
        if row is None:
            from server.domain.shared.errors import NotFound

            raise NotFound(object_id=turn.id)
        row.status = turn.status.value
        row.partial_text = turn.partial_text
        row.final_text = turn.final_text
        row.answerability = turn.answerability.value if turn.answerability else None
        row.citations = [c.to_payload() for c in turn.citations]
        row.suggested_actions = [a.to_payload() for a in turn.suggested_actions]
        row.provider_call_ref = turn.provider_call_ref
        row.cost_status = turn.cost_status
        row.cost_micros = turn.cost_micros
        row.error_code = turn.error_code
        row.finished_at = turn.finished_at
        await self._session.flush()

    async def get_turn(self, turn_id: str) -> ConversationTurn | None:
        row = await self._session.get(ConversationTurnRow, turn_id)
        return self._turn(row) if row else None

    async def get_turn_for_update(self, turn_id: str) -> ConversationTurn | None:
        """Row-locked read used to claim or finalise a turn exactly once."""
        stmt = select(ConversationTurnRow).where(ConversationTurnRow.id == turn_id).with_for_update()
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._turn(row) if row else None

    async def count_turns_by_actor(self, actor_id: str) -> int:
        stmt = (
            select(sa.func.count())
            .select_from(ConversationTurnRow)
            .join(ConversationSessionRow, ConversationSessionRow.id == ConversationTurnRow.session_id)
            .where(ConversationSessionRow.actor_id == actor_id)
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def count_turns_in_project(self, project_id: str) -> int:
        stmt = (
            select(sa.func.count())
            .select_from(ConversationTurnRow)
            .join(ConversationSessionRow, ConversationSessionRow.id == ConversationTurnRow.session_id)
            .where(ConversationSessionRow.project_id == project_id)
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def recent_messages(self, session_id: str, limit: int) -> list[dict[str, str]]:
        stmt = (
            select(ConversationTurnRow)
            .where(
                ConversationTurnRow.session_id == session_id,
                ConversationTurnRow.status == "succeeded",
            )
            .order_by(ConversationTurnRow.sequence.desc())
            .limit(limit)
        )
        rows = list((await self._session.execute(stmt)).scalars())
        messages: list[dict[str, str]] = []
        for row in reversed(rows):
            messages.append({"role": "user", "content": row.user_message})
            if row.final_text:
                messages.append({"role": "assistant", "content": row.final_text})
        return messages

    @staticmethod
    def _turn(row: ConversationTurnRow) -> ConversationTurn:
        from server.domain.conversations import Answerability, Citation, SuggestedAction

        return ConversationTurn(
            id=row.id,
            session_id=row.session_id,
            client_turn_id=row.client_turn_id,
            sequence=row.sequence,
            user_message=row.user_message,
            request_hash=row.request_hash,
            context_hash=row.context_hash,
            status=TurnStatus(row.status),
            partial_text=row.partial_text,
            final_text=row.final_text,
            answerability=Answerability(row.answerability) if row.answerability else None,
            citations=tuple(Citation(**citation) for citation in (row.citations or [])),
            suggested_actions=tuple(SuggestedAction(**action) for action in (row.suggested_actions or [])),
            provider_call_ref=row.provider_call_ref,
            cost_status=row.cost_status,
            cost_micros=row.cost_micros,
            error_code=row.error_code,
            created_at=_aware(row.created_at),
            finished_at=_aware(row.finished_at),
        )


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, actor_id: str, scope: str, key: str) -> dict[str, Any] | None:
        row = await self._session.get(IdempotencyRow, {"actor_id": actor_id, "scope": scope, "key": key})
        if row is None:
            return None
        return {"request_hash": row.request_hash, "resource_id": row.resource_id, "response": row.response_json}

    async def put(
        self,
        *,
        actor_id: str,
        scope: str,
        key: str,
        request_hash: str,
        resource_id: str | None,
        response: dict[str, Any],
    ) -> None:
        self._session.add(
            IdempotencyRow(
                actor_id=actor_id,
                scope=scope,
                key=key,
                request_hash=request_hash,
                resource_id=resource_id,
                response_json=response,
                created_at=_now(),
            )
        )
        await self._session.flush()


class SharesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        share_id: str,
        project_id: str,
        version_id: str,
        token_hash: str,
        expires_at: datetime,
        license_ack: bool = True,
    ) -> None:
        from server.infrastructure.db.tables import ShareRow

        self._session.add(
            ShareRow(
                id=share_id,
                project_id=project_id,
                version_id=version_id,
                token_hash=token_hash,
                expires_at=expires_at,
                license_ack=license_ack,
                created_at=_now(),
            )
        )
        await self._session.flush()

    async def get(self, share_id: str) -> dict[str, Any] | None:
        from server.infrastructure.db.tables import ShareRow

        row = await self._session.get(ShareRow, share_id)
        if row is None:
            return None
        return {
            "id": row.id,
            "project_id": row.project_id,
            "version_id": row.version_id,
            "token_hash": row.token_hash,
            "expires_at": row.expires_at,
            "revoked_at": row.revoked_at,
            "license_ack": row.license_ack,
        }

    async def find_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        from server.infrastructure.db.tables import ShareRow

        stmt = select(ShareRow).where(ShareRow.token_hash == token_hash)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": row.id,
            "project_id": row.project_id,
            "version_id": row.version_id,
            "token_hash": row.token_hash,
            "expires_at": row.expires_at,
            "revoked_at": row.revoked_at,
            "license_ack": row.license_ack,
        }

    async def revoke(self, share_id: str) -> None:
        from server.infrastructure.db.tables import ShareRow

        row = await self._session.get(ShareRow, share_id)
        if row is not None:
            row.revoked_at = _now()
            await self._session.flush()

    async def project_for(self, share_id: str) -> str | None:
        record = await self.get(share_id)
        return None if record is None else str(record["project_id"])

    async def list_for_project(self, project_id: str) -> list[dict[str, Any]]:
        from server.infrastructure.db.tables import ShareRow

        stmt = select(ShareRow).where(ShareRow.project_id == project_id).order_by(ShareRow.created_at.desc())
        return [
            {
                "id": row.id,
                "version_id": row.version_id,
                "expires_at": row.expires_at,
                "revoked_at": row.revoked_at,
                "license_ack": row.license_ack,
            }
            for row in (await self._session.execute(stmt)).scalars()
        ]


class ReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        review_id: str,
        version_id: str,
        project_id: str,
        semantic_hash: str,
        reviewer_id: str,
        decision: str,
        notes: str,
        coverage_claim_ids: list[str],
    ) -> None:
        from server.infrastructure.db.tables import ContentReviewRow

        self._session.add(
            ContentReviewRow(
                id=review_id,
                version_id=version_id,
                project_id=project_id,
                semantic_hash=semantic_hash,
                reviewer_id=reviewer_id,
                decision=decision,
                notes=notes,
                coverage_claim_ids=coverage_claim_ids,
                created_at=_now(),
            )
        )
        await self._session.flush()

    async def latest_for(self, version_id: str) -> dict[str, Any] | None:
        from server.infrastructure.db.tables import ContentReviewRow

        stmt = (
            select(ContentReviewRow)
            .where(ContentReviewRow.version_id == version_id)
            .order_by(ContentReviewRow.created_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": row.id,
            "version_id": row.version_id,
            "semantic_hash": row.semantic_hash,
            "reviewer_id": row.reviewer_id,
            "decision": row.decision,
            "notes": row.notes,
            "coverage_claim_ids": row.coverage_claim_ids,
            "created_at": row.created_at,
        }

    async def add_report(
        self,
        *,
        report_id: str,
        version_id: str,
        project_id: str,
        spec_hash: str,
        source_hash: str,
        runtime_hash: str,
        checker_version: str,
        layer: str,
        status: str,
        evidence_manifest: dict[str, Any],
    ) -> None:
        from server.infrastructure.db.tables import ValidationReportRow

        self._session.add(
            ValidationReportRow(
                id=report_id,
                version_id=version_id,
                project_id=project_id,
                spec_hash=spec_hash,
                source_hash=source_hash,
                runtime_hash=runtime_hash,
                checker_version=checker_version,
                layer=layer,
                status=status,
                evidence_manifest=evidence_manifest,
                created_at=_now(),
            )
        )
        await self._session.flush()

    async def reports_for(self, version_id: str) -> list[dict[str, Any]]:
        from server.infrastructure.db.tables import ValidationReportRow

        stmt = (
            select(ValidationReportRow)
            .where(ValidationReportRow.version_id == version_id)
            .order_by(ValidationReportRow.created_at.desc())
        )
        return [
            {
                "id": row.id,
                "version_id": row.version_id,
                "spec_hash": row.spec_hash,
                "checker_version": row.checker_version,
                "layer": row.layer,
                "status": row.status,
                "evidence_manifest": row.evidence_manifest,
                "created_at": row.created_at,
            }
            for row in (await self._session.execute(stmt)).scalars()
        ]


class ExperienceSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        session_id: str,
        share_id: str,
        version_id: str,
        project_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        from server.infrastructure.db.tables import ExperienceSessionRow

        self._session.add(
            ExperienceSessionRow(
                id=session_id,
                share_id=share_id,
                version_id=version_id,
                project_id=project_id,
                token_hash=token_hash,
                status="active",
                expires_at=expires_at,
                created_at=_now(),
            )
        )
        await self._session.flush()

    async def get(self, session_id: str) -> dict[str, Any] | None:
        from server.infrastructure.db.tables import ExperienceSessionRow

        row = await self._session.get(ExperienceSessionRow, session_id)
        if row is None:
            return None
        return {
            "id": row.id,
            "share_id": row.share_id,
            "version_id": row.version_id,
            "project_id": row.project_id,
            "status": row.status,
            "expires_at": _aware(row.expires_at),
        }

    async def revoke_for_share(self, share_id: str) -> int:
        from server.infrastructure.db.tables import ExperienceSessionRow

        stmt = select(ExperienceSessionRow).where(ExperienceSessionRow.share_id == share_id)
        rows = list((await self._session.execute(stmt)).scalars())
        for row in rows:
            row.status = "revoked"
        await self._session.flush()
        return len(rows)
