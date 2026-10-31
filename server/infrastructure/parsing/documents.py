"""Isolated parse step: text, text-layer PDFs and still images (F02-R01/R02).

Never OCRs, never fetches URLs, never trusts a file extension. A PDF without an
extractable text layer fails with NO_EXTRACTABLE_TEXT instead of producing an
empty ready document.

Images become *visual material*: the bytes stay in the content-addressed store and
are described by the model on demand (``describe_image``). The parser only proves
the file is a real PNG/JPEG/WebP of acceptable size, so a disguised script fails
here rather than reaching a decoder elsewhere.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from server.domain.shared.errors import UnsupportedMedia, ValidationFailure
from server.domain.shared.text import normalize_text

PDF_MAGIC = b"%PDF-"
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_TEXT_LAYER_PAGES = 200

# Signature -> (mime, decoder). SVG is deliberately absent: it is executable.
IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


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
    for signature, mime in IMAGE_SIGNATURES:
        if data.startswith(signature):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"\x00\x00\x01\x00"):
        raise UnsupportedMedia("不接受图标/可执行容器，请上传 PNG/JPEG/WebP 图片。")
    if data.lstrip()[:5].lower().startswith(b"<svg") or b"<svg" in data[:512].lower():
        raise UnsupportedMedia("不接受 SVG（可执行脚本），请上传 PNG/JPEG/WebP。")
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
        raise ValidationFailure("PDF_UNREADABLE", "PDF 无法解析。", {"reason": f"{type(exc).__name__}: {exc}"[:200]}) from exc
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


def parse_image(data: bytes, mime: str) -> ParsedDocument:
    """Validate a real raster image; text stays empty because vision reads it."""
    if len(data) > MAX_IMAGE_BYTES:
        raise ValidationFailure("SOURCE_TOO_LARGE", "图片超过 8 MB 上限。", {"limit": MAX_IMAGE_BYTES})
    if mime == "image/png":
        width, height = _png_size(data)
    elif mime == "image/jpeg":
        width, height = _jpeg_size(data)
    else:
        width, height = None, None
    if width and height and width * height > MAX_IMAGE_PIXELS:
        raise ValidationFailure(
            "IMAGE_TOO_LARGE",
            "图片像素过多，请压缩后再上传。",
            {"width": width, "height": height, "limit": MAX_IMAGE_PIXELS},
        )
    return ParsedDocument(text="", mime_type=mime, page_count=0)


def _png_size(data: bytes) -> tuple[int, int]:
    # IHDR is the first chunk: width/height are big-endian at offsets 16..24.
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise ValidationFailure("IMAGE_CORRUPT", "PNG 头不完整。")
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _jpeg_size(data: bytes) -> tuple[int, int]:
    index = 2
    while index < len(data) - 9:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            height = int.from_bytes(data[index + 5 : index + 7], "big")
            width = int.from_bytes(data[index + 7 : index + 9], "big")
            return width, height
        length = int.from_bytes(data[index + 2 : index + 4], "big")
        index += 2 + max(length, 2)
    raise ValidationFailure("IMAGE_CORRUPT", "JPEG 尺寸信息缺失。")


def parse_source(data: bytes, declared_content_type: str | None) -> ParsedDocument:
    mime = sniff_mime(data)
    if declared_content_type and declared_content_type not in {
        "text/plain",
        "application/pdf",
        "text/markdown",
        "image/png",
        "image/jpeg",
        "image/webp",
    }:
        raise UnsupportedMedia(f"不支持的内容类型：{declared_content_type}。")
    if mime == "application/pdf":
        return parse_pdf(data)
    if mime.startswith("image/"):
        return parse_image(data, mime)
    return ParsedDocument(text=normalize_text(decode_text(data)), mime_type="text/plain", page_count=0)
