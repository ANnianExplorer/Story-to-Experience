"""Auto-extract claims from a frozen snapshot (F02-R03).

The Evidence agent already knows how to read spans and label provenance. This
service lets the **creator** get those claims without typing each one: upload the
material, freeze a snapshot, and the machine proposes the facts. The creator can
then correct or delete them; nothing here approves content.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from server.application.generation.roles import EVIDENCE_SCHEMA, ROLE_PROMPTS, extract_json, validate_payload
from server.application.ports import ModelProvider, ScopeFactory
from server.domain.agents import AgentRole
from server.domain.evidence import Claim, SourceSnapshot
from server.domain.runs import BudgetLedger
from server.domain.shared.errors import Conflict, NotFound, ValidationFailure


@dataclass(frozen=True, slots=True)
class ExtractedClaim:
    statement: str
    content_type: str
    evidence_span_ids: tuple[str, ...]
    qualifier: str | None


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    claims: tuple[ExtractedClaim, ...]
    gaps: tuple[str, ...]
    ordering_facts: tuple[dict[str, object], ...]
    model: str
    cost_status: str


class ClaimExtractionService:
    """Propose claims for a snapshot, bounded by a small dedicated budget."""

    def __init__(self, uow: ScopeFactory, provider: ModelProvider) -> None:
        self._uow = uow
        self._provider = provider

    async def extract(
        self,
        actor_id: str,
        project_id: str,
        snapshot_id: str,
        *,
        max_spans: int = 40,
    ) -> ExtractionResult:
        async with self._uow() as uow:
            project = await uow.projects.get(project_id)
            if project is None:
                raise NotFound(object_id=project_id)
            project.assert_owned_by(actor_id)
            snapshot = await uow.evidence.get_snapshot(snapshot_id)
            if snapshot is None or snapshot.project_id != project_id:
                raise NotFound(object_id=snapshot_id)
            spans: list[dict[str, str]] = []
            for entry in snapshot.manifest.documents:
                rows = await uow.evidence.spans_for(entry.source_id, entry.parse_version)
                allowed = {part.split(":", 1)[0] for part in entry.span_hashes}
                for row in rows:
                    if row.id in allowed:
                        spans.append({"span_id": row.id, "quote": row.quote[:400]})
            if not spans:
                raise ValidationFailure(
                    "SNAPSHOT_NO_SPANS",
                    "该快照没有可引用的片段，无法抽取事实。",
                    {"snapshot_id": snapshot_id},
                )

        # Keep the prompt bounded; the caller sees how many spans were used.
        selected = spans[:max_spans]
        budget = BudgetLedger(max_calls=2, max_repair_rounds=0)
        prompt = (
            f"资料片段（JSON，含 span_id 与原文）：\n{json.dumps(selected, ensure_ascii=False)}\n"
            "请输出事实抽取 JSON。"
        )
        response = await self._provider.complete(
            role=AgentRole.EVIDENCE.value,
            system=ROLE_PROMPTS[AgentRole.EVIDENCE],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3500,
            budget=budget,
            json_schema=EVIDENCE_SCHEMA,
        )
        payload = validate_payload(extract_json(response.text), EVIDENCE_SCHEMA, "Evidence")
        allowed_ids = {span["span_id"] for span in selected}
        claims = tuple(
            ExtractedClaim(
                statement=claim["statement"],
                content_type=claim["content_type"],
                # A model-invented span id is dropped, never trusted.
                evidence_span_ids=tuple(
                    span for span in claim["evidence_span_ids"] if span in allowed_ids
                ),
                qualifier=claim.get("qualifier"),
            )
            for claim in payload["claims"]
        )
        return ExtractionResult(
            claims=claims,
            gaps=tuple(payload["gaps"]),
            ordering_facts=tuple(payload["ordering_facts"]),
            model=getattr(response, "model", "unknown"),
            cost_status=getattr(getattr(response, "cost_status", None), "value", "unknown"),
        )

    async def extract_and_save(
        self,
        actor_id: str,
        project_id: str,
        snapshot_id: str,
    ) -> ExtractionResult:
        """Extract and persist in one step, skipping statements already recorded."""
        result = await self.extract(actor_id, project_id, snapshot_id)
        async with self._uow() as uow:
            existing = {claim.statement for claim in await uow.evidence.latest_claims(project_id)}
        fresh = [claim for claim in result.claims if claim.statement not in existing]
        if fresh:
            from server.application.evidence import EvidenceService
            from server.infrastructure.storage.blobs import LocalBlobStore  # noqa: F401  (type only)

            # Reuse the normal claim use case so evidence/ownership checks apply.
            service = EvidenceService(self._uow, _NoBlobs())
            await service.add_claims(
                actor_id,
                project_id,
                [
                    {
                        "statement": claim.statement,
                        "content_type": claim.content_type,
                        "evidence_span_ids": list(claim.evidence_span_ids),
                        "qualifier": claim.qualifier,
                    }
                    for claim in fresh
                ],
            )
        return result


class _NoBlobs:
    """Placeholder blob store: claim insertion never touches storage."""

    async def put(self, data: bytes, sha256: str) -> str:  # pragma: no cover - never called
        raise AssertionError("claim extraction must not write blobs")

    async def get(self, storage_key: str) -> bytes:  # pragma: no cover - never called
        raise AssertionError("claim extraction must not read blobs")
