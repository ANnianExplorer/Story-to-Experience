from __future__ import annotations

from collections.abc import AsyncIterator

import dataclasses

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from server.infrastructure.db.engine import create_all, drop_all, make_uow_factory
from xujing_api.config import Settings
from xujing_api.main import create_app

ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite://",
        environment="test",
        bind_host="127.0.0.1",
        bind_port=8000,
        identity_mode="dev",
        storage_root="var/test-blobs",
        model_provider="mock",
        model_base_url=None,
        model_api_key=None,
        model_name="mock",
        mock_allowed=True,
    )


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    engine = create_async_engine(
        settings.database_url, poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    await create_all(engine)
    app = create_app(settings, uow_factory=make_uow_factory(engine))
    yield httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"x-actor-id": ALICE},
    )
    await drop_all(engine)
    await engine.dispose()


def brief_json(audience: str = "五年级学生") -> dict[str, object]:
    return {"audience": audience, "duration_minutes": 8, "learning_goals": ["观察工具用途"]}


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_create_and_get_project(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/projects", json={"name": "工坊体验", "brief": brief_json()})
    assert created.status_code == 201
    body = created.json()
    assert body["data"]["name"] == "工坊体验"
    assert body["request_id"]
    project_id = body["data"]["id"]

    fetched = await client.get(f"/api/v1/projects/{project_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["brief"]["audience"] == "五年级学生"


async def test_owner_comes_from_session_not_payload(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/projects",
        json={"name": "伪造归属", "brief": brief_json(), "owner_id": BOB},
    )
    assert created.status_code == 201
    other = await client.get(
        f"/api/v1/projects/{created.json()['data']['id']}", headers={"x-actor-id": BOB}
    )
    assert other.status_code == 404
    assert other.json()["error"]["code"] == "NOT_FOUND"


async def test_invalid_brief_returns_422_details(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/projects",
        json={"name": "坏简报", "brief": {"audience": "", "duration_minutes": 99, "learning_goals": []}},
    )
    assert response.status_code == 422


async def test_patch_requires_expected_revision(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/projects", json={"name": "工坊体验", "brief": brief_json()})
    project_id = created.json()["data"]["id"]
    missing = await client.patch(f"/api/v1/projects/{project_id}", json={"brief": brief_json("六年级")})
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "EXPECTED_REVISION_REQUIRED"

    ok = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"brief": brief_json("六年级"), "expected_revision": 1},
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["brief_revision"] == 2

    stale = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"brief": brief_json("七年级"), "expected_revision": 1},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "BRIEF_REVISION_CONFLICT"


async def test_unauthenticated_when_identity_disabled(settings: Settings) -> None:
    disabled = dataclasses.replace(settings, identity_mode="disabled")
    engine = create_async_engine(
        disabled.database_url, poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    await create_all(engine)
    app = create_app(disabled, uow_factory=make_uow_factory(engine))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as raw:
        response = await raw.get("/api/v1/projects")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    await drop_all(engine)
    await engine.dispose()
