"""Deterministic ExperienceSpec assembly for the Builder agent (F03, ADR-0004).

Division of labour: the **Builder model writes language** (scene titles, body
text, task labels, feedback, hints, option labels, dialogue persona), while the
**structure** (ids, flags, completion mapping, conditions, effects, references)
is assembled here from the frozen blueprint and evidence. That keeps every
participant-visible string model-authored while guaranteeing that wiring errors
cannot produce an unplayable candidate — and the deterministic validator still
re-checks the result.

Nothing here invents cultural content: text and ordering come from the model's
blueprint and the evidence agent's `ordering_facts`. Missing ordering evidence is
reported as a gap instead of being filled with a guessed sequence.
"""
from __future__ import annotations

import uuid
from typing import Any

from server.domain.shared.errors import ValidationFailure

SOURCE_CLAIM_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")
MAX_OPTIONS = 6


def _claim_id(index: int) -> str:
    return f"claim_{index}"


def _objective_id(index: int) -> str:
    return f"objective_{index}"


def _scene_flag(scene_index: int) -> str:
    return f"done_s{scene_index}"


def source_claim_id_for(statement: str, known: dict[str, str]) -> str:
    """Stable source-claim UUID: the imported claim when known, else a uuid5.

    A uuid5 is deterministic for the same statement, so re-running a build never
    silently relabels a claim.
    """
    if statement in known:
        return known[statement]
    return str(uuid.uuid5(SOURCE_CLAIM_NAMESPACE, statement))


def build_draft_spec(
    *,
    blueprint: dict[str, Any],
    evidence: dict[str, Any],
    brief: dict[str, Any],
    snapshot_id: str,
    known_claim_ids: dict[str, str],
) -> dict[str, Any]:
    """Assemble the spec skeleton the Builder model will fill with text."""
    claims_payload = evidence["claims"]
    claim_ids = [_claim_id(index) for index in range(len(claims_payload))]
    claims = [
        {
            "id": claim_ids[index],
            "statement": claim["statement"],
            "content_type": claim["content_type"],
            "evidence_span_ids": list(claim["evidence_span_ids"]),
            "source_claim_id": source_claim_id_for(claim["statement"], known_claim_ids),
            "source_claim_revision": 1,
        }
        for index, claim in enumerate(claims_payload)
    ]

    objectives = []
    for index, objective in enumerate(blueprint["objectives"]):
        mapped = [claim_ids[i] for i in objective["claim_indexes"] if 0 <= i < len(claim_ids)]
        if not mapped:
            raise ValidationFailure(
                "BLUEPRINT_REFERENCES_MISSING_CLAIM",
                "蓝图目标引用了不存在的事实下标。",
                {"objective_id": objective["objective_id"]},
            )
        objectives.append({"id": _objective_id(index), "description": objective["description"], "claim_ids": mapped})

    interactive = [scene for scene in blueprint["scenes"] if not scene["is_completion"]]
    completion_scene = next((scene for scene in blueprint["scenes"] if scene["is_completion"]), None)
    if completion_scene is None:
        raise ValidationFailure("BLUEPRINT_INVALID", "蓝图缺少完成场景。")
    if not 4 <= len(blueprint["scenes"]) <= 6:
        raise ValidationFailure("BLUEPRINT_INVALID", "体验场景需 4—6 个。", {"scenes": len(blueprint["scenes"])})
    if not 1 <= len(interactive) <= 5:
        raise ValidationFailure("BLUEPRINT_INVALID", "交互场景数量必须在 1—5 之间。")

    objective_index_by_id = {item["objective_id"]: index for index, item in enumerate(blueprint["objectives"])}
    ordering_facts = evidence.get("ordering_facts") or []

    flags = [{"id": _scene_flag(index), "initial": False} for index in range(len(interactive))]
    # An always-false marker gives tasks and transitions a legal "no condition"
    # expression without an empty `all` (experience-spec §条件与效果).
    flags.append({"id": "never", "initial": False})

    scenes: list[dict[str, Any]] = []
    tasks_total = 0
    required_flags: list[str] = []

    for scene_index, scene in enumerate(interactive):
        mapped_claims = [claim_ids[i] for i in scene["claim_indexes"] if 0 <= i < len(claim_ids)]
        content_type = scene["content_type"]
        if content_type in {"supported", "legend"} and not mapped_claims:
            raise ValidationFailure(
                "SCENE_WITHOUT_SUPPORTED_CLAIM",
                "支持性场景必须绑定事实。",
                {"scene_id": scene["scene_id"]},
            )
        mapped_objectives = [
            _objective_id(objective_index_by_id[objective])
            for objective in scene["objective_ids"]
            if objective in objective_index_by_id
        ]
        supported_claims = [
            claim_ids[index]
            for index in scene["claim_indexes"]
            if 0 <= index < len(claims_payload) and claims_payload[index]["content_type"] in {"supported", "legend"}
        ]
        if not supported_claims:
            raise ValidationFailure(
                "REQUIRED_TASK_WITHOUT_SUPPORT",
                "每个交互场景都必须有一条 supported/legend 依据。",
                {"scene_id": scene["scene_id"]},
            )
        if not mapped_objectives:
            raise ValidationFailure(
                "SCENE_WITHOUT_OBJECTIVE",
                "交互场景必须绑定教学目标。",
                {"scene_id": scene["scene_id"]},
            )

        completion_flag = _scene_flag(scene_index)
        task = _build_task(
            scene=scene,
            scene_index=scene_index,
            completion_flag=completion_flag,
            claim_ids=supported_claims,
            objective_ids=mapped_objectives,
            ordering_facts=ordering_facts,
            claim_ids_by_name=claim_ids,
            claims_payload=claims_payload,
        )
        tasks_total += 1
        required_flags.append(completion_flag)

        next_scene = (
            interactive[scene_index + 1]["scene_id"]
            if scene_index + 1 < len(interactive)
            else completion_scene["scene_id"]
        )
        if scene_index + 1 < len(interactive):
            requires = {"flag_equals": {"id": completion_flag, "value": True}}
            label = "继续"
        else:
            requires = {"all": [{"flag_equals": {"id": flag_id, "value": True}} for flag_id in required_flags]}
            label = "完成体验"
        transitions = [{"id": f"go_{next_scene}", "label": label, "requires": requires, "target_scene": next_scene}]

        scenes.append(
            {
                "id": scene["scene_id"],
                "title": scene["title"],
                "text": scene["text"],
                "content_type": content_type,
                "asset_ids": [],
                "claim_ids": mapped_claims,
                "tasks": [task],
                "transitions": transitions,
            }
        )

    # The completion page is authored framing, never an evidence-backed claim,
    # so it is always typed "adaptation" — a supported/legend page without
    # bound claims would violate the contract and misstate provenance.
    scenes.append(
        {
            "id": completion_scene["scene_id"],
            "title": completion_scene["title"],
            "text": completion_scene["text"],
            "content_type": "adaptation",
            "asset_ids": [],
            "claim_ids": [],
            "tasks": [],
            "transitions": [],
        }
    )

    return {
        "schema_version": "1.0.0",
        "runtime_version": "1.0.0",
        "brief": {
            "audience": brief["audience"],
            "duration_minutes": brief["duration_minutes"],
            "learning_goals": list(brief["learning_goals"])[:6],
        },
        "source_snapshot_id": snapshot_id,
        "entry_scene": interactive[0]["scene_id"],
        "flags": flags,
        "claims": claims,
        "objectives": objectives,
        "scenes": scenes,
        "completion": {"scene_id": completion_scene["scene_id"], "required_flags": required_flags},
        "asset_manifest": [],
    }


