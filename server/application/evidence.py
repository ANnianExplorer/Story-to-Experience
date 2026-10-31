"""Evidence application service: upload → parse → spans → claims → snapshot (F02).

Parsing and claim extraction are orchestrated here; the domain objects own the
invariants. Files are content-addressed and their storage keys are generated
server-side — a client never supplies a path.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from server.application.ports import BlobStore, ScopeFactory
from server.domain.shared.canonical_json import canonical_sha256
from server.domain.shared.errors import Conflict, NotFound, ValidationFailure
from server.domain.evidence import (
    Claim,
    SourceDocument,
    SourceSnapshot,
    SourceSpan,
    SnapshotManifest,
    SnapshotManifestEntry,
    validate_content_type,
)
from server.domain.shared.ids import new_id
from server.domain.shared.text import paragraph_spans, sha256_bytes, sha256_text, slice_span
from server.infrastructure.parsing.documents import parse_source


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceService:
    def __init__(
        self,
        uow: ScopeFactory,
        blobs: BlobStore,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._uow = uow
        self._blobs = blobs
        # Injectable ID source: production uses UUIDs, tests use fixed IDs so
        # scripted model artifacts can reference real spans and claims.
        self._new_id = id_factory or new_id

    async def upload(
        self,
        actor_id: str,
        project_id: str,
        *,
        filename: str,
        data: bytes,
        license_note: str,
        declared_content_type: str | None = None,
    ) -> SourceDocument:
        if not license_note.strip():
            raise ValidationFailure("LICENSE_REQUIRED", "上传资料必须说明使用许可。", {"field": "license_note"})
        async with self._uow() as uow:
            project = await uow.projects.get(project_id)
            if project is None:
                raise NotFound(object_id=project_id)
            project.assert_owned_by(actor_id)

        digest = sha256_bytes(data)
        storage_key = await self._blobs.put(data, digest)
        document = SourceDocument(
            id=self._new_id(),
            project_id=project_id,
            sha256=digest,
            storage_key=storage_key,
            mime_type=declared_content_type or "text/plain",
            license_note=license_note.strip(),
            title=(filename or "未命名资料")[:200],
            parse_status="parsing",
            created_at=_now(),
        )
        async with self._uow() as uow:
            await uow.evidence.add_document(document)
            await uow.commit()

        try:
            parsed = parse_source(data, declared_content_type)
        except ValidationFailure as error:
            await self._mark_failed(document.id, error.code)
            raise
        return await self._store_parsed(document.id, parsed.text, parsed.mime_type, parsed.page_count)

    async def _mark_failed(self, source_id: str, code: str) -> None:
        async with self._uow() as uow:
            document = await uow.evidence.get_document(source_id)
            if document is None:
                return
            document.parse_status = "failed"
            document.error_code = code
            await uow.evidence.save_document(document)
            await uow.commit()

    async def _store_parsed(self, source_id: str, text: str, mime_type: str, page_count: int) -> SourceDocument:
        spans = build_spans(source_id=source_id, text=text, parse_version=1, page_count=page_count, id_factory=self._new_id)
        async with self._uow() as uow:
            document = await uow.evidence.get_document(source_id)
            if document is None:
                raise NotFound(object_id=source_id)
            document.normalized_text = text
            document.parse_status = "ready"
            document.parse_version = 1
            document.mime_type = mime_type
            document.error_code = None
            uow.evidence.prime_project(source_id, document.project_id)
            await uow.evidence.add_spans(spans)
            saved = await uow.evidence.save_document(document)
            await uow.commit()
        return saved

    async def get_document(self, actor_id: str, source_id: str) -> SourceDocument:
        async with self._uow() as uow:
            document = await uow.evidence.get_document(source_id)
            if document is None:
                raise NotFound(object_id=source_id)
            project = await uow.projects.get(document.project_id)
            if project is None or project.owner_id != actor_id:
                raise NotFound(object_id=source_id)
        return document

    async def spans(self, actor_id: str, source_id: str) -> list[SourceSpan]:
        document = await self.get_document(actor_id, source_id)
        if document.parse_status != "ready":
            raise ValidationFailure("SOURCE_NOT_READY", "资料尚未解析完成。", {"parse_status": document.parse_status})
        async with self._uow() as uow:
            return await uow.evidence.spans_for(source_id, document.parse_version)

    async def add_claims(self, actor_id: str, project_id: str, claims: list[dict[str, object]]) -> list[Claim]:
        """Persist extracted claims. Every claim must cite spans of this project."""
        async with self._uow() as uow:
            project = await uow.projects.get(project_id)
            if project is None:
                raise NotFound(object_id=project_id)
            project.assert_owned_by(actor_id)
            existing = await uow.evidence.latest_claims(project_id)
            revisions = {claim.id: claim.revision for claim in existing}
            stored: list[Claim] = []
            for payload in claims:
                claim_id = str(payload.get("id") or self._new_id())
                claim = Claim(
                    id=claim_id,
                    project_id=project_id,
                    revision=revisions.get(claim_id, 0) + 1,
                    statement=str(payload.get("statement") or ""),
                    content_type=validate_content_type(str(payload.get("content_type") or "")),
                    evidence_span_ids=tuple(str(span) for span in (payload.get("evidence_span_ids") or [])),
                    qualifier=(str(payload["qualifier"]) if payload.get("qualifier") else None),
                    created_at=_now(),
                )
                for span_id in claim.evidence_span_ids:
                    span = await uow.evidence.get_span(span_id)
                    if span is None:
                        raise ValidationFailure(
                            "UNKNOWN_EVIDENCE",
                            "事实引用了不存在的证据片段。",
                            {"claim_id": claim.id, "span_id": span_id},
                        )
                    source = await uow.evidence.get_document(span.source_id)
                    if source is None or source.project_id != project_id:
                        raise Conflict("EVIDENCE_SCOPE_MISMATCH", "证据片段不属于当前项目。", object_id=span_id)
                stored.append(claim)
            for claim in stored:
                await uow.evidence.add_claim(claim)
            await uow.commit()
        return stored

    async def documents(self, actor_id: str, project_id: str) -> list[SourceDocument]:
        """List a project's materials so the workbench can restore state after a reload."""
        async with self._uow() as uow:
            project = await uow.projects.get(project_id)
            if project is None:
                raise NotFound(object_id=project_id)
            project.assert_owned_by(actor_id)
            return await uow.evidence.list_documents(project_id)

    async def claims(self, actor_id: str, project_id: str) -> list[Claim]:
        async with self._uow() as uow:
            project = await uow.projects.get(project_id)
            if project is None:
                raise NotFound(object_id=project_id)
            project.assert_owned_by(actor_id)
            return await uow.evidence.latest_claims(project_id)

    async def freeze_snapshot(self, actor_id: str, project_id: str, source_ids: list[str]) -> SourceSnapshot:
        if not source_ids:
            raise ValidationFailure("SNAPSHOT_EMPTY", "冻结快照至少需要一个资料。")
        async with self._uow() as uow:
            project = await uow.projects.get(project_id)
            if project is None:
                raise NotFound(object_id=project_id)
            project.assert_owned_by(actor_id)
            entries: list[SnapshotManifestEntry] = []
            for source_id in source_ids:
                document = await uow.evidence.get_document(source_id)
                if document is None or document.project_id != project_id:
                    raise NotFound(object_id=source_id)
                if document.parse_status != "ready":
                    raise ValidationFailure(
                        "SOURCE_NOT_READY",
                        "存在尚未解析完成的资料，不能冻结快照。",
                        {"source_id": source_id, "parse_status": document.parse_status},
                    )
                spans = await uow.evidence.spans_for(source_id, document.parse_version)
                if not spans:
                    raise ValidationFailure("SOURCE_NO_SPANS", "资料没有可引用的片段。", {"source_id": source_id})
                entries.append(
                    SnapshotManifestEntry(
                        source_id=source_id,
                        sha256=document.sha256,
                        parse_version=document.parse_version,
                        span_hashes=tuple(f"{span.id}:{span.text_hash}" for span in spans),
                    )
                )
            claims = await uow.evidence.latest_claims(project_id)
            allowed_spans = {
                span_id for entry in entries for span_id in (part.split(":", 1)[0] for part in entry.span_hashes)
            }
            claim_payloads = []
            for claim in claims:
                if not set(claim.evidence_span_ids) <= allowed_spans:
                    raise ValidationFailure(
                        "CLAIM_OUTSIDE_SNAPSHOT",
                        "事实引用了不在本次快照内的证据。",
                        {"claim_id": claim.id},
                    )
                claim_payloads.append(
                    {
                        "id": claim.id,
                        "revision": claim.revision,
                        "statement": claim.statement,
                        "content_type": claim.content_type,
                        "evidence_span_ids": list(claim.evidence_span_ids),
                        "qualifier": claim.qualifier,
                    }
                )
            manifest = SnapshotManifest(
                project_id=project_id, documents=tuple(entries), claims=tuple(claim_payloads)
            )
            snapshot = SourceSnapshot(
                id=self._new_id(),
                project_id=project_id,
                sha256=canonical_sha256(manifest.to_payload()),
                manifest=manifest,
                created_at=_now(),
            )
            await uow.evidence.add_snapshot(snapshot)
            await uow.commit()
        return snapshot

    async def snapshots(self, actor_id: str, project_id: str) -> list[SourceSnapshot]:
        """List frozen snapshots so a reloaded client can restore its frozen state."""
        async with self._uow() as uow:
            project = await uow.projects.get(project_id)
            if project is None:
                raise NotFound(object_id=project_id)
            project.assert_owned_by(actor_id)
            return await uow.evidence.list_snapshots(project_id)

    async def snapshot_for_generation(self, project_id: str, snapshot_id: str) -> SourceSnapshot:
        async with self._uow() as uow:
            snapshot = await uow.evidence.get_snapshot(snapshot_id)
        if snapshot is None or snapshot.project_id != project_id:
            raise NotFound(object_id=snapshot_id)
        return snapshot


def build_spans(
    *,
    source_id: str,
    text: str,
    parse_version: int,
    page_count: int,
    id_factory: Callable[[], str] | None = None,
) -> list[SourceSpan]:
    make_id = id_factory or new_id
    paragraphs = paragraph_spans(text)
    spans: list[SourceSpan] = []
    for ordinal, (start, end) in enumerate(paragraphs):
        quote = slice_span(text, start, end)
        # A text-layer PDF has no reliable page mapping per paragraph here; the
        # page field stays null rather than being guessed.
        page = None if page_count == 0 else None
        spans.append(
            SourceSpan(
                id=make_id(),
                source_id=source_id,
                parse_version=parse_version,
                page=page,
                paragraph=ordinal,
                start_cp=start,
                end_cp=end,
                quote=quote,
                text_hash=sha256_text(quote),
                ordinal=ordinal,
            )
        )
    return spans
