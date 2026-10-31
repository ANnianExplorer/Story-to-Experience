"""SQLAlchemy table definitions (PostgreSQL in production, SQLite for unit tests).

Constraints mirror docs/spec/data-model.md. Database constraints are the second
line of defence; application invariants are still enforced in the domain.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSONType = sa.JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def _ts(*args: object, **kwargs: object) -> sa.Column:
    return sa.Column(sa.DateTime(timezone=True), *args, **kwargs)


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(sa.String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    brief_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    brief_revision: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    revision_head_id: Mapped[str | None] = mapped_column(sa.String(36))
    latest_candidate_version_id: Mapped[str | None] = mapped_column(sa.String(36))
    selected_version_id: Mapped[str | None] = mapped_column(sa.String(36))
    stable_version_id: Mapped[str | None] = mapped_column(sa.String(36))
    active_revision_run_id: Mapped[str | None] = mapped_column(sa.String(36))
    created_at = _ts(nullable=False)
    updated_at = _ts(nullable=False)


class BriefRevisionRow(Base):
    __tablename__ = "project_brief_revisions"

    project_id: Mapped[str] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    revision: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    brief_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    note: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    created_at = _ts(nullable=False)


class SourceDocumentRow(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    mime_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    license_note: Mapped[str] = mapped_column(sa.Text, nullable=False)
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    parse_status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="pending")
    parse_version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    normalized_text: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    error_code: Mapped[str | None] = mapped_column(sa.String(64))
    created_at = _ts(nullable=False)


class SourceSpanRow(Base):
    __tablename__ = "source_spans"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(sa.ForeignKey("source_documents.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(sa.String(36), index=True, nullable=False)
    parse_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(sa.Integer)
    paragraph: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    start_cp: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    end_cp: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    quote: Mapped[str] = mapped_column(sa.Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    __table_args__ = (
        sa.UniqueConstraint("source_id", "parse_version", "ordinal", name="uq_span_ordinal"),
        sa.CheckConstraint("end_cp >= start_cp", name="ck_span_range"),
    )


class ClaimRow(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    revision: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    statement: Mapped[str] = mapped_column(sa.Text, nullable=False)
    content_type: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    evidence_span_ids: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    qualifier: Mapped[str | None] = mapped_column(sa.Text)
    created_at = _ts(nullable=False)
    __table_args__ = (sa.UniqueConstraint("project_id", "id", "revision", name="uq_claim_revision"),)


class SourceSnapshotRow(Base):
    __tablename__ = "source_snapshots"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    manifest_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    created_at = _ts(nullable=False)


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    stage: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    input_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    source_snapshot_id: Mapped[str | None] = mapped_column(sa.String(36))
    base_version_id: Mapped[str | None] = mapped_column(sa.String(36))
    attempt: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    lease_owner: Mapped[str | None] = mapped_column(sa.String(120))
    lease_expires_at = _ts()
    fencing_token: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    last_sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    counters: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(sa.String(64))
    created_at = _ts(nullable=False)
    finished_at = _ts()


class RunStepRow(Base):
    __tablename__ = "run_steps"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(sa.ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False)
    step_key: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    input_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    stage_version: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    output_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    output_ref: Mapped[str | None] = mapped_column(sa.String(200))
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at = _ts(nullable=False)
    __table_args__ = (sa.UniqueConstraint("run_id", "step_key", "input_hash", "stage_version", name="uq_run_step"),)


class RunEventRow(Base):
    __tablename__ = "run_events"

    run_id: Mapped[str] = mapped_column(sa.ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    sequence: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    type: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at = _ts(nullable=False)


class ModelCallRow(Base):
    __tablename__ = "model_calls"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(sa.ForeignKey("runs.id", ondelete="SET NULL"), index=True)
    agent_task_id: Mapped[str | None] = mapped_column(sa.String(36), index=True)
    provider: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    model: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(sa.String(200))
    attempt: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(sa.Integer)
    output_tokens: Mapped[int | None] = mapped_column(sa.Integer)
    currency: Mapped[str | None] = mapped_column(sa.String(3))
    cost_micros: Mapped[int | None] = mapped_column(sa.BigInteger)
    cost_status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    role: Mapped[str | None] = mapped_column(sa.String(40))
    mock: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(sa.String(64))
    started_at = _ts()
    finished_at = _ts()


class IdempotencyRow(Base):
    __tablename__ = "idempotency_requests"

    actor_id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(sa.String(160), primary_key=True)
    key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    request_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(sa.String(36))
    response_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at = _ts(nullable=False)


class AgentPlanRow(Base):
    __tablename__ = "agent_plans"

    run_id: Mapped[str] = mapped_column(sa.ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    plan_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at = _ts(nullable=False)


class AgentTaskRow(Base):
    __tablename__ = "agent_tasks"

    task_id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(sa.ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(sa.String(36), index=True, nullable=False)
    parent_task_id: Mapped[str | None] = mapped_column(sa.String(36))
    agent_id: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    role: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    profile_version: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="pending")
    envelope: Mapped[dict] = mapped_column(JSONType, nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSONType)
    artifact_refs: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    usage: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at = _ts(nullable=False)
    updated_at = _ts(nullable=False)


class AgentArtifactRow(Base):
    __tablename__ = "agent_artifacts"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(sa.ForeignKey("agent_tasks.task_id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(sa.String(36), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    schema_version: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False)
    citation_refs: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    created_at = _ts(nullable=False)


class ConversationSessionRow(Base):
    __tablename__ = "conversation_sessions"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(sa.String(64), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(sa.String(36), index=True, nullable=False)
    version_id: Mapped[str | None] = mapped_column(sa.String(36))
    profile_hash: Mapped[str | None] = mapped_column(sa.String(64))
    profile_json: Mapped[dict | None] = mapped_column(JSONType)
    share_id: Mapped[str | None] = mapped_column(sa.String(36))
    context_hash: Mapped[str | None] = mapped_column(sa.String(64))
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="active")
    expires_at = _ts()
    created_at = _ts(nullable=False)


class ConversationTurnRow(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        sa.ForeignKey("conversation_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    client_turn_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    context_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="queued")
    user_message: Mapped[str] = mapped_column(sa.Text, nullable=False)
    partial_text: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    final_text: Mapped[str | None] = mapped_column(sa.Text)
    answerability: Mapped[str | None] = mapped_column(sa.String(16))
    citations: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    suggested_actions: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    context_json: Mapped[dict | None] = mapped_column(JSONType)
    # Gateway request ids are not UUIDs; keep room for provider-specific formats.
    provider_call_ref: Mapped[str | None] = mapped_column(sa.String(128))
    cost_status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="unknown")
    cost_micros: Mapped[int | None] = mapped_column(sa.BigInteger)
    error_code: Mapped[str | None] = mapped_column(sa.String(64))
    created_at = _ts(nullable=False)
    finished_at = _ts()
    __table_args__ = (
        sa.UniqueConstraint("session_id", "client_turn_id", name="uq_turn_idempotency"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_turn_sequence"),
    )


class VersionRow(Base):
    __tablename__ = "experience_versions"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(sa.String(36))
    run_id: Mapped[str | None] = mapped_column(sa.String(36))
    step_key: Mapped[str | None] = mapped_column(sa.String(120))
    content_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    dialogue_profile_json: Mapped[dict | None] = mapped_column(JSONType)
    spec_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    semantic_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    dialogue_profile_hash: Mapped[str | None] = mapped_column(sa.String(64))
    runtime_version: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    created_at = _ts(nullable=False)
    __table_args__ = (sa.UniqueConstraint("run_id", "step_key", name="uq_version_step"),)


class ValidationReportRow(Base):
    __tablename__ = "validation_reports"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(sa.String(36), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(sa.String(36), index=True, nullable=False)
    spec_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    source_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    runtime_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    checker_version: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    layer: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    evidence_manifest: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at = _ts(nullable=False)


class ContentReviewRow(Base):
    __tablename__ = "content_reviews"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(sa.String(36), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(sa.String(36), index=True, nullable=False)
    semantic_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    decision: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    notes: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    coverage_claim_ids: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    created_at = _ts(nullable=False)


class ShareRow(Base):
    __tablename__ = "shares"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(sa.String(36), index=True, nullable=False)
    version_id: Mapped[str] = mapped_column(sa.String(36), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    expires_at = _ts(nullable=False)
    revoked_at = _ts()
    license_ack: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    created_at = _ts(nullable=False)


class ExperienceSessionRow(Base):
    __tablename__ = "experience_sessions"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    share_id: Mapped[str] = mapped_column(sa.ForeignKey("shares.id", ondelete="CASCADE"), nullable=False)
    version_id: Mapped[str] = mapped_column(sa.String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(sa.String(36), nullable=False)
    token_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="active")
    expires_at = _ts(nullable=False)
    created_at = _ts(nullable=False)
