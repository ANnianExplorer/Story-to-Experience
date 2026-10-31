"""Scripted model responses used by orchestration tests.

The scripted content is deliberately *data*: it represents what a real model
would return, so the orchestration, schema validation, engine and validator are
exercised for real. Tests using this fixture are marked as simulated runs.
"""
from __future__ import annotations

import json
from typing import Any

SPAN_A = "30000000-0000-4000-8000-000000000001"
SPAN_B = "30000000-0000-4000-8000-000000000002"
SPAN_C = "30000000-0000-4000-8000-000000000003"

CLAIM_A = "20000000-0000-4000-8000-000000000001"
CLAIM_B = "20000000-0000-4000-8000-000000000002"
CLAIM_C = "20000000-0000-4000-8000-000000000003"


def plan_payload() -> dict[str, Any]:
    return {
        "summary": "先抽事实，再设计四个场景，构建后用审校与程序检查汇合。",
        "clarifications": [],
        "tasks": [
            {
                "task_id": "evidence",
                "role": "evidence",
                "objective": "从冻结片段提取事实与先后关系",
                "depends_on": [],
                "expected_output": "evidence_bundle",
            },
            {
                "task_id": "design",
                "role": "experience_designer",
                "objective": "设计四场景蓝图",
                "depends_on": ["evidence"],
                "expected_output": "blueprint",
            },
            {
                "task_id": "build",
                "role": "experience_builder",
                "objective": "构建 ExperienceSpec 与对话配置",
                "depends_on": ["design"],
                "expected_output": "candidate",
            },
            {
                "task_id": "review",
                "role": "review",
                "objective": "审校表述与来源",
                "depends_on": ["build"],
                "expected_output": "review_findings",
            },
        ],
    }


def evidence_payload() -> dict[str, Any]:
    return {
        "claims": [
            {
                "statement": "合成材料设定工具 X 用于观察。",
                "content_type": "supported",
                "evidence_span_ids": [SPAN_C],
                "qualifier": None,
            },
            {
                "statement": "合成材料设定 A 先于 C。",
                "content_type": "supported",
                "evidence_span_ids": [SPAN_A],
                "qualifier": None,
            },
            {
                "statement": "合成材料设定 B 先于 C。",
                "content_type": "supported",
                "evidence_span_ids": [SPAN_B],
                "qualifier": None,
            },
        ],
        "gaps": ["资料未规定 A 与 B 的先后顺序。"],
        "ordering_facts": [
            {"before": "A", "after": "C", "claim_index": 1},
            {"before": "B", "after": "C", "claim_index": 2},
        ],
    }


def blueprint_payload() -> dict[str, Any]:
    return {
        "title": "合成工坊体验",
        "entry_idea": "从观察工具开始，逐层理解前置步骤。",
        "objectives": [
            {"objective_id": "obj_tool", "description": "辨认工具用途。", "claim_indexes": [0]},
            {"objective_id": "obj_order", "description": "理解 C 的两个前置步骤。", "claim_indexes": [1, 2]},
        ],
        "scenes": [
            {
                "scene_id": "entry",
                "title": "入口",
                "text": "观察工坊里的工具。",
                "content_type": "supported",
                "objective_ids": ["obj_tool"],
                "claim_indexes": [0],
                "mechanic": "hotspot",
                "mechanic_reason": "材料只说明工具用途，适合直接观察。",
                "is_completion": False,
            },
            {
                "scene_id": "choice_scene",
                "title": "选择场景",
                "text": "工具 X 的用途是什么？",
                "content_type": "supported",
                "objective_ids": ["obj_tool"],
                "claim_indexes": [0],
                "mechanic": "choice",
                "mechanic_reason": "需要在两个用途之间区分。",
                "is_completion": False,
            },
            {
                "scene_id": "sequence_scene",
                "title": "排序场景",
                "text": "按要求排列步骤。",
                "content_type": "supported",
                "objective_ids": ["obj_order"],
                "claim_indexes": [1, 2],
                "mechanic": "sequence",
                "mechanic_reason": "材料只给出 A<C、B<C 两条偏序。",
                "is_completion": False,
            },
            {
                "scene_id": "done",
                "title": "完成",
                "text": "体验结束。",
                "content_type": "adaptation",
                "objective_ids": [],
                "claim_indexes": [],
                "mechanic": "hotspot",
                "mechanic_reason": "完成页不需要任务。",
                "is_completion": True,
            },
        ],
        "dialogue": {
            "persona_name": "小序",
            "persona_role": "工坊导览助手",
            "adaptation_note": "小序是改编角色，对白为创作，不是历史原话。",
            "hint_policy": "gentle",
        },
    }


