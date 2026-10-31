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

BUILDER_CONTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "minLength": 1, "maxLength": 64},
                    "title": {"type": "string", "minLength": 1, "maxLength": 80},
                    "text": {"type": "string", "minLength": 1, "maxLength": 600},
                    "task_label": {"type": ["string", "null"], "maxLength": 60},
                    "success": {"type": ["string", "null"], "maxLength": 160},
                    "failure": {"type": ["string", "null"], "maxLength": 160},
                    "hints": {"type": "array", "items": {"type": "string", "maxLength": 80}, "maxItems": 2},
                    "options": {
                        "type": "array",
                        "maxItems": 6,
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "maxLength": 32},
                                "label": {"type": "string", "minLength": 1, "maxLength": 60},
                                "feedback": {"type": "string", "minLength": 1, "maxLength": 160},
                            },
                            "required": ["id", "label", "feedback"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["id", "title", "text", "task_label", "success", "failure", "hints", "options"],
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
    "required": ["scenes", "dialogue"],
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

你是 ExperienceBuilder，负责为已冻结的结构草稿撰写面向参与者的文字。
结构（ID、标记、条件、跳转、事实绑定）已经由系统按蓝图生成，你**不要**改动结构，
只输出每个场景的标题、正文、任务标签、成功/失败反馈、提示，以及对话角色设定。

硬性要求：
- 文字只能表述给定事实里的内容；不得补造工序、年代、人物原话或因果关系。
- 资料没有写到的内容写进缺口思路，不要写成确定事实。
- 正文纯文本，不含 HTML；每个场景正文 ≤ 120 字；反馈 ≤ 60 字。
- 选择题每个选项的 label 与 feedback 都要写，且只有一个是正确答案（结构里已定）。
- adaptation_note 必须说明该角色是改编创作，不是历史原话。"""
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



# A minimal, schema-valid shape for the trickiest parts of the spec. Models
# systematically mis-write nested conditions, so one concrete example is worth
# more than another paragraph of rules. `tests/test_spec_example.py` asserts
# this example still validates against the versioned Schema, so it cannot drift.
SPEC_EXAMPLE = {
    "schema_version": "1.0.0",
    "runtime_version": "1.0.0",
    "brief": {"audience": "五年级学生", "duration_minutes": 5, "learning_goals": ["观察工具"]},
    "source_snapshot_id": "10000000-0000-4000-8000-000000000001",
    "entry_scene": "entry",
    "flags": [
        {"id": "clue_seen", "initial": False},
        {"id": "choice_done", "initial": False},
        {"id": "order_done", "initial": False},
    ],
    "claims": [
        {
            "id": "claim_tool",
            "statement": "资料中的事实陈述。",
            "content_type": "supported",
            "evidence_span_ids": ["30000000-0000-4000-8000-000000000001"],
            "source_claim_id": "20000000-0000-4000-8000-000000000001",
            "source_claim_revision": 1,
        },
        {
            "id": "claim_order",
            "statement": "资料写明的先后关系。",
            "content_type": "supported",
            "evidence_span_ids": ["30000000-0000-4000-8000-000000000002"],
            "source_claim_id": "20000000-0000-4000-8000-000000000002",
            "source_claim_revision": 1,
        },
    ],
    "objectives": [
        {"id": "obj_tool", "description": "辨认工具。", "claim_ids": ["claim_tool"]},
        {"id": "obj_order", "description": "理解顺序。", "claim_ids": ["claim_order"]},
    ],
    "scenes": [
        {
            "id": "entry",
            "title": "入口",
            "text": "观察工具。",
            "content_type": "supported",
            "asset_ids": [],
            "claim_ids": ["claim_tool"],
            "tasks": [
                {
                    "id": "hotspot_tool",
                    "type": "hotspot",
                    "label": "观察",
                    "required": True,
                    "completion_flag": "clue_seen",
                    "objective_ids": ["obj_tool"],
                    "claim_ids": ["claim_tool"],
                    "requires": {"flag_equals": {"id": "order_done", "value": False}},
                    "on_success": [],
                    "feedback": {"success": "看到了。", "failure": "再找找。", "claim_ids": ["claim_tool"]},
                    "hints": ["看左侧。"],
                }
            ],
            "transitions": [
                {
                    "id": "go_choice",
                    "label": "下一步",
                    "requires": {"flag_equals": {"id": "clue_seen", "value": True}},
                    "target_scene": "choice",
                }
            ],
        },
        {
            "id": "choice",
            "title": "选择",
            "text": "它用来做什么？",
            "content_type": "supported",
            "asset_ids": [],
            "claim_ids": ["claim_tool"],
            "tasks": [
                {
                    "id": "choice_tool",
                    "type": "choice",
                    "label": "选择用途",
                    "required": True,
                    "completion_flag": "choice_done",
                    "objective_ids": ["obj_tool"],
                    "claim_ids": ["claim_tool"],
                    "requires": {"flag_equals": {"id": "order_done", "value": False}},
                    "on_success": [],
                    "feedback": {"success": "正确。", "failure": "再想想。", "claim_ids": ["claim_tool"]},
                    "hints": ["回看一下。"],
                    "options": [
                        {"id": "opt_yes", "label": "用于观察", "correct": True, "feedback": "正确。", "on_success": []},
                        {"id": "opt_no", "label": "用于切割", "correct": False, "feedback": "不对。", "on_success": []},
                    ],
                }
            ],
            "transitions": [
                {
                    "id": "go_order",
                    "label": "下一步",
                    "requires": {"flag_equals": {"id": "choice_done", "value": True}},
                    "target_scene": "order",
                }
            ],
        },
        {
            "id": "order",
            "title": "排序",
            "text": "按资料顺序排列。",
            "content_type": "supported",
            "asset_ids": [],
            "claim_ids": ["claim_order"],
            "tasks": [
                {
                    "id": "order_steps",
                    "type": "sequence",
                    "label": "排列",
                    "required": True,
                    "completion_flag": "order_done",
                    "objective_ids": ["obj_order"],
                    "claim_ids": ["claim_order"],
                    "requires": {"flag_equals": {"id": "clue_seen", "value": True}},
                    "on_success": [],
                    "feedback": {"success": "正确。", "failure": "顺序不对。", "claim_ids": ["claim_order"]},
                    "hints": ["先想第一步。"],
                    "items": [{"id": "A", "label": "甲"}, {"id": "B", "label": "乙"}],
                    "precedence": [{"before": "A", "after": "B", "claim_id": "claim_order"}],
                }
            ],
            "transitions": [
                {
                    "id": "finish",
                    "label": "完成",
                    "requires": {
                        "all": [
                            {"flag_equals": {"id": "clue_seen", "value": True}},
                            {"flag_equals": {"id": "choice_done", "value": True}},
                            {"flag_equals": {"id": "order_done", "value": True}},
                        ]
                    },
                    "target_scene": "done",
                }
            ],
        },
        {
            "id": "done",
            "title": "完成",
            "text": "结束。",
            "content_type": "adaptation",
            "asset_ids": [],
            "claim_ids": [],
            "tasks": [],
            "transitions": [],
        },
    ],
    "completion": {"scene_id": "done", "required_flags": ["clue_seen", "choice_done", "order_done"]},
    "asset_manifest": [],
}

CONDITION_RULES = """条件与效果的写法（必须严格遵守）：
- 条件只有四种：{"flag_equals": {"id": "标记", "value": true|false}}、{"all": [条件, ...]}、{"any": [条件, ...]}、{"not": 条件}。
- 不得把标记名直接写进 all/any 数组；数组元素必须是完整的条件对象。
- 无前置条件时写 {"flag_equals": {"id": "某个_initial=false_的标记", "value": false}}，不要用空 all。
- 效果只能是 {"set_flag": "标记", "value": true}；任务的 completion_flag 不要写进 on_success。"""


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
