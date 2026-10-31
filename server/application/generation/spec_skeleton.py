"""Compact, generated shape guide for the ExperienceSpec contract.

Language models cannot reliably infer a nested JSON Schema from a prose prompt.
Rather than hand-maintain a second description of the spec, this module derives a
compact **skeleton** (keys, types, cardinalities, enums) straight from the
versioned JSON Schema. It contains no content and no limits that the Schema does
not already state, so it cannot drift from the contract.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

# server/application/generation/<module>.py -> repository root is parents[3].
CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "packages" / "contracts"
EXPERIENCE_SPEC_SCHEMA = CONTRACTS_DIR / "experience-spec.schema.json"

_SKIP_KEYS = {"$schema", "$id", "title", "description", "format", "if", "then", "else", "allOf"}


def _resolve(node: dict[str, Any], root: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    if depth > 8:
        return {}
    if "$ref" in node:
        target: Any = root
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return _resolve(target, root, depth + 1)
    if "oneOf" in node and len(node["oneOf"]) == 1:
        return _resolve(node["oneOf"][0], root, depth + 1)
    return node


def _describe(node: dict[str, Any], root: dict[str, Any], depth: int = 0) -> Any:
    node = _resolve(node, root, depth)
    if not node:
        return "any"
    if "enum" in node:
        return "enum(" + "|".join(str(value) for value in node["enum"]) + ")"
    if "const" in node:
        return f'"{node["const"]}"'
    if "oneOf" in node:
        variants = [_describe(child, root, depth + 1) for child in node["oneOf"]]
        return {"oneOf": variants}
    kind = node.get("type")
    if isinstance(kind, list):
        return "|".join(str(item) for item in kind)
    if kind == "object" or "properties" in node:
        result: dict[str, Any] = {}
        required = set(node.get("required", []))
        for key, child in node.get("properties", {}).items():
            description = _describe(child, root, depth + 1)
            result[key + ("" if key in required else "?")] = description
        if node.get("additionalProperties") is False:
            result["_note"] = "只允许以上字段（additionalProperties=false）"
        return result
    if kind == "array":
        item = _describe(node.get("items", {}), root, depth + 1)
        count = []
        if "minItems" in node:
            count.append(f"min={node['minItems']}")
        if "maxItems" in node:
            count.append(f"max={node['maxItems']}")
        suffix = f" [{', '.join(count)}]" if count else ""
        return f"{item}{suffix}"
    if kind == "integer":
        bounds = []
        if "minimum" in node:
            bounds.append(f"min={node['minimum']}")
        if "maximum" in node:
            bounds.append(f"max={node['maximum']}")
        return f"integer{'(' + ', '.join(bounds) + ')' if bounds else ''}"
    if kind == "string":
        pattern = node.get("pattern")
        if pattern == "^[A-Za-z][A-Za-z0-9_-]{0,63}$":
            return "internal-id (ASCII 字母开头, ≤64)"
        if "maxLength" in node:
            return f"string(≤{node['maxLength']})"
        return "string"
    if kind == "boolean":
        return "boolean"
    return str(kind or "any")


@lru_cache(maxsize=1)
def experience_spec_skeleton() -> str:
    schema = json.loads(EXPERIENCE_SPEC_SCHEMA.read_text(encoding="utf-8"))
    shape = _describe(schema, schema)
    return json.dumps(shape, ensure_ascii=False, indent=1)


def builder_shape_guide() -> str:
    return (
        "ExperienceSpec 结构（由 1.0.0 Schema 生成；? 表示可选，数组方括号为数量限制）：\n"
        + experience_spec_skeleton()
    )
