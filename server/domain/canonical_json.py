"""Canonical JSON serialisation used for content hashing (data-model §文本与哈希).

Implements the RFC 8785 (JCS) subset this project needs: object keys sorted by
UTF-16 code units, no insignificant whitespace, strings escaped with the
shortest valid JSON form, and only integers/strings/booleans/null/arrays/
objects. Floats, NaN, Infinity and non-string keys are rejected instead of being
silently rounded, because a silent change would break hash equality across
languages and invalidate reviews.
"""
from __future__ import annotations

import json
from typing import Any, NoReturn

from .errors import ValidationFailure


def _escaped_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _reject(message: str) -> NoReturn:
    raise ValidationFailure("NON_CANONICAL_JSON", message)


def _serialize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        _reject("规范 JSON 不接受浮点数，请使用整数或定点字符串。")
    if isinstance(value, str):
        return _escaped_string(value)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                _reject("规范 JSON 的对象键必须是字符串。")
        ordered = sorted(value, key=lambda key: key.encode("utf-16-be"))
        return "{" + ",".join(f"{_escaped_string(k)}:{_serialize(value[k])}" for k in ordered) + "}"
    _reject(f"规范 JSON 不支持的类型：{type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return the canonical UTF-8 JSON text (str) for hashing and storage."""
    return _serialize(value)


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    import hashlib

    return hashlib.sha256(canonical_bytes(value)).hexdigest()
