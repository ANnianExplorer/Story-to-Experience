"""Conversation sessions, turns, dialogue profiles and quotas (F11)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from .canonical_json import canonical_sha256
from .errors import Conflict, ValidationFailure

CONVERSATION_PROTOCOL_VERSION = "1.0.0"
MAX_MESSAGE_CHARS = 4000
MAX_ACTIVE_TURNS = 1
MAX_CITATIONS_PER_TURN = 12
SESSION_RETENTION_DAYS = 90


class SessionKind(StrEnum):
    CREATOR = "creator"
    GUIDE = "guide"


class TurnStatus(StrEnum):
    QUEUED = "queued"
    STREAMING = "streaming"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TURN_TERMINAL = frozenset({TurnStatus.SUCCEEDED, TurnStatus.FAILED, TurnStatus.CANCELLED})


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Answerability(StrEnum):
    ANSWERED = "answered"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class DialogueProfile:
    """Versioned companion config published with an experience version.

    ``source_scope`` is a *public projection* selector, not a permission: the
    application layer resolves it against published evidence only.
    ``adaptation_note`` must be shown to participants so fictional dialogue is
    never mistaken for historical quotation.
    """

    id: str
    profile_version: str
    persona_name: str
    persona_role: str
    adaptation_note: str
    source_scope: tuple[str, ...]
    objective_ids: tuple[str, ...]
    hint_policy: Literal["none", "gentle", "progressive"]
    max_hint_level: int
    allowed_actions: tuple[str, ...]
    model_policy_ref: str
    protocol_version: str = CONVERSATION_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if not self.persona_name.strip():
            raise ValidationFailure("INVALID_DIALOGUE_PROFILE", "角色名称不能为空。")
        if not self.adaptation_note.strip():
            raise ValidationFailure(
                "INVALID_DIALOGUE_PROFILE",
                "角色设定必须包含改编说明，避免伪装成历史原话。",
            )
        if self.hint_policy == "none" and self.max_hint_level != 0:
            raise ValidationFailure("INVALID_DIALOGUE_PROFILE", "无提示策略的 max_hint_level 必须为 0。")
        if not 0 <= self.max_hint_level <= 3:
            raise ValidationFailure("INVALID_DIALOGUE_PROFILE", "提示级别需在 0—3 之间。")
        allowed_actions(self.allowed_actions)
        if self.protocol_version != CONVERSATION_PROTOCOL_VERSION:
            raise ValidationFailure("PROTOCOL_VERSION_UNSUPPORTED", "对话协议版本不支持。")

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "protocol_version": self.protocol_version,
            "profile_version": self.profile_version,
            "persona": {"name": self.persona_name, "role": self.persona_role},
            "adaptation_note": self.adaptation_note,
            "source_scope": list(self.source_scope),
            "objective_ids": list(self.objective_ids),
            "hint_policy": self.hint_policy,
            "max_hint_level": self.max_hint_level,
            "allowed_actions": list(self.allowed_actions),
            "model_policy_ref": self.model_policy_ref,
        }

    def hash(self) -> str:
        return canonical_sha256(self.to_payload())


# Guide actions are whitelisted presentation actions. They never mutate task
# state; the engine remains the only writer of completion flags.
GUIDE_ACTION_WHITELIST: frozenset[str] = frozenset(
    {"open_source_card", "highlight_claim", "suggest_hint", "navigate_scene", "replay_scene"}
)


def allowed_actions(actions: tuple[str, ...]) -> tuple[str, ...]:
    unknown = set(actions) - GUIDE_ACTION_WHITELIST
    if unknown:
        raise ValidationFailure(
            "DIALOGUE_ACTION_NOT_ALLOWED",
            "对话配置包含未授权的建议动作。",
            {"unknown": sorted(unknown)},
        )
    if len(set(actions)) != len(actions):
        raise ValidationFailure("INVALID_DIALOGUE_PROFILE", "建议动作不能重复。")
    return actions


@dataclass(frozen=True, slots=True)
class Citation:
    span_id: str
    source_id: str
    label: str
    quote: str
    start_cp: int
    end_cp: int
    claim_ids: tuple[str, ...] = ()
    public: bool = True

    def __post_init__(self) -> None:
        if not self.public:
            raise ValidationFailure("PRIVATE_CITATION", "对话引用只能指向允许公开的证据投影。")
        if self.end_cp < self.start_cp:
            raise ValidationFailure("INVALID_CITATION", "引用区间不合法。")

    def to_payload(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "source_id": self.source_id,
            "label": self.label,
            "quote": self.quote,
            "start_cp": self.start_cp,
            "end_cp": self.end_cp,
            "claim_ids": list(self.claim_ids),
        }


@dataclass(frozen=True, slots=True)
class SuggestedAction:
    kind: str
    label: str
    scene_id: str | None = None
    claim_id: str | None = None
    level: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in GUIDE_ACTION_WHITELIST:
            raise ValidationFailure("DIALOGUE_ACTION_NOT_ALLOWED", f"未授权的建议动作：{self.kind}。")

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "scene_id": self.scene_id,
            "claim_id": self.claim_id,
            "level": self.level,
        }


@dataclass(slots=True)
class ConversationSession:
    id: str
    kind: SessionKind
    actor_id: str
    project_id: str
    version_id: str | None
    profile_hash: str | None
    status: Literal["active", "expired", "revoked"] = "active"
    context_hash: str | None = None
    share_id: str | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.kind is SessionKind.GUIDE:
            if self.version_id is None or self.profile_hash is None:
                raise ValidationFailure(
                    "INVALID_SESSION",
                    "Guide 会话必须绑定固定版本与对话配置。",
                )
            if self.share_id is None:
                raise ValidationFailure("INVALID_SESSION", "Guide 会话必须由分享会话创建。")
        else:
            if self.version_id is not None and not self.version_id:
                raise ValidationFailure("INVALID_SESSION", "创作会话的基准版本非法。")

    def require_active(self, now: datetime | None = None) -> None:
        if self.status != "active":
            raise Conflict("SESSION_INACTIVE", "会话已失效。", object_id=self.id)
        if self.expires_at is not None and now is not None:
            expires = self.expires_at
            if expires.tzinfo is None:
                # SQLite drops tzinfo; stored timestamps are always UTC.
                from datetime import timezone

                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= now:
                raise Conflict("SESSION_EXPIRED", "会话已过期。", object_id=self.id)


@dataclass(slots=True)
class ConversationTurn:
    id: str
    session_id: str
    client_turn_id: str
    sequence: int
    user_message: str
    request_hash: str
    context_hash: str
    status: TurnStatus = TurnStatus.QUEUED
    partial_text: str = ""
    final_text: str | None = None
    answerability: Answerability | None = None
    citations: tuple[Citation, ...] = ()
    suggested_actions: tuple[SuggestedAction, ...] = ()
    provider_call_ref: str | None = None
    cost_status: str = "unknown"
    cost_micros: int | None = None
    error_code: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.client_turn_id:
            raise ValidationFailure("INVALID_TURN", "缺少 client_turn_id 幂等键。")
        message = self.user_message.strip()
        if not message:
            raise ValidationFailure("INVALID_TURN", "消息不能为空。")
        if len(message) > MAX_MESSAGE_CHARS:
            raise ValidationFailure("INVALID_TURN", f"消息不能超过 {MAX_MESSAGE_CHARS} 字符。")
        self.user_message = message
        if self.status in TURN_TERMINAL and self.final_text is None and self.status is TurnStatus.SUCCEEDED:
            raise ValidationFailure("INVALID_TURN", "成功的 turn 必须有最终文本。")

    def request_fingerprint(self) -> str:
        return canonical_sha256({"client_turn_id": self.client_turn_id, "message": self.user_message, "context": self.context_hash})

    def start_streaming(self) -> None:
        if self.status is not TurnStatus.QUEUED:
            raise Conflict("TURN_NOT_QUEUED", "只有排队中的 turn 可以开始流式生成。", object_id=self.id)
        self.status = TurnStatus.STREAMING

    def append_delta(self, delta: str) -> None:
        if self.status is not TurnStatus.STREAMING:
            raise Conflict("TURN_NOT_STREAMING", "只有流式中的 turn 可以追加文本。", object_id=self.id)
        if len(self.partial_text) + len(delta) > MAX_MESSAGE_CHARS:
            raise ValidationFailure("TURN_TOO_LONG", "回复长度超出限制。")
        self.partial_text += delta

    def complete(self, text: str, citations: tuple[Citation, ...], actions: tuple[SuggestedAction, ...], answerability: Answerability) -> None:
        if self.status in TURN_TERMINAL:
            raise Conflict("TURN_TERMINAL", "turn 已结束，不能重复提交完整回答。", object_id=self.id)
        if len(citations) > MAX_CITATIONS_PER_TURN:
            raise ValidationFailure("TOO_MANY_CITATIONS", "单轮引用过多。")
        self.final_text = text
        self.citations = citations
        self.suggested_actions = actions
        self.answerability = answerability
        self.status = TurnStatus.SUCCEEDED
        self.partial_text = ""

    def fail(self, code: str) -> None:
        if self.status is TurnStatus.SUCCEEDED:
            raise Conflict("TURN_TERMINAL", "已成功的 turn 不能回退为失败。", object_id=self.id)
        self.error_code = code
        self.status = TurnStatus.FAILED

    def cancel(self) -> None:
        if self.status is TurnStatus.SUCCEEDED:
            raise Conflict("TURN_ALREADY_SUCCEEDED", "已完成的 turn 返回当前终态，不能取消。", object_id=self.id)
        if self.status is TurnStatus.CANCELLED:
            return
        self.status = TurnStatus.CANCELLED


@dataclass(frozen=True, slots=True)
class ConversationBudget:
    """Independent conversation budget (F11-R06); never shared with run budget."""

    max_turns_per_session: int = 60
    max_turns_per_actor_per_day: int = 200
    max_turns_per_project_per_day: int = 2000
    max_output_tokens_per_turn: int = 1200
    max_calls_per_turn: int = 2
    currency: str = "CNY"
    max_cost_micros_per_session: int = 2_000_000

    def check_limits(self, *, turns_in_session: int, turns_by_actor: int, turns_in_project: int) -> None:
        if turns_in_session >= self.max_turns_per_session:
            raise Conflict("SESSION_QUOTA_EXCEEDED", "会话轮数已达上限。")
        if turns_by_actor >= self.max_turns_per_actor_per_day:
            raise Conflict("ACTOR_QUOTA_EXCEEDED", "参与者今日对话额度已用尽。")
        if turns_in_project >= self.max_turns_per_project_per_day:
            raise Conflict("PROJECT_QUOTA_EXCEEDED", "项目今日对话额度已用尽。")


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    """Frozen per-turn context. Facts and version pins outrank any summary."""

    session_id: str
    turn_id: str
    version_id: str | None
    scene_id: str | None
    flags: tuple[str, ...]
    objective_ids: tuple[str, ...]
    fact_anchor_hash: str
    message_window: tuple[dict[str, str], ...]
    retrieved_span_ids: tuple[str, ...]
    summary_version: str
    context_hash: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "version_id": self.version_id,
            "scene_id": self.scene_id,
            "flags": list(self.flags),
            "objective_ids": list(self.objective_ids),
            "fact_anchor_hash": self.fact_anchor_hash,
            "message_window": [dict(message) for message in self.message_window],
            "retrieved_span_ids": list(self.retrieved_span_ids),
            "summary_version": self.summary_version,
            "context_hash": self.context_hash,
        }
