"""End-to-end HTTP test of the participant chain (simulated model).

The creator side is prepared through the application services; every participant
step is exercised over HTTP only: share token → manifest → experience session →
Guide conversation → turn, then the share is revoked and the participant surface
must close.
"""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from server.application.delivery import DeliveryService
from server.application.generation.orchestration import OrchestrationService
from server.application.runs import RunService
from server.infrastructure.db.engine import create_all, drop_all, make_uow_factory
from server.tests.providers_spanaware import SpanAwareProvider
from xujing_api.config import Settings
from xujing_api.main import create_app

ALICE = "11111111-1111-4111-8111-111111111111"
MATERIAL = "合成材料设定工具 X 用于观察。\n\n合成材料设定 A 先于 C。\n\n合成材料设定 B 先于 C。"

pytestmark = pytest.mark.simulated


def brief_json() -> dict[str, object]:
    return {"audience": "五年级学生", "duration_minutes": 5, "learning_goals": ["观察工具用途"]}


@pytest.fixture
async def participant(tmp_path):
    """A client plus the app it talks to (needed to build creator-side state)."""
    settings = Settings(
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
    engine = create_async_engine(
        settings.database_url, poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    await create_all(engine)
    app = create_app(settings, uow_factory=make_uow_factory(engine), provider=SpanAwareProvider())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"x-actor-id": ALICE},
    ) as client:
        yield client, app
    await drop_all(engine)
    await engine.dispose()


async def _prepare(client: httpx.AsyncClient, app) -> tuple[str, str, str]:
    created = await client.post("/api/v1/projects", json={"name": "分享项目", "brief": brief_json()})
    project_id = created.json()["data"]["id"]
    uploaded = await client.post(
        f"/api/v1/projects/{project_id}/sources/text",
        json={"text": MATERIAL, "title": "材料", "license_note": "合成"},
    )
    source_id = uploaded.json()["data"]["source_id"]
    spans = await client.get(f"/api/v1/sources/{source_id}/spans")
    span_ids = [span["id"] for span in spans.json()["data"]]
    await client.post(
        f"/api/v1/projects/{project_id}/claims",
        json={
            "claims": [
                {"statement": "合成材料设定工具 X 用于观察。", "content_type": "supported", "evidence_span_ids": [span_ids[2]]},
                {"statement": "合成材料设定 A 先于 C。", "content_type": "supported", "evidence_span_ids": [span_ids[0]]},
                {"statement": "合成材料设定 B 先于 C。", "content_type": "supported", "evidence_span_ids": [span_ids[1]]},
            ]
        },
    )
    snapshot = await client.post(f"/api/v1/projects/{project_id}/source-snapshots", json={"source_ids": [source_id]})
    snapshot_id = snapshot.json()["data"]["id"]

    runs = RunService(app.state.uow_factory)
    submitted = await runs.submit_generation(
        ALICE,
        project_id,
        source_snapshot_id=snapshot_id,
        brief_revision=1,
        idempotency_key="participant-1",
    )
    await runs.claim(submitted.run_id, "worker-test")
    outcome = await OrchestrationService(
        app.state.uow_factory, app.state.provider, app.state.validator, provider_is_mock=True
    ).execute(submitted.run_id, actor_instruction="给五年级使用，保留出处。")
    assert outcome.status == "succeeded", (outcome.error_code, outcome.error_message)

    delivery = DeliveryService(app.state.uow_factory)
    await delivery.record_validation(
        ALICE, outcome.version_id, report=outcome.validation, source_hash="s" * 64, runtime_hash="r" * 64
    )
    async with app.state.uow_factory() as uow:
        version = await uow.versions.get(outcome.version_id)
    await delivery.submit_review(
        ALICE,
        outcome.version_id,
        decision="approved",
        notes="合成样例核对通过。",
        coverage_claim_ids=[claim["id"] for claim in version["spec"]["claims"]],
        expected_semantic_hash=version["semantic_hash"],
    )
    share, token = await delivery.create_share(
        ALICE, project_id, version_id=outcome.version_id, license_ack=True, hours=1
    )
    return project_id, share.id, token


async def test_participant_flow_then_revocation(participant) -> None:
    client, app = participant
    _project_id, share_id, token = await _prepare(client, app)

    manifest = await client.get(f"/api/v1/share/{token}/manifest")
    assert manifest.status_code == 200, manifest.text
    version_id = manifest.json()["data"]["version_id"]
    assert manifest.json()["data"]["dialogue_profile"]["persona"]["name"]

    session = await client.post(f"/api/v1/share/{token}/sessions")
    assert session.status_code == 201, session.text
    experience_session_id = session.json()["data"]["session_id"]

    guide = await client.post(f"/api/v1/experience-sessions/{experience_session_id}/conversations")
    assert guide.status_code == 201, guide.text
    conversation_id = guide.json()["data"]["conversation_id"]
    assert guide.json()["data"]["version_id"] == version_id

    turn = await client.post(
        f"/api/v1/conversations/{conversation_id}/turns",
        json={"client_turn_id": "participant-turn-1", "message": "这个工具是用来做什么的？"},
    )
    assert turn.status_code == 202, turn.text
    executed = await client.post(f"/api/v1/conversation-turns/{turn.json()['data']['turn_id']}/run")
    assert executed.status_code == 200, executed.text
    payload = executed.json()["data"]
    assert payload["status"] == "succeeded"
    assert payload["citations"], "a Guide answer must carry server-mapped citations"

    revoked = await client.delete(f"/api/v1/shares/{share_id}")
    assert revoked.status_code == 204
    after = await client.get(f"/api/v1/share/{token}/manifest")
    assert after.status_code == 404
    assert after.json()["error"]["code"] == "SHARE_NOT_FOUND"
    blocked = await client.post(f"/api/v1/experience-sessions/{experience_session_id}/conversations")
    assert blocked.status_code == 404


async def test_share_creation_requires_license_acknowledgement(participant) -> None:
    client, app = participant
    project_id, _share_id, _token = await _prepare(client, app)
    versions = await client.get(f"/api/v1/projects/{project_id}/versions")
    version_id = versions.json()["data"][0]["id"]
    refused = await client.post(
        f"/api/v1/versions/{version_id}/shares", json={"version_id": version_id, "license_ack": False}
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "LICENSE_ACK_REQUIRED"


async def test_export_of_missing_version_is_404(participant) -> None:
    client, _app = participant
    missing = await client.post(
        "/api/v1/versions/00000000-0000-4000-8000-000000000000/exports", json={"mode": "draft"}
    )
    assert missing.status_code == 404
