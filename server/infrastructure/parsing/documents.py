"""Isolated parse step: text and text-layer PDFs only (F02-R01/R02).

Never OCRs, never fetches URLs, never trusts a file extension. A PDF without an
extractable text layer fails with NO_EXTRACTABLE_TEXT instead of producing an
empty ready document.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from server.domain.errors import UnsupportedMedia, ValidationFailure
from server.domain.text import normalize_text

PDF_MAGIC = b"%PDF-"
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_TEXT_LAYER_PAGES = 200


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    text: str
    mime_type: str
    page_count: int


def sniff_mime(data: bytes) -> str:
    if data.startswith(PDF_MAGIC):
        return "application/pdf"
    if data.startswith(b"<") or b"<html" in data[:512].lower():
        raise UnsupportedMedia("不接受 HTML/XML 内容，请上传纯文本或文本 PDF。")
    if data.startswith(b"\x00\x00\x01\x00") or data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8"):
        raise UnsupportedMedia("图片需走图片资料通道，当前仅接受纯文本与文本 PDF。")
    return "text/plain"


def decode_text(data: bytes) -> str:
    if len(data) > MAX_TEXT_BYTES:
        raise ValidationFailure("SOURCE_TOO_LARGE", "文本资料超过 2 MB 上限。", {"limit": MAX_TEXT_BYTES})
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    try:
        return data.decode("gb18030")
    except UnicodeDecodeError as exc:
        raise ValidationFailure("SOURCE_ENCODING", "无法以 UTF-8 或 GB18030 解码文本。") from exc


def parse_pdf(data: bytes) -> ParsedDocument:
    if len(data) > MAX_PDF_BYTES:
        raise ValidationFailure("SOURCE_TOO_LARGE", "PDF 超过 20 MB 上限。", {"limit": MAX_PDF_BYTES})
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # pypdf raises several unrelated types
        raise ValidationFailure("PDF_UNREADABLE", "PDF 无法解析。") from exc
    if reader.is_encrypted:
        raise ValidationFailure("PDF_ENCRYPTED", "不接受加密 PDF。")
    if len(reader.pages) > MAX_TEXT_LAYER_PAGES:
        raise ValidationFailure("PDF_TOO_MANY_PAGES", "PDF 页数超出上限。", {"limit": MAX_TEXT_LAYER_PAGES})
    chunks: list[str] = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:  # a broken page must not silently produce empty success
            chunks.append("")
    text = "\n\n".join(chunks)
    if not text.strip():
        raise ValidationFailure(
            "NO_EXTRACTABLE_TEXT",
            "PDF 没有可提取的文字层（可能是扫描件）；请上传文本 PDF 或纯文本。",
        )
    return ParsedDocument(text=normalize_text(text), mime_type="application/pdf", page_count=len(reader.pages))


def parse_source(data: bytes, declared_content_type: str | None) -> ParsedDocument:
    mime = sniff_mime(data)
    if declared_content_type and declared_content_type not in {"text/plain", "application/pdf", "text/markdown"}:
        raise UnsupportedMedia(f"不支持的内容类型：{declared_content_type}。")
    if mime == "application/pdf":
        return parse_pdf(data)
    return ParsedDocument(text=normalize_text(decode_text(data)), mime_type="text/plain", page_count=0)
