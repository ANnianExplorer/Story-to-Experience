"""The prompt's worked example must itself be valid under the versioned Schema.

Without this, the example could drift from the contract and teach the model a
shape that the validator rejects — the exact failure mode it exists to prevent.
"""
from __future__ import annotations

import pytest

from server.application.generation.roles import SPEC_EXAMPLE, validate_payload, CANDIDATE_SCHEMA
from server.application.generation.spec_validation import validate_experience_spec


def test_prompt_example_is_schema_valid() -> None:
    validate_experience_spec(SPEC_EXAMPLE)


def test_prompt_example_rejects_unknown_fields() -> None:
    from server.domain.shared.errors import ValidationFailure

    broken = {**SPEC_EXAMPLE, "unexpected": 1}
    with pytest.raises(ValidationFailure) as error:
        validate_experience_spec(broken)
    assert error.value.code == "SPEC_SCHEMA_INVALID"


def test_candidate_envelope_schema_accepts_shape() -> None:
    payload = validate_payload(
        {"spec": SPEC_EXAMPLE, "dialogue": {"persona_name": "导览", "persona_role": "讲解", "adaptation_note": "改编角色。", "hint_policy": "gentle"}},
        CANDIDATE_SCHEMA,
        "Builder",
    )
    assert payload["spec"]["schema_version"] == "1.0.0"
