"""API composition root: build adapters, mount routers, install error mapping.

Business rules live in ``server.application``; this module only chooses
implementations and wires them together.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI

from server.infrastructure.db.engine import create_engine, make_uow_factory
from server.infrastructure.llm.gateway import AnthropicGatewayProvider, MockProvider
from server.infrastructure.storage.blobs import LocalBlobStore
from server.infrastructure.validation.node_validator import NodeValidator
from xujing_api.config import Settings, get_settings
from xujing_api.core.errors import install_error_handlers
from xujing_api.core.identity import DevIdentity
from xujing_api.routers import conversations, delivery, meta, projects, runs

REPO_ROOT = Path(__file__).resolve().parents[3]
logger = logging.getLogger("xujing.startup")


def build_provider(settings: Settings) -> Any:
    if settings.model_provider == "mock":
        return MockProvider()
    return AnthropicGatewayProvider(
        base_url=settings.model_base_url,
        api_key=settings.model_api_key,
        model=settings.model_name,
    )


def create_app(
    settings: Settings | None = None,
    *,
    uow_factory: Any | None = None,
    identity: Any | None = None,
    provider: Any | None = None,
    validator: Any | None = None,
    blob_store: Any | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    engine = None
    if uow_factory is None:
        engine = create_engine(resolved.database_url)
        uow_factory = make_uow_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # A process that died mid-run leaves its run active, which blocks the
        # project's single active-task slot. Reaping at startup keeps a restart
        # from requiring manual database cleanup.
        try:
            from server.application.runs import RunService

            reaped = await RunService(app.state.uow_factory).reap_orphans()
            if reaped:
                logger.info("reaped %d orphaned run(s) at startup", reaped)
        except Exception:  # never block startup on housekeeping
            logger.exception("orphan reap failed at startup")
        yield
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title="叙境 API", version="0.5.0", lifespan=lifespan)
    install_error_handlers(app)
    app.state.settings = resolved
    app.state.uow_factory = uow_factory
    app.state.identity = identity or DevIdentity(enabled=resolved.identity_mode == "dev")
    app.state.provider = provider or build_provider(resolved)
    app.state.validator = validator or NodeValidator(package_root=REPO_ROOT / "packages" / "validator")
    app.state.blobs = blob_store or LocalBlobStore(resolved.storage_root)

    for module in (meta, projects, runs, delivery, conversations):
        app.include_router(module.router)
    return app