def _build_task(
    *,
    scene: dict[str, Any],
    scene_index: int,
    completion_flag: str,
    claim_ids: list[str],
    objective_ids: list[str],
    ordering_facts: list[dict[str, Any]],
    claims_payload: list[dict[str, Any]],
    claim_ids_by_name: list[str],
) -> dict[str, Any]:
    mechanic = scene["mechanic"]
    task_id = f"task_s{scene_index}"
    base = {
        "id": task_id,
        "type": mechanic,
        "label": scene["title"],
        "required": True,
        "completion_flag": completion_flag,
        "objective_ids": objective_ids,
        "claim_ids": claim_ids,
        "requires": {"flag_equals": {"id": "never", "value": False}},
        "on_success": [],
        "feedback": {"success": "完成。", "failure": "再试一次。", "claim_ids": claim_ids},
        "hints": [],
    }
    if mechanic == "hotspot":
        return base
    if mechanic == "choice":
        base["options"] = [
            {"id": "opt_correct", "label": "正确选项", "correct": True, "feedback": "正确。", "on_success": []},
            {"id": "opt_distractor", "label": "干扰选项", "correct": False, "feedback": "再想想。", "on_success": []},
        ]
        return base
    if mechanic != "sequence":
        raise ValidationFailure("MECHANIC_UNSUPPORTED", f"不支持的机制：{mechanic}。")

    # Sequence: items and edges come only from the material's ordering facts.
    if not ordering_facts:
        raise ValidationFailure(
            "INSUFFICIENT_ORDERING_EVIDENCE",
            "蓝图要求排序机制，但资料没有给出任何先后关系；请补充资料或改用其他机制。",
            {"scene_id": scene["scene_id"]},
        )
    names: list[str] = []
    for fact in ordering_facts:
        for name in (fact["before"], fact["after"]):
            if name not in names:
                names.append(name)
    if len(names) < 2 or len(names) > 6:
        raise ValidationFailure(
            "SEQUENCE_ITEM_COUNT",
            "排序元素数量必须在 2—6 之间。",
            {"items": names},
        )
    precedence = []
    for fact in ordering_facts:
        index = fact["claim_index"]
        if not 0 <= index < len(claims_payload):
            raise ValidationFailure("ORDERING_CLAIM_UNKNOWN", "先后关系引用了不存在的事实下标。")
        precedence.append(
            {"before": fact["before"], "after": fact["after"], "claim_id": claim_ids_by_name[index]}
        )
    base["items"] = [{"id": f"i{position}", "label": name} for position, name in enumerate(names)]
    label_by_name = {name: f"i{position}" for position, name in enumerate(names)}
    base["precedence"] = [
        {"before": label_by_name[edge["before"]], "after": label_by_name[edge["after"]], "claim_id": edge["claim_id"]}
        for edge in precedence
    ]
    return base
