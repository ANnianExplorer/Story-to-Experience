"""Identifier helpers.

Business IDs are UUIDs (API contract). Internal ExperienceSpec node IDs use a
separate short ASCII alphabet and are validated in the engine, not here.
"""
from __future__ import annotations

import uuid

ID_PREFIX_LENGTH = 8


def new_id() -> str:
    return str(uuid.uuid4())


def parse_id(value: str, label: str = "id") -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        from .errors import ValidationFailure

        raise ValidationFailure("INVALID_ID", f"{label} 不是合法 UUID。", {"value": str(value)[:64]}) from exc
