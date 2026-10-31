from __future__ import annotations

import dataclasses
import json
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from server.infrastructure.db.engine import create_all, drop_all, make_uow_factory
from server.tests.providers import ScriptedProvider
from server.tests.scripted_agents import scripted
from xujing_api.config import Settings
from xujing_api.main import create_app

ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite://",
        environment="test",
        bind_host="127.0.0.1",
        bind_port=8000,
        identity_mode="dev",
        storage_root=str(tmp_path / "blobs"),
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
    app = create_app(
        settings,
        uow_factory=make_uow_factory(engine),
        provider=ScriptedProvider(scripted()),
    )
    yield httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"x-actor-id": ALICE},
    )
    await drop_all(engine)
    await engine.dispose()


def brief_json(audience: str = "五年级学生") -> dict[str, object]:
    return {"audience": audience, "duration_minutes": 5, "learning_goals": ["观察工具用途"]}


MATERIAL = "合成材料设定工具 X 用于观察。\n\n合成材料设定 A 先于 C。\n\n合成材料设定 B 先于 C。"


async def test_health_reports_mode(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["simulated"] is True


async def test_full_creator_to_guide_flow(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/projects", json={"name": "工坊体验", "brief": brief_json()})
    assert created.status_code == 201
    project_id = created.json()["data"]["id"]

    uploaded = await client.post(
        f"/api/v1/projects/{project_id}/sources/text",
        json={"text": MATERIAL, "title": "合成材料", "license_note": "合成样例，允许演示。"},
    )
    assert uploaded.status_code == 202, uploaded.text
    source_id = uploaded.json()["data"]["source_id"]
    assert uploaded.json()["data"]["parse_status"] == "ready"

    spans = await client.get(f"/api/v1/sources/{source_id}/spans")
    span_ids = [span["id"] for span in spans.json()["data"]]
    assert len(span_ids) == 3

    claims = await client.post(
        f"/api/v1/projects/{project_id}/claims",
        json={
            "claims": [
                {"statement": "合成材料设定工具 X 用于观察。", "content_type": "supported", "evidence_span_ids": [span_ids[2]]},
                {"statement": "合成材料设定 A 先于 C。", "content_type": "supported", "evidence_span_ids": [span_ids[0]]},
                {"statement": "合成材料设定 B 先于 C。", "content_type": "supported", "evidence_span_ids": [span_ids[1]]},
            ]
        },
    )
    assert claims.status_code == 201, claims.text

    snapshot = await client.post(
        f"/api/v1/projects/{project_id}/source-snapshots", json={"source_ids": [source_id]}
    )
    snapshot_id = snapshot.json()["data"]["id"]

    run = await client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"source_snapshot_id": snapshot_id, "brief_revision": 1},
        headers={"Idempotency-Key": "run-key-1"},
    )
    assert run.status_code == 202, run.text
    run_id = run.json()["data"]["run_id"]

    duplicate = await client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"source_snapshot_id": snapshot_id, "brief_revision": 1},
        headers={"Idempotency-Key": "run-key-1"},
    )
    assert duplicate.json()["data"]["run_id"] == run_id
    assert duplicate.json()["data"]["created"] is False

    async with client.stream("GET", f"/api/v1/runs/{run_id}/events") as stream:
        payload = "".join([chunk async for chunk in stream.aiter_text()])
    assert "queued" in payload

    cancelled = await client.post(f"/api/v1/runs/{run_id}/cancel")
    assert cancelled.json()["data"]["status"] == "cancelled"


async def test_missing_idempotency_key_is_rejected(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/projects", json={"name": "无键", "brief": brief_json()})
    project_id = created.json()["data"]["id"]
    response = await client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"source_snapshot_id": "10000000-0000-4000-8000-000000000001", "brief_revision": 1},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


async def test_scan_only_pdf_is_rejected_not_silently_empty(client: httpx.AsyncClient) -> None:
    from io import BytesIO

    from pypdf import PdfWriter

    created = await client.post("/api/v1/projects", json={"name": "扫描件", "brief": brief_json()})
    project_id = created.json()["data"]["id"]
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)  # image-only page: no text layer
    writer.write(buffer)
    response = await client.post(
        f"/api/v1/projects/{project_id}/sources",
        files={"file": ("scan.pdf", buffer.getvalue(), "application/pdf")},
        data={"license_note": "扫描件测试"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "NO_EXTRACTABLE_TEXT", response.json()


async def test_other_user_cannot_read_any_subresource(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/projects", json={"name": "私有", "brief": brief_json()})
    project_id = created.json()["data"]["id"]
    uploaded = await client.post(
        f"/api/v1/projects/{project_id}/sources/text",
        json={"text": MATERIAL, "title": "材料", "license_note": "合成"},
    )
    source_id = uploaded.json()["data"]["source_id"]
    bob = {"x-actor-id": BOB}
    for path in (
        f"/api/v1/projects/{project_id}",
        f"/api/v1/sources/{source_id}",
        f"/api/v1/sources/{source_id}/spans",
        f"/api/v1/projects/{project_id}/claims",
        f"/api/v1/projects/{project_id}/versions",
    ):
        response = await client.get(path, headers=bob)
        assert response.status_code == 404, path
        assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_creator_conversation_endpoint_streams_citations(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/projects", json={"name": "对话项目", "brief": brief_json()})
    project_id = created.json()["data"]["id"]
    uploaded = await client.post(
        f"/api/v1/projects/{project_id}/sources/text",
        json={"text": MATERIAL, "title": "材料", "license_note": "合成"},
    )
    assert uploaded.status_code == 202
    conversation = await client.post(f"/api/v1/projects/{project_id}/conversations", json={})
    assert conversation.status_code == 201
    conversation_id = conversation.json()["data"]["conversation_id"]

    turn = await client.post(
        f"/api/v1/conversations/{conversation_id}/turns",
        json={"client_turn_id": "client-turn-0001", "message": "请解释这份材料的用途"},
    )
    assert turn.status_code == 202, turn.text
    turn_id = turn.json()["data"]["turn_id"]
    # A turn that has not finished must not expose partial text as the answer.
    partial = await client.get(f"/api/v1/conversation-turns/{turn_id}/events")
    assert partial.status_code == 422
    assert partial.json()["error"]["code"] == "TURN_INCOMPLETE"


async def test_guide_session_cannot_be_created_without_active_share(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/share/not-a-real-token/manifest")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SHARE_NOT_FOUND"
    session = await client.post("/api/v1/share/not-a-real-token/sessions")
    assert session.status_code == 404


async def test_listing_project_sources_restores_workbench_state(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/projects", json={"name": "资料列表", "brief": brief_json()})
    project_id = created.json()["data"]["id"]
    uploaded = await client.post(
        f"/api/v1/projects/{project_id}/sources/text",
        json={"text": MATERIAL, "title": "材料一", "license_note": "合成"},
    )
    source_id = uploaded.json()["data"]["source_id"]

    listed = await client.get(f"/api/v1/projects/{project_id}/sources")
    assert listed.status_code == 200
    items = listed.json()["data"]
    assert [item["source_id"] for item in items] == [source_id]
    assert items[0]["parse_status"] == "ready"
    assert items[0]["title"] == "材料一"

    # Another actor sees the project as nonexistent, not an empty list.
    other = await client.get(
        f"/api/v1/projects/{project_id}/sources", headers={"x-actor-id": BOB}
    )
    assert other.status_code == 404
