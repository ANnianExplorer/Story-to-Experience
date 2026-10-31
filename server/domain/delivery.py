"""Delivery rules: review decisions, share tokens, export gating (F08)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .shared.errors import Conflict, ValidationFailure

SHARE_TOKEN_BYTES = 32  # 256 bits of entropy
ReviewDecision = Literal["approved", "needs_changes"]


def issue_share_token() -> tuple[str, str]:
    """Return (raw_token, token_hash). Only the hash is persisted."""
    raw = secrets.token_urlsafe(SHARE_TOKEN_BYTES)
    return raw, hash_share_token(raw)


def hash_share_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_share_token(raw: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_share_token(raw), stored_hash)


@dataclass(frozen=True, slots=True)
class Share:
    id: str
    project_id: str
    version_id: str
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None = None
    license_ack: bool = False

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now and self.license_ack


@dataclass(frozen=True, slots=True)
class ContentReview:
    id: str
    version_id: str
    semantic_hash: str
    reviewer_id: str
    decision: ReviewDecision
    notes: str
    coverage_claim_ids: tuple[str, ...]
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.decision not in ("approved", "needs_changes"):
            raise ValidationFailure("INVALID_REVIEW", "审核结论必须是 approved 或 needs_changes。")
        if not self.reviewer_id:
            raise ValidationFailure("INVALID_REVIEW", "审核必须记录审核人。")

    @staticmethod
    def reject_model_approval(actor_kind: str) -> None:
        if actor_kind != "human":
            raise Conflict("MODEL_CANNOT_APPROVE", "模型或 Agent 不能提交内容批准。")


@dataclass(frozen=True, slots=True)
class ExportRequest:
    id: str
    version_id: str
    mode: Literal["draft", "formal"]
    manifest_hash: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in ("draft", "formal"):
            raise ValidationFailure("INVALID_EXPORT_MODE", "导出模式必须是 draft 或 formal。")
