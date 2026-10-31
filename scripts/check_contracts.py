"""Validate repository contract fixtures, NOT the production player/state engine."""
from __future__ import annotations

import copy
import itertools
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("Missing jsonschema. Install requirements-docs.txt; contract checks were NOT run.", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "packages/contracts"


def load(relative: str) -> dict | list:
    return json.loads((CONTRACTS / relative).read_text(encoding="utf-8"))


def semantic_errors(spec: dict, evidence_ids: set[str]) -> list[str]:
    """Static fixture checks only; no state transition or reachability implementation."""
    errors: list[str] = []

    def unique(values: list[str], label: str) -> set[str]:
        if len(values) != len(set(values)):
            errors.append(f"duplicate {label}")
        return set(values)

    def refs(values: list[str], allowed: set[str], label: str) -> None:
        if not set(values) <= allowed:
            errors.append(f"unknown {label}: {sorted(set(values) - allowed)}")

    flags = unique([f["id"] for f in spec["flags"]], "flags")
    claims = unique([c["id"] for c in spec["claims"]], "claims")
    objectives = unique([o["id"] for o in spec["objectives"]], "objectives")
    scenes = unique([s["id"] for s in spec["scenes"]], "scenes")
    assets = unique([a["id"] for a in spec["asset_manifest"]], "assets")
    tasks = [t for s in spec["scenes"] for t in s["tasks"]]
    unique([t["id"] for t in tasks], "tasks")
    completion_flags = unique([t["completion_flag"] for t in tasks], "task completion flags")
    refs(list(completion_flags), flags, "task completion flag")
    if len(tasks) > 12:
        errors.append("more than 12 tasks")
    required = [t for t in tasks if t["required"]]
    if not 1 <= len(required) <= 6:
        errors.append("required task count outside 1..6")
    if set(spec["completion"]["required_flags"]) != {t["completion_flag"] for t in required}:
        errors.append("completion flags differ from required tasks")
    refs([spec["entry_scene"], spec["completion"]["scene_id"]], scenes, "scene")
    if spec["entry_scene"] == spec["completion"]["scene_id"]:
        errors.append("entry cannot be completion scene")

    def condition(node: dict, depth: int = 1) -> None:
        if depth > 6:
            errors.append("condition depth exceeds 6")
        if "flag_equals" in node:
            refs([node["flag_equals"]["id"]], flags, "condition flag")
        elif "not" in node:
            condition(node["not"], depth + 1)
        else:
            for child in next(iter(node.values())):
                condition(child, depth + 1)

    def effects(items: list[dict]) -> None:
        refs([e["set_flag"] for e in items], flags, "effect flag")
        if any(e["set_flag"] in completion_flags for e in items):
            errors.append("task completion flag must be engine-owned")

    claim_by_id = {c["id"]: c for c in spec["claims"]}
    for claim in spec["claims"]:
        refs(claim["evidence_span_ids"], evidence_ids, "evidence span")
    for objective in spec["objectives"]:
        refs(objective["claim_ids"], claims, "objective claim")
    for scene in spec["scenes"]:
        refs(scene["asset_ids"], assets, "scene asset")
        refs(scene["claim_ids"], claims, "scene claim")
        unique([t["id"] for t in scene["transitions"]], "transitions")
        if scene["id"] == spec["completion"]["scene_id"] and (scene["tasks"] or scene["transitions"]):
            errors.append("completion scene must be terminal")
        for transition in scene["transitions"]:
            refs([transition["target_scene"]], scenes, "transition target")
            condition(transition["requires"])
        for task in scene["tasks"]:
            refs(task["claim_ids"], claims, "task claim")
            refs(task["objective_ids"], objectives, "task objective")
            refs(task["feedback"]["claim_ids"], claims, "feedback claim")
            if task["required"]:
                if not task["claim_ids"] or not task["objective_ids"]:
                    errors.append("required task missing knowledge binding")
                if not any(claim_by_id[c]["content_type"] in {"supported", "legend"} for c in task["claim_ids"] if c in claim_by_id):
                    errors.append("required task missing evidence-supported knowledge")
                if any(claim_by_id[c]["content_type"] == "unconfirmed" for c in task["claim_ids"] if c in claim_by_id):
                    errors.append("required task uses unconfirmed claim")
                if not set(task["claim_ids"]) <= set(task["feedback"]["claim_ids"]):
                    errors.append("required feedback missing claim binding")
            condition(task["requires"])
            effects(task["on_success"])
            if task["type"] == "choice":
                unique([o["id"] for o in task["options"]], "choice options")
                if not any(o["correct"] for o in task["options"]):
                    errors.append("choice has no correct option")
                for option in task["options"]:
                    effects(option["on_success"])
                    if "target_scene" in option:
                        refs([option["target_scene"]], scenes, "choice target")
            elif task["type"] == "sequence":
                items = unique([i["id"] for i in task["items"]], "sequence items")
                edges: dict[str, set[str]] = {item: set() for item in items}
                for edge in task["precedence"]:
                    refs([edge["before"], edge["after"]], items, "precedence item")
                    refs([edge["claim_id"]], set(task["claim_ids"]), "precedence task claim")
                    if edge["before"] in edges and edge["after"] in edges:
                        edges[edge["before"]].add(edge["after"])
                visiting: set[str] = set()
                visited: set[str] = set()

                def acyclic(node: str) -> bool:
                    if node in visiting:
                        return False
                    if node in visited:
                        return True
                    visiting.add(node)
                    if any(not acyclic(child) for child in edges[node]):
                        return False
                    visiting.remove(node)
                    visited.add(node)
                    return True

                if any(not acyclic(node) for node in edges):
                    errors.append("cyclic sequence precedence")
    return errors


def replace_pointer(value: dict, pointer: str, replacement: object) -> None:
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer.removeprefix("/").split("/")]
    parent: dict | list = value
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    if isinstance(parent, list):
        parent[int(parts[-1])] = replacement
    else:
        parent[parts[-1]] = replacement


