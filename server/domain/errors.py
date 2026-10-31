"""Stable error codes shared by domain, application and HTTP mapping.

Every rejection carries a code the API layer maps to one HTTP status; unknown
errors are never converted into empty results.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DomainError(Exception):
    code: str
    message: str
    status: int = 422
    object_id: str | None = None
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code}: {self.message}"


class NotFound(DomainError):
    def __init__(self, code: str = "NOT_FOUND", message: str = "资源不存在。", object_id: str | None = None) -> None:
        super().__init__(code=code, message=message, status=404, object_id=object_id)


class Unauthorized(DomainError):
    def __init__(self, message: str = "需要身份认证。") -> None:
        super().__init__(code="UNAUTHORIZED", message=message, status=401)


class Forbidden(DomainError):
    def __init__(self, message: str = "无权执行该操作。") -> None:
        super().__init__(code="FORBIDDEN", message=message, status=403)


class Conflict(DomainError):
    def __init__(self, code: str, message: str, object_id: str | None = None) -> None:
        super().__init__(code=code, message=message, status=409, object_id=object_id)


class ValidationFailure(DomainError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code=code, message=message, status=422, details=details or {})


class TooLarge(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__(code="PAYLOAD_TOO_LARGE", message=message, status=413)


class UnsupportedMedia(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__(code="UNSUPPORTED_MEDIA_TYPE", message=message, status=415)


class NotConfigured(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__(code="NOT_CONFIGURED", message=message, status=503)