def candidate_payload() -> dict[str, Any]:
    spec = {
        "schema_version": "1.0.0",
        "runtime_version": "1.0.0",
        "brief": {
            "audience": "五年级学生",
            "duration_minutes": 5,
            "learning_goals": ["观察工具用途", "识别前置步骤"],
        },
        "source_snapshot_id": "10000000-0000-4000-8000-000000000001",
        "entry_scene": "entry",
        "flags": [
            {"id": "clue_seen", "initial": False},
            {"id": "choice_done", "initial": False},
            {"id": "sequence_done", "initial": False},
        ],
        "claims": [
            {
                "id": "claim_tool",
                "statement": "合成材料设定工具 X 用于观察。",
                "content_type": "supported",
                "evidence_span_ids": [SPAN_C],
                "source_claim_id": CLAIM_C,
                "source_claim_revision": 1,
            },
            {
                "id": "claim_A_C",
                "statement": "合成材料设定 A 先于 C。",
                "content_type": "supported",
                "evidence_span_ids": [SPAN_A],
                "source_claim_id": CLAIM_A,
                "source_claim_revision": 1,
            },
            {
                "id": "claim_B_C",
                "statement": "合成材料设定 B 先于 C。",
                "content_type": "supported",
                "evidence_span_ids": [SPAN_B],
                "source_claim_id": CLAIM_B,
                "source_claim_revision": 1,
            },
        ],
        "objectives": [
            {"id": "obj_tool", "description": "辨认工具用途。", "claim_ids": ["claim_tool"]},
            {"id": "obj_order", "description": "理解 C 的两个前置步骤。", "claim_ids": ["claim_A_C", "claim_B_C"]},
        ],
        "scenes": [
            {
                "id": "entry",
                "title": "入口",
                "text": "观察工坊里的工具。",
                "content_type": "supported",
                "asset_ids": [],
                "claim_ids": ["claim_tool"],
                "tasks": [
                    {
                        "id": "hotspot_tool",
                        "type": "hotspot",
                        "label": "观察工具 X",
                        "required": True,
                        "completion_flag": "clue_seen",
                        "objective_ids": ["obj_tool"],
                        "claim_ids": ["claim_tool"],
                        "requires": {"flag_equals": {"id": "sequence_done", "value": False}},
                        "on_success": [],
                        "feedback": {
                            "success": "你看到工具 X。",
                            "failure": "还没找到工具。",
                            "claim_ids": ["claim_tool"],
                        },
                        "hints": ["先看工作台左侧。"],
                    }
                ],
                "transitions": [
                    {
                        "id": "go_choice",
                        "label": "进入选择",
                        "requires": {"flag_equals": {"id": "clue_seen", "value": True}},
                        "target_scene": "choice_scene",
                    }
                ],
            },
            {
                "id": "choice_scene",
                "title": "选择场景",
                "text": "工具 X 的用途是什么？",
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
                        "requires": {"flag_equals": {"id": "sequence_done", "value": False}},
                        "on_success": [],
                        "feedback": {"success": "正确。", "failure": "再想想。", "claim_ids": ["claim_tool"]},
                        "hints": ["回到入口再看一次。"],
                        "options": [
                            {
                                "id": "opt_correct",
                                "label": "用于观察",
                                "correct": True,
                                "feedback": "正确。",
                                "on_success": [],
                            },
                            {
                                "id": "opt_distractor",
                                "label": "用于切割",
                                "correct": False,
                                "feedback": "工具 X 不用于切割。",
                                "on_success": [],
                            },
                        ],
                    }
                ],
                "transitions": [
                    {
                        "id": "go_sequence",
                        "label": "进入排序",
                        "requires": {"flag_equals": {"id": "choice_done", "value": True}},
                        "target_scene": "sequence_scene",
                    }
                ],
            },
            {
                "id": "sequence_scene",
                "title": "排序场景",
                "text": "按要求排列步骤。",
                "content_type": "supported",
                "asset_ids": [],
                "claim_ids": ["claim_A_C", "claim_B_C"],
                "tasks": [
                    {
                        "id": "sequence_steps",
                        "type": "sequence",
                        "label": "排列 A、B、C",
                        "required": True,
                        "completion_flag": "sequence_done",
                        "objective_ids": ["obj_order"],
                        "claim_ids": ["claim_A_C", "claim_B_C"],
                        "requires": {"flag_equals": {"id": "choice_done", "value": True}},
                        "on_success": [],
                        "feedback": {
                            "success": "顺序正确。",
                            "failure": "C 必须排在最后。",
                            "claim_ids": ["claim_A_C", "claim_B_C"],
                        },
                        "hints": ["C 有两个前置步骤。"],
                        "items": [
                            {"id": "A", "label": "A"},
                            {"id": "B", "label": "B"},
                            {"id": "C", "label": "C"},
                        ],
                        "precedence": [
                            {"before": "A", "after": "C", "claim_id": "claim_A_C"},
                            {"before": "B", "after": "C", "claim_id": "claim_B_C"},
                        ],
                    }
                ],
                "transitions": [
                    {
                        "id": "finish",
                        "label": "完成体验",
                        "requires": {
                            "all": [
                                {"flag_equals": {"id": "clue_seen", "value": True}},
                                {"flag_equals": {"id": "choice_done", "value": True}},
                                {"flag_equals": {"id": "sequence_done", "value": True}},
                            ]
                        },
                        "target_scene": "done",
                    }
                ],
            },
            {
                "id": "done",
                "title": "完成",
                "text": "体验结束。",
                "content_type": "adaptation",
                "asset_ids": [],
                "claim_ids": [],
                "tasks": [],
                "transitions": [],
            },
        ],
        "completion": {"scene_id": "done", "required_flags": ["clue_seen", "choice_done", "sequence_done"]},
        "asset_manifest": [],
    }
    return {
        "spec": spec,
        "dialogue": {
            "persona_name": "小序",
            "persona_role": "工坊导览助手",
            "adaptation_note": "小序是改编角色，对白为创作，不是历史原话。",
            "hint_policy": "gentle",
        },
    }


