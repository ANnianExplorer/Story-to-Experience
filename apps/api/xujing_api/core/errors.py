"""HTTP mapping for domain errors and the standard success/error envelopes."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from server.domain.shared.errors import DomainError


def request_id_of(request: Request) -> str:
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, str) and existing:
        return existing
    generated = str(uuid.uuid4())
    request.state.request_id = generated
    return generated


def envelope(data: Any, request: Request, *, cursor: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"data": data, "request_id": request_id_of(request)}
    if cursor is not None:
        body["next_cursor"] = cursor
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "object_id": exc.object_id,
                    "retryable": exc.retryable,
                    "details": exc.details,
                },
                "request_id": request_id_of(request),
            },
        )
