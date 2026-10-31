from __future__ import annotations

import unicodedata

import pytest

from server.domain.shared.errors import ValidationFailure
from server.domain.shared.text import (
    normalize_text,
    paragraph_spans,
    sha256_text,
    slice_span,
)


def test_normalize_is_idempotent_and_keeps_whitespace() -> None:
    raw = "第一行\r\n\r\n  第二行\t有空格  \r第三行"
    once = normalize_text(raw)
    assert once == "第一行\n\n  第二行\t有空格  \n第三行"
    assert normalize_text(once) == once


def test_normalize_applies_nfc_without_changing_code_points_meaning() -> None:
    decomposed = "é"
    composed = unicodedata.normalize("NFC", decomposed)
    assert normalize_text(decomposed) == composed
    assert len(composed) == 1


def test_slice_span_uses_code_points_and_rejects_bad_ranges() -> None:
    text = "𝕏文化"  # astral plane char is one code point in Python str
    assert slice_span(text, 0, 1) == "𝕏"
    assert slice_span(text, 1, 3) == "文化"
    with pytest.raises(ValidationFailure) as error:
        slice_span(text, 2, 1)
    assert error.value.code == "SPAN_OUT_OF_RANGE"
    with pytest.raises(ValidationFailure):
        slice_span(text, 0, 4)


def test_paragraph_spans_cover_non_blank_runs_exactly() -> None:
    text = "甲\n\n乙丙\n丁\n\n\n戊"
    spans = paragraph_spans(text)
    quotes = [text[start:end] for start, end in spans]
    assert quotes == ["甲", "乙丙\n丁", "戊"]


def test_sha256_matches_known_value() -> None:
    assert sha256_text("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_png_is_accepted_as_visual_material_and_svg_is_rejected() -> None:
    import struct
    import zlib

    from server.infrastructure.parsing.documents import parse_source
    from server.domain.shared.errors import UnsupportedMedia, ValidationFailure

    def chunk(kind: bytes, body: bytes) -> bytes:
        payload = kind + body
        return struct.pack(">I", len(body)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 3, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00" * 12))
        + chunk(b"IEND", b"")
    )
    parsed = parse_source(png, "image/png")
    assert parsed.mime_type == "image/png"
    assert parsed.text == "", "an image has no text layer; it is described by the model on demand"

    with pytest.raises(UnsupportedMedia):
        parse_source(b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", None)
    with pytest.raises(ValidationFailure):
        parse_source(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "image/png")
