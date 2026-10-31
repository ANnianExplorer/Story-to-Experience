"""Health and capability reporting.

The report is deliberately explicit about simulation and validation
availability: a caller must be able to tell a real run from a scripted one.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["meta"])


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    provider = request.app.state.provider
    return {
        "status": "ok",
        "environment": settings.environment,
        "model_provider": getattr(provider, "name", "unknown"),
        "model_configured": getattr(provider, "configured", True),
        "simulated": bool(getattr(provider, "is_mock", False)),
        "validator_available": bool(getattr(request.app.state.validator, "script_exists", True)),
    }
