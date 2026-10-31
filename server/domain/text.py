"""Text normalisation, hashing and span slicing rules (F02-R02, data-model §文本与哈希).

Rules implemented here are deliberately narrow: CRLF/CR -> LF and Unicode NFC.
Whitespace is never collapsed and body text is never deleted, so offsets keep a
deterministic meaning. Offsets are Unicode code point half-open intervals; the
Python ``str`` index already counts code points.
"""
from __future__ import annotations

import hashlib
import unicodedata

from .errors import ValidationFailure


def normalize_text(raw: str) -> str:
    """Normalise line endings then NFC. Idempotent."""
    unified = raw.replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", unified)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def normalize_and_hash(raw: str) -> tuple[str, str]:
    normalized = normalize_text(raw)
    return normalized, sha256_text(normalized)


def slice_span(text: str, start: int, end: int) -> str:
    """Return the half-open slice, rejecting negative, inverted or out-of-range spans."""
    if start < 0 or end < start or end > len(text):
        raise ValidationFailure(
            "SPAN_OUT_OF_RANGE",
            "片段定位超出规范化文本范围。",
            {"start": start, "end": end, "length": len(text)},
        )
    return text[start:end]


def paragraph_spans(text: str) -> list[tuple[int, int]]:
    """Split normalised text into non-empty paragraph spans.

    A paragraph is a maximal run of non-blank lines. Leading/trailing blank
    lines are excluded from the span but never removed from the document.
    """
    spans: list[tuple[int, int]] = []
    start: int | None = None
    position = 0
    for line in text.split("\n"):
        line_end = position + len(line)
        if line.strip():
            if start is None:
                start = position
            end = line_end
        else:
            if start is not None:
                spans.append((start, end))
                start = None
        position = line_end + 1  # account for the newline itself
    if start is not None:
        spans.append((start, len(text)))
    return spans


def is_blank(text: str) -> bool:
    return not text.strip()
