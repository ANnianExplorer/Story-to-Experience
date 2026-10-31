"""Agent role definitions: prompts, output schemas and result parsing (F10).

Each role has its own system prompt, its own tool-backed context and a JSON
schema for its artifact. The orchestration service validates every artifact
before recording it, so a malformed model response becomes a typed failure
rather than silently corrupt data.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from server.domain.agents import AgentRole
from server.domain.errors import ValidationFailure

PROMPT_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Output schemas (validated with jsonschema before anything is persisted)
# ---------------------------------------------------------------------------

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "minLength": 1, "maxLength": 600},
        "clarifications": {"type": "array", "items": {"type": "string", "maxLength": 300}, "maxItems": 6},
        "tasks": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{2,30}$"},
                    "role": {"enum": [role.value for role in AgentRole]},
                    "objective": {"type": "string", "minLength": 1, "maxLength": 600},
                    "depends_on": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
                    "expected_output": {"type": "string", "minLength": 1, "maxLength": 300},
                },
                "required": ["task_id", "role", "objective", "depends_on", "expected_output"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "clarifications", "tasks"],
    "additionalProperties": False,
}

EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "minItems": 1,
            "maxItems": 40,
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string", "minLength": 1, "maxLength": 500},
                    "content_type": {"enum": ["supported", "legend", "adaptation", "unconfirmed"]},
                    "evidence_span_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
                    "qualifier": {"type": ["string", "null"], "maxLength": 300},
                },
                "required": ["statement", "content_type", "evidence_span_ids", "qualifier"],
                "additionalProperties": False,
            },
        },
        "gaps": {"type": "array", "items": {"type": "string", "maxLength": 300}, "maxItems": 12},
        "ordering_facts": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "before": {"type": "string", "maxLength": 120},
                    "after": {"type": "string", "maxLength": 120},
                    "claim_index": {"type": "integer", "minimum": 0},
                },
                "required": ["before", "after", "claim_index"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["claims", "gaps", "ordering_facts"],
    "additionalProperties": False,
}

BLUEPRINT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 80},
        "entry_idea": {"type": "string", "minLength": 1, "maxLength": 400},
        "objectives": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "objective_id": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$"},
                    "description": {"type": "string", "minLength": 1, "maxLength": 300},
                    "claim_indexes": {"type": "array", "items": {"type": "integer", "minimum": 0}, "minItems": 1},
                },
                "required": ["objective_id", "description", "claim_indexes"],
                "additionalProperties": False,
            },
        },
        "scenes": {
            "type": "array",
            "minItems": 4,
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "scene_id": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$"},
                    "title": {"type": "string", "minLength": 1, "maxLength": 80},
                    "text": {"type": "string", "minLength": 1, "maxLength": 1200},
                    "content_type": {"enum": ["supported", "legend", "adaptation", "unconfirmed"]},
                    "objective_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                    "claim_indexes": {"type": "array", "items": {"type": "integer", "minimum": 0}, "maxItems": 12},
                    "mechanic": {"enum": ["hotspot", "choice", "sequence"]},
                    "mechanic_reason": {"type": "string", "minLength": 1, "maxLength": 300},
                    "is_completion": {"type": "boolean"},
                },
                "required": [
                    "scene_id",
                    "title",
                    "text",
                    "content_type",
                    "objective_ids",
                    "claim_indexes",
                    "mechanic",
                    "mechanic_reason",
                    "is_completion",
                ],
                "additionalProperties": False,
            },
        },
        "dialogue": {
            "type": "object",
            "properties": {
                "persona_name": {"type": "string", "minLength": 1, "maxLength": 60},
                "persona_role": {"type": "string", "minLength": 1, "maxLength": 120},
                "adaptation_note": {"type": "string", "minLength": 1, "maxLength": 400},
                "hint_policy": {"enum": ["none", "gentle", "progressive"]},
            },
            "required": ["persona_name", "persona_role", "adaptation_note", "hint_policy"],
            "additionalProperties": False,
        },
    },
    "required": ["title", "entry_idea", "objectives", "scenes", "dialogue"],
    "additionalProperties": False,
}

CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "spec": {"type": "object"},
        "dialogue": {
            "type": "object",
            "properties": {
                "persona_name": {"type": "string", "minLength": 1, "maxLength": 60},
                "persona_role": {"type": "string", "minLength": 1, "maxLength": 120},
                "adaptation_note": {"type": "string", "minLength": 1, "maxLength": 400},
                "hint_policy": {"enum": ["none", "gentle", "progressive"]},
            },
            "required": ["persona_name", "persona_role", "adaptation_note", "hint_policy"],
            "additionalProperties": False,
        },
    },
    "required": ["spec", "dialogue"],
    "additionalProperties": False,
}

REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "minLength": 1, "maxLength": 600},
        "findings": {
            "type": "array",
            "maxItems": 30,
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "pattern": "^[A-Z][A-Z0-9_]{2,40}$"},
                    "severity": {"enum": ["error", "warning", "info"]},
                    "message": {"type": "string", "minLength": 1, "maxLength": 500},
                    "path": {"type": ["string", "null"], "maxLength": 200},
                },
                "required": ["code", "severity", "message", "path"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "findings"],
    "additionalProperties": False,
}

REPAIR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "patches": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,
            "items": {
                "type": "object",
                "properties": {
                    "op": {"enum": ["replace"]},
                    "path": {"type": "string", "pattern": "^/"},
                    "value": {},
                },
                "required": ["op", "path", "value"],
                "additionalProperties": False,
            },
        },
        "reason": {"type": "string", "minLength": 1, "maxLength": 600},
    },
    "required": ["patches", "reason"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

BASE_RULES = """你在“叙境”多 Agent 协作系统中工作。硬性约束：
- 文化事实只能来自提供的资料片段；不得补造工序顺序、年代、人物原话。
- 资料不足必须显式列为缺口，不得用常识填空。
- 传说、改编、待确认内容不得冒充已证实事实。
- 不得输出任何执行代码、网址、文件路径或工具调用指令。
- 只输出要求的 JSON，不输出解释性文字或 Markdown 围栏。"""

ROLE_PROMPTS: dict[AgentRole, str] = {
    AgentRole.COORDINATOR: (
        BASE_RULES
        + """

