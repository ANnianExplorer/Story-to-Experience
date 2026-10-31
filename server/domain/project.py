"""Project and brief domain objects (F01).

The owner is always supplied by the authenticated session; a client-provided
owner_id is never trusted. Brief edits append revisions and never rewrite
history.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .errors import NotFound, ValidationFailure

MAX_NAME_LENGTH = 120
MAX_AUDIENCE_LENGTH = 120
MAX_GOAL_LENGTH = 200
MAX_GOALS = 6
MIN_DURATION_MINUTES = 1
MAX_DURATION_MINUTES = 30


def _require_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValidationFailure("INVALID_NAME", "项目名称不能为空。", {"field": "name"})
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ValidationFailure("INVALID_NAME", "项目名称过长。", {"field": "name", "max": MAX_NAME_LENGTH})
    return cleaned


@dataclass(frozen=True, slots=True)
class Brief:
    audience: str
    duration_minutes: int
    learning_goals: tuple[str, ...]

    def __post_init__(self) -> None:
        audience = self.audience.strip()
        if not audience:
            raise ValidationFailure("INVALID_BRIEF", "受众不能为空。", {"field": "audience"})
        if len(audience) > MAX_AUDIENCE_LENGTH:
            raise ValidationFailure("INVALID_BRIEF", "受众描述过长。", {"field": "audience", "max": MAX_AUDIENCE_LENGTH})
        duration = self.duration_minutes
        if not isinstance(duration, int) or isinstance(duration, bool):
            raise ValidationFailure("INVALID_BRIEF", "时长必须是整数分钟。", {"field": "duration_minutes"})
        if not MIN_DURATION_MINUTES <= duration <= MAX_DURATION_MINUTES:
            raise ValidationFailure(
                "INVALID_BRIEF",
                f"时长必须在 {MIN_DURATION_MINUTES}—{MAX_DURATION_MINUTES} 分钟之间。",
                {"field": "duration_minutes"},
            )
        goals = tuple(goal.strip() for goal in self.learning_goals)
        if not 1 <= len(goals) <= MAX_GOALS:
            raise ValidationFailure("INVALID_BRIEF", f"教学目标需 1—{MAX_GOALS} 条。", {"field": "learning_goals"})
        for goal in goals:
            if not goal:
                raise ValidationFailure("INVALID_BRIEF", "教学目标不能为空。", {"field": "learning_goals"})
            if len(goal) > MAX_GOAL_LENGTH:
                raise ValidationFailure("INVALID_BRIEF", "教学目标过长。", {"field": "learning_goals", "max": MAX_GOAL_LENGTH})
        object.__setattr__(self, "audience", audience)
        object.__setattr__(self, "learning_goals", goals)

    def to_payload(self) -> dict[str, object]:
        return {
            "audience": self.audience,
            "duration_minutes": self.duration_minutes,
            "learning_goals": list(self.learning_goals),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "Brief":
        goals = payload.get("learning_goals") or ()
        if isinstance(goals, str) or not isinstance(goals, (list, tuple)):
            raise ValidationFailure("INVALID_BRIEF", "教学目标必须是数组。", {"field": "learning_goals"})
        duration = payload.get("duration_minutes")
        return cls(
            audience=str(payload.get("audience") or ""),
            duration_minutes=duration if isinstance(duration, int) and not isinstance(duration, bool) else -1,
            learning_goals=tuple(str(goal) for goal in goals),
        )


@dataclass(slots=True)
class Project:
    id: str
    owner_id: str
    name: str
    brief: Brief
    brief_revision: int = 1
    revision_head_id: str | None = None
    latest_candidate_version_id: str | None = None
    selected_version_id: str | None = None
    stable_version_id: str | None = None
    active_revision_run_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.name = _require_name(self.name)

    def rename(self, name: str) -> None:
        self.name = _require_name(name)

    def assert_owned_by(self, actor_id: str) -> None:
        if self.owner_id != actor_id:
            # Uniform 404: never reveal that another user's project exists.
            raise NotFound(object_id=self.id)


@dataclass(frozen=True, slots=True)
class BriefRevision:
    project_id: str
    revision: int
    brief: Brief
    note: str
    created_at: datetime | None = None
