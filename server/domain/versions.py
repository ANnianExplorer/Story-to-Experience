"""Version immutability, project pointers and revision head checks (F07)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .shared.errors import Conflict, ValidationFailure

TechnicalStatus = Literal["not_run", "passed", "failed", "inconclusive"]
ContentStatus = Literal["pending", "approved", "needs_changes"]
TECHNICAL_VALUES = frozenset({"not_run", "passed", "failed", "inconclusive"})
CONTENT_VALUES = frozenset({"pending", "approved", "needs_changes"})


@dataclass(frozen=True, slots=True)
class ExperienceVersion:
    id: str
    project_id: str
    parent_id: str | None
    run_id: str | None
    step_key: str | None
    spec: dict[str, object]
    spec_hash: str
    semantic_hash: str
    manifest_hash: str
    runtime_version: str
    dialogue_profile: dict[str, object] | None = None
    dialogue_profile_hash: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.spec_hash or not self.semantic_hash or not self.manifest_hash:
            raise ValidationFailure("INVALID_VERSION", "版本必须携带 spec/semantic/manifest 哈希。")
        if (self.dialogue_profile is None) != (self.dialogue_profile_hash is None):
            raise ValidationFailure("INVALID_VERSION", "对话配置与哈希必须同时存在。")


def claim_revision_slot(project_revision_head_id: str | None, base_version_id: str) -> None:
    if project_revision_head_id != base_version_id:
        raise Conflict(
            "VERSION_CONFLICT",
            "基准版本已变化，请重新加载。",
            object_id=base_version_id,
        )


def assert_can_go_stable(technical: str, content: str, *, hash_matches: bool, license_ok: bool) -> None:
    if technical != "passed":
        raise Conflict("TECHNICAL_GATE_FAILED", "技术检查尚未通过，不能设为稳定版。")
    if content != "approved":
        raise Conflict("CONTENT_GATE_FAILED", "内容尚未审核通过，不能设为稳定版。")
    if not hash_matches:
        raise Conflict("REPORT_HASH_STALE", "检查报告与当前内容哈希不一致，请重新检查。")
    if not license_ok:
        raise Conflict("LICENSE_REVOKED", "授权或许可已失效，不能正式交付。")


ALLOWED_PATCH_PREFIXES: tuple[str, ...] = (
    "/brief/audience",
    "/brief/duration_minutes",
    "/brief/learning_goals",
    "/scenes/",
)

FORBIDDEN_PATCH_PREFIXES: tuple[str, ...] = (
    "/claims",
    "/source_snapshot_id",
    "/completion/scene_id",
    "/completion/required_flags",
    "/runtime_version",
    "/schema_version",
)


def check_patch_path(path: str) -> None:
    """Whitelist JSON Patch paths by parsed segments, never by raw string prefix."""
    if not path.startswith("/"):
        raise ValidationFailure("INVALID_PATCH_PATH", "补丁路径必须是 JSON Pointer。", {"path": path[:200]})
    if "~" in path.replace("~0", "").replace("~1", ""):
        raise ValidationFailure("INVALID_PATCH_PATH", "补丁路径含非法转义。", {"path": path[:200]})
    decoded = path.replace("~1", "/").replace("~0", "~")
    for prefix in FORBIDDEN_PATCH_PREFIXES:
        if decoded == prefix or decoded.startswith(prefix + "/"):
            raise ValidationFailure("PATCH_PATH_FORBIDDEN", "该路径不允许由模型补丁修改。", {"path": decoded[:200]})
    for prefix in ALLOWED_PATCH_PREFIXES:
        if prefix.endswith("/"):
            if decoded.startswith(prefix):
                return
        elif decoded == prefix:
            return
    raise ValidationFailure("PATCH_PATH_FORBIDDEN", "补丁路径不在允许范围内。", {"path": decoded[:200]})
