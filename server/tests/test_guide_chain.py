"""Experience-side chain: share → session → Guide conversation → cited answer (simulated).

Covers F08-R03 (fixed share, revocation) and F11-R02/R03 (Guide bound to one
published version, public evidence only, citations mapped server-side).
"""
from __future__ import annotations

import pytest

from server.application.conversations.service import ConversationService
from server.application.delivery import DeliveryService
from server.infrastructure.validation.node_validator import NodeValidator
from server.tests.test_conversation import BoundGuideProvider
from server.tests.test_orchestration import ALICE, run_generation

pytestmark = pytest.mark.simulated


async def publish(uow_factory, blob_store, scripted_provider, node_validator):
    """Generate, record the deterministic report, approve and share a version."""
    project, _snapshot, _spans, outcome = await run_generation(
        uow_factory, blob_store, scripted_provider, node_validator
    )
    assert outcome.status == "succeeded", (outcome.error_code, outcome.error_message)
    delivery = DeliveryService(uow_factory)
    await delivery.record_validation(
        ALICE,
        outcome.version_id,
        report=outcome.validation,
        source_hash="s" * 64,
        runtime_hash="r" * 64,
    )
    async with uow_factory() as uow:
        version = await uow.versions.get(outcome.version_id)
    await delivery.submit_review(
        ALICE,
        outcome.version_id,
        decision="approved",
        notes="合成样例人工核对通过。",
        coverage_claim_ids=[claim["id"] for claim in version["spec"]["claims"]],
        expected_semantic_hash=version["semantic_hash"],
    )
    share, token = await delivery.create_share(
        ALICE, project.id, version_id=outcome.version_id, license_ack=True, hours=1
    )
    return project, outcome.version_id, share, token, delivery


async def test_guide_conversation_runs_only_on_the_shared_version(uow_factory, blob_store, scripted_provider, node_validator):
    project, version_id, share, token, delivery = await publish(
        uow_factory, blob_store, scripted_provider, node_validator
    )
    resolved = await delivery.resolve_share(token)
    assert resolved["version"]["id"] == version_id

    conversations = ConversationService(uow_factory, BoundGuideProvider(), provider_is_mock=True)
    session = await conversations.create_guide_session_from_experience(
        experience_session_id=(
            await delivery.create_experience_session(token, ALICE)
        )["session_id"],
        actor_id=ALICE,
    )
    assert session.version_id == version_id
    assert session.profile_hash
    assert session.share_id == share.id

    turn, _ = await conversations.submit_turn(
        ALICE, session.id, client_turn_id="guide-1", message="这个工具是用来做什么的？"
    )
    execution = await conversations.execute_turn(turn.id, scene_id="entry", flags=["done_s0"])
    assert execution.turn.status.value == "succeeded"
    assert execution.turn.citations, "a Guide answer must cite the frozen version's evidence"
    # Citations must come from the version's public evidence projection only.
    async with uow_factory() as uow:
        version = await uow.versions.get(version_id)
    public_scope = set(version["dialogue_profile"]["source_scope"])
    assert {citation.span_id for citation in execution.turn.citations} <= public_scope


async def test_revoking_the_share_blocks_new_guide_conversations(uow_factory, blob_store, scripted_provider, node_validator):
    _project, _version_id, share, token, delivery = await publish(
        uow_factory, blob_store, scripted_provider, node_validator
    )
    opened = await delivery.create_experience_session(token, ALICE)
    await delivery.revoke_share(ALICE, share.id)

    from server.domain.shared.errors import NotFound

    with pytest.raises(NotFound):
        await delivery.resolve_share(token)
    conversations = ConversationService(uow_factory, BoundGuideProvider(), provider_is_mock=True)
    with pytest.raises(NotFound):
        await conversations.create_guide_session_from_experience(
            experience_session_id=opened["session_id"], actor_id=ALICE
        )


async def test_share_token_is_never_stored_in_plain_text(uow_factory, blob_store, scripted_provider, node_validator):
    _project, _version_id, share, token, delivery = await publish(
        uow_factory, blob_store, scripted_provider, node_validator
    )
    assert token not in share.token_hash
    async with uow_factory() as uow:
        stored = await uow.shares.get(share.id)
    assert stored is not None
    assert stored["token_hash"] != token
    assert len(stored["token_hash"]) == 64


async def test_guide_session_rejects_unknown_experience_session(uow_factory, scripted_provider):
    conversations = ConversationService(uow_factory, BoundGuideProvider(), provider_is_mock=True)
    from server.domain.shared.errors import NotFound

    with pytest.raises(NotFound):
        await conversations.create_guide_session_from_experience(
            experience_session_id="00000000-0000-4000-8000-000000000000", actor_id=ALICE
        )
