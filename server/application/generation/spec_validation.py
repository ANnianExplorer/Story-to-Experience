"""JSON-Schema validation of generated artifacts (R02).

The model's candidate is checked against the same versioned Schema the editor,
player and validator use. A spec that fails here never reaches the engine, so
"the engine said it was fine" can never be read as "the contract was met".
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from server.domain.shared.errors import ValidationFailure

# server/application/generation/<module>.py -> repository root is parents[3].
CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "packages" / "contracts"
EXPERIENCE_SPEC_SCHEMA = CONTRACTS_DIR / "experience-spec.schema.json"
DIALOGUE_PROFILE_SCHEMA = CONTRACTS_DIR / "dialogue-profile.schema.json"


@lru_cache(maxsize=4)
def load_schema(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _errors(payload: Any, schema_path: Path, label: str) -> list[dict[str, str]]:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(load_schema(str(schema_path)))
    return [
        {"path": "/".join(str(part) for part in error.path) or "/", "message": error.message[:200]}
        for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path))[:10]
    ]


def validate_experience_spec(spec: Any) -> None:
    problems = _errors(spec, EXPERIENCE_SPEC_SCHEMA, "ExperienceSpec")
    if problems:
        raise ValidationFailure("SPEC_SCHEMA_INVALID", "候选规格不符合 ExperienceSpec 1.0.0 契约。", {"errors": problems})


def validate_dialogue_profile(profile_payload: Any) -> None:
    """Validate the profile's *runtime shape* (the dialogue-profile root is a oneOf union)."""
    from jsonschema import Draft202012Validator

    schema = load_schema(str(DIALOGUE_PROFILE_SCHEMA))
    branch = schema["$defs"]["profile"]
    validator = Draft202012Validator({**branch, "$defs": schema["$defs"]})
    problems = [
        {"path": "/".join(str(part) for part in error.path) or "/", "message": error.message[:200]}
        for error in sorted(validator.iter_errors(profile_payload), key=lambda item: list(item.path))[:10]
    ]
    if problems:
        raise ValidationFailure("DIALOGUE_SCHEMA_INVALID", "对话配置不符合 DialogueProfile 契约。", {"errors": problems})
