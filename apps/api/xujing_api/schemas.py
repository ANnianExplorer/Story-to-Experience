"""Pydantic request/response models for the public API (mirrors docs/spec/api.md)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BriefModel(BaseModel):
    audience: str = Field(min_length=1, max_length=120)
    duration_minutes: int = Field(ge=1, le=30)
    learning_goals: list[str] = Field(min_length=1, max_length=6)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brief: BriefModel


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    brief: BriefModel | None = None
    expected_revision: int | None = Field(default=None, ge=1)


class ClaimInput(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    statement: str = Field(min_length=1, max_length=2000)
    content_type: Literal["supported", "legend", "adaptation", "unconfirmed"]
    evidence_span_ids: list[str] = Field(default_factory=list, max_length=20)
    qualifier: str | None = Field(default=None, max_length=300)


class ClaimsRequest(BaseModel):
    claims: list[ClaimInput] = Field(min_length=1, max_length=200)


class SnapshotRequest(BaseModel):
    source_ids: list[str] = Field(min_length=1, max_length=20)


class RunRequest(BaseModel):
    source_snapshot_id: str
    brief_revision: int = Field(ge=1)
    auto_continue: bool = False
    instruction: str = Field(default="", max_length=2000)


class ReviewRequest(BaseModel):
    decision: Literal["approved", "needs_changes"]
    notes: str = Field(default="", max_length=4000)
    coverage_claim_ids: list[str] = Field(min_length=1, max_length=200)
    expected_semantic_hash: str = Field(min_length=64, max_length=64)


class StableRequest(BaseModel):
    version_id: str


class ShareRequest(BaseModel):
    version_id: str
    license_ack: bool
    hours: int = Field(default=72, ge=1, le=720)


class ExportRequest(BaseModel):
    mode: Literal["draft", "formal"]


class ConversationCreate(BaseModel):
    kind: Literal["creator"] = "creator"
    base_version_id: str | None = None


class TurnRequest(BaseModel):
    client_turn_id: str = Field(min_length=8, max_length=64)
    message: str = Field(min_length=1, max_length=4000)
    scene_id: str | None = Field(default=None, max_length=64)
    flags: list[str] = Field(default_factory=list, max_length=12)


class GuideConversationCreate(BaseModel):
    kind: Literal["guide"] = "guide"


class ActorInfo(BaseModel):
    id: str
    display_name: str = ""
    kind: str = "human"


class DataEnvelope(BaseModel):
    data: Any
    request_id: str
    next_cursor: str | None = None
