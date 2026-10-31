"""Source documents, spans, claims and immutable snapshots (F02).

Rules:
- offsets are Unicode code point half-open intervals into normalised text;
- a scanned/blank PDF is a failure (NO_EXTRACTABLE_TEXT), never a ready empty
  document;
- ``supported`` and ``legend`` claims must carry evidence spans;
- snapshots are immutable manifests binding document hashes, parse versions,
  spans and claim revisions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from .errors import Conflict, ValidationFailure

ContentType = Literal["supported", "legend", "adaptation", "unconfirmed"]
CONTENT_TYPES: frozenset[str] = frozenset({"supported", "legend", "adaptation", "unconfirmed"})
EVIDENCE_REQUIRED: frozenset[str] = frozenset({"supported", "legend"})
ParseStatus = Literal["pending", "parsing", "ready", "failed"]

MAX_TEXT_SOURCE_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_SPANS_PER_DOCUMENT = 5000
MAX_CLAIM_STATEMENT = 2000


def validate_content_type(value: str) -> ContentType:
    if value not in CONTENT_TYPES:
        raise ValidationFailure("INVALID_CONTENT_TYPE", "内容性质必须是 supported/legend/adaptation/unconfirmed。", {"value": value})
    return value  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class SourceSpan:
    id: str
    source_id: str
    parse_version: int
    page: int | None
    paragraph: int
    start_cp: int
    end_cp: int
    quote: str
    text_hash: str
    ordinal: int

    def __post_init__(self) -> None:
        if self.start_cp < 0 or self.end_cp < self.start_cp:
            raise ValidationFailure("INVALID_SPAN", "片段区间不合法。", {"span_id": self.id})
        if not self.quote.strip():
            raise ValidationFailure("INVALID_SPAN", "片段文本不能为空。", {"span_id": self.id})

    @property
    def length(self) -> int:
        return self.end_cp - self.start_cp


@dataclass(slots=True)
class SourceDocument:
    id: str
    project_id: str
    sha256: str
    storage_key: str
    mime_type: str
    license_note: str
    title: str
    parse_status: ParseStatus = "pending"
    parse_version: int = 1
    normalized_text: str = ""
    error_code: str | None = None
    created_at: datetime | None = None

    def require_ready(self) -> str:
        if self.parse_status != "ready":
            raise ValidationFailure(
                "SOURCE_NOT_READY",
                "资料尚未解析完成。",
                {"source_id": self.id, "parse_status": self.parse_status, "error_code": self.error_code},
            )
        return self.normalized_text


@dataclass(slots=True)
class Claim:
    id: str
    project_id: str
    revision: int
    statement: str
    content_type: ContentType
    evidence_span_ids: tuple[str, ...]
    qualifier: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        statement = self.statement.strip()
        if not statement:
            raise ValidationFailure("INVALID_CLAIM", "事实陈述不能为空。", {"claim_id": self.id})
        if len(statement) > MAX_CLAIM_STATEMENT:
            raise ValidationFailure("INVALID_CLAIM", "事实陈述过长。", {"claim_id": self.id})
        validate_content_type(self.content_type)
        if self.content_type in EVIDENCE_REQUIRED and not self.evidence_span_ids:
            raise ValidationFailure(
                "CLAIM_REQUIRES_EVIDENCE",
                "supported/legend 事实必须绑定证据片段。",
                {"claim_id": self.id, "content_type": self.content_type},
            )
        self.statement = statement


@dataclass(frozen=True, slots=True)
class SnapshotManifestEntry:
    source_id: str
    sha256: str
    parse_version: int
    span_hashes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SnapshotManifest:
    project_id: str
    documents: tuple[SnapshotManifestEntry, ...]
    claims: tuple[dict[str, object], ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "documents": [
                {
                    "source_id": doc.source_id,
                    "sha256": doc.sha256,
                    "parse_version": doc.parse_version,
                    "span_hashes": list(doc.span_hashes),
                }
                for doc in self.documents
            ],
            "claims": [dict(claim) for claim in self.claims],
        }


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    id: str
    project_id: str
    sha256: str
    manifest: SnapshotManifest
    created_at: datetime | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "sha256": self.sha256,
            "manifest": self.manifest.to_payload(),
        }


def ensure_snapshot_usable(snapshot: SourceSnapshot | None, project_id: str) -> SourceSnapshot:
    if snapshot is None:
        raise ValidationFailure("SNAPSHOT_REQUIRED", "缺少冻结的来源快照。", {"project_id": project_id})
    if snapshot.project_id != project_id:
        raise Conflict("SNAPSHOT_PROJECT_MISMATCH", "来源快照不属于当前项目。", object_id=snapshot.id)
    return snapshot