def review_payload() -> dict[str, Any]:
    return {
        "summary": "表述没有越出材料，目标覆盖、来源可追溯。",
        "findings": [
            {
                "code": "ADAPTATION_LABEL_PRESENT",
                "severity": "info",
                "message": "完成页标记为 adaptation，符合改编说明。",
                "path": "/scenes/done",
            }
        ],
    }



def builder_content_payload() -> dict[str, Any]:
    """Text-only Builder output, keyed by the ids in the deterministic draft."""
    spec = candidate_payload()["spec"]
    scenes = []
    for scene in spec["scenes"]:
        task = scene["tasks"][0] if scene["tasks"] else None
        scenes.append(
            {
                "id": scene["id"],
                "title": scene["title"],
                "text": scene["text"],
                "task_label": task["label"] if task else None,
                "success": task["feedback"]["success"] if task else None,
                "failure": task["feedback"]["failure"] if task else None,
                "hints": list(task["hints"]) if task and task["hints"] else [],
                # Option ids must match the structural draft (opt_a/opt_b...).
                "options": [
                    {"id": option["id"], "label": option["label"], "feedback": option["feedback"]}
                    for option in (task.get("options") or [])
                ]
                if task
                else [],
            }
        )
    return {"scenes": scenes, "dialogue": candidate_payload()["dialogue"]}


def repair_payload() -> dict[str, Any]:
    return {
        "patches": [
            {"op": "replace", "path": "/brief/duration_minutes", "value": 5},
        ],
        "reason": "统一时长为 5 分钟。",
    }


def scripted(overrides: dict[str, str] | None = None) -> dict[str, str]:
    mapping = {
        "coordinator": json.dumps(plan_payload(), ensure_ascii=False),
        "evidence": json.dumps(evidence_payload(), ensure_ascii=False),
        "experience_designer": json.dumps(blueprint_payload(), ensure_ascii=False),
        "experience_builder": json.dumps(builder_content_payload(), ensure_ascii=False),
        "review": json.dumps(review_payload(), ensure_ascii=False),
        "repair": json.dumps(repair_payload(), ensure_ascii=False),
    }
    if overrides:
        mapping.update(overrides)
    return mapping