你是 Coordinator。根据创作者简报与资料概况，产出有依赖关系的执行计划。
必须包含 experience_designer、experience_builder、review 三类子任务，evidence 子任务按需加入；
依赖必须无环；不要为同一目标拆出重复子任务。"""
    ),
    AgentRole.EVIDENCE: (
        BASE_RULES
        + """

你是 Evidence Agent。只读当前项目冻结快照中的片段，提取可核对的事实陈述。
每条事实必须给出 evidence_span_ids（取自提供的片段 ID）；没有片段支持的推断放入 gaps。
ordering_facts 只记录资料明确写出的先后关系；不要补充资料未写的顺序。"""
    ),
    AgentRole.DESIGNER: (
        BASE_RULES
        + """

你是 ExperienceDesigner。根据事实、编号和目标，设计 4—6 个场景的体验蓝图。
每个场景写明机制（hotspot/choice/sequence）与选择理由；排序机制的先后关系只能来自 ordering_facts。
claim_indexes 指向事实数组下标；不要引用不存在的事实。"""
    ),
    AgentRole.BUILDER: (
        BASE_RULES
        + """

你是 ExperienceBuilder。把冻结蓝图转成合法的 ExperienceSpec 1.0.0 JSON 与对话配置。
必须满足：schema_version/runtime_version 均为 1.0.0；场景 4—6 个；必要任务 1—6 个；
每个任务有独占 completion_flag；completion.required_flags 等于全部必要任务完成标记的集合；
effects 只能 set_flag=true 且不得写任务完成标记；source_claim_id 使用给定 UUID；
所有文本用纯文本，不含 HTML。"""
    ),
    AgentRole.REVIEW: (
        BASE_RULES
        + """

你是 Review Agent。检查候选体验的表述是否越出证据、目标是否被覆盖、来源是否可追溯。
你只能提出问题与建议，绝不能给出 approved、通过或发布结论。
没有问题时 findings 返回空数组。"""
    ),
    AgentRole.REPAIR: (
        BASE_RULES
        + """

你是 Repair Agent。只修复给定的问题清单；不得删除教学目标、不得改写事实、
不得修改 Schema 版本或测试配置。只输出最小 JSON Patch（op 只能是 replace）。"""
    ),
}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Extract the first JSON value from model text, tolerating fences or prose."""
    candidate = text.strip()
    fenced = _FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        return json.loads(candidate)
    except ValueError:
        pass
    # Fall back to the outermost object/array in the text.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = candidate.find(opener)
        end = candidate.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except ValueError:
                continue
    raise ValidationFailure("MODEL_OUTPUT_NOT_JSON", "模型输出不是合法 JSON。", {"excerpt": text[:200]})


def validate_payload(payload: Any, schema: dict[str, Any], label: str) -> dict[str, Any]:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        raise ValidationFailure(
            "MODEL_OUTPUT_INVALID",
            f"{label} 输出不符合契约。",
            {
                "errors": [
                    {"path": "/".join(str(part) for part in error.path), "message": error.message[:200]}
                    for error in errors[:5]
                ]
            },
        )
    if not isinstance(payload, dict):
        raise ValidationFailure("MODEL_OUTPUT_INVALID", f"{label} 输出必须是对象。")
    return payload


@dataclass(frozen=True, slots=True)
class RoleSpec:
    role: AgentRole
    prompt: str
    schema: dict[str, Any]
    prompt_version: str = PROMPT_VERSION