def main() -> int:
    schema = load("experience-spec.schema.json")
    sample = load("examples/workshop.valid.json")
    cases = load("examples/invalid-cases.json")
    evidence = load("examples/workshop.evidence.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    evidence_ids = {s["id"] for s in evidence["spans"]}
    errors: list[str] = []
    schema_errors = list(validator.iter_errors(sample))
    if schema_errors:
        errors.extend(f"positive schema: {e.json_path}: {e.message}" for e in schema_errors)
    else:
        errors.extend(f"positive semantics: {e}" for e in semantic_errors(sample, evidence_ids))
    if sample["source_snapshot_id"] != evidence["source_snapshot_id"]:
        errors.append("positive evidence snapshot mismatch")
    observed: list[dict[str, str]] = []
    for case in cases:
        candidate = copy.deepcopy(sample)
        replace_pointer(candidate, case["path"], case["value"])
        invalid_schema = bool(list(validator.iter_errors(candidate)))
        actual = "schema_invalid" if invalid_schema else ("semantic_invalid" if semantic_errors(candidate, evidence_ids) else "valid")
        observed.append({"id": case["id"], "expected": case["expected"], "actual": actual})
        if actual != case["expected"]:
            errors.append(f"negative case {case['id']}: expected {case['expected']}, got {actual}")
    # Independent fixed oracle for synthetic partial order; not a player engine.
    orders = {"".join(order) for order in itertools.permutations("ABC") if order.index("A") < order.index("C") and order.index("B") < order.index("C")}
    if orders != {"ABC", "BAC"}:
        errors.append(f"partial order oracle mismatch: {orders}")
    print(json.dumps({"check": "contract_fixtures", "status": "failed" if errors else "passed", "positive_fixtures": 1, "negative_fixtures": observed, "independent_valid_orders": sorted(orders), "errors": errors, "scope": "schema and static fixture checks only; no runtime, reachability, model, browser or content acceptance"}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
