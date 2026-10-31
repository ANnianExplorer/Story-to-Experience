"""Delivery use cases: human review, shares, stable promotion, export gating (F08, F07)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from server.application.ports import ScopeFactory
from server.domain.shared.canonical_json import canonical_sha256
from server.domain.delivery import (
    ContentReview,
    Share,
    hash_share_token,
    issue_share_token,
    verify_share_token,
)
from server.domain.shared.errors import Conflict, NotFound, ValidationFailure
from server.domain.shared.ids import new_id
from server.domain.versions import assert_can_go_stable

DEFAULT_SHARE_HOURS = 72


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class DeliveryService:
    def __init__(self, uow: ScopeFactory) -> None:
        self._uow = uow

    async def _owned_version(self, uow, actor_id: str, version_id: str) -> dict:
        version = await uow.versions.get(version_id)
        if version is None:
            raise NotFound(object_id=version_id)
        project = await uow.projects.get(version["project_id"])
        if project is None or project.owner_id != actor_id:
            raise NotFound(object_id=version_id)
        return version

    async def submit_review(
        self,
        actor_id: str,
        version_id: str,
        *,
        decision: str,
        notes: str,
        coverage_claim_ids: list[str],
        expected_semantic_hash: str,
        actor_kind: str = "human",
    ) -> ContentReview:
        ContentReview.reject_model_approval(actor_kind)
        async with self._uow() as uow:
            version = await self._owned_version(uow, actor_id, version_id)
            if version["semantic_hash"] != expected_semantic_hash:
                raise Conflict(
                    "SEMANTIC_HASH_MISMATCH",
                    "内容语义已变化，审核必须基于当前哈希。",
                    object_id=version_id,
                )
            claim_ids = {claim["id"] for claim in version["spec"].get("claims", [])}
            unknown = set(coverage_claim_ids) - claim_ids
            if unknown:
                raise ValidationFailure(
                    "REVIEW_COVERAGE_UNKNOWN",
                    "审核覆盖了不属于该版本的事实。",
                    {"unknown": sorted(unknown)},
                )
            if decision == "approved" and not coverage_claim_ids:
                raise ValidationFailure("REVIEW_COVERAGE_REQUIRED", "批准必须说明覆盖了哪些事实。")
            review = ContentReview(
                id=new_id(),
                version_id=version_id,
                semantic_hash=version["semantic_hash"],
                reviewer_id=actor_id,
                decision=decision,  # type: ignore[arg-type]
                notes=notes,
                coverage_claim_ids=tuple(coverage_claim_ids),
                created_at=_now(),
            )
            await uow.reviews.add(
                review_id=review.id,
                version_id=version_id,
                project_id=version["project_id"],
                semantic_hash=review.semantic_hash,
                reviewer_id=actor_id,
                decision=review.decision,
                notes=review.notes,
                coverage_claim_ids=list(review.coverage_claim_ids),
            )
            await uow.commit()
        return review

    async def record_validation(
        self,
        actor_id: str,
        version_id: str,
        *,
        report: dict,
        source_hash: str,
        runtime_hash: str,
    ) -> None:
        async with self._uow() as uow:
            version = await self._owned_version(uow, actor_id, version_id)
            await uow.reviews.add_report(
                report_id=new_id(),
                version_id=version_id,
                project_id=version["project_id"],
                spec_hash=version["spec_hash"],
                source_hash=source_hash,
                runtime_hash=runtime_hash,
                checker_version=str(report.get("checker_version", "unknown")),
                layer="full",
                status=str(report.get("status", "not_run")),
                evidence_manifest={
                    "search": report.get("search"),
                    "findings": report.get("findings"),
                    "layers": report.get("layers"),
                },
            )
            await uow.commit()

    async def promote_stable(self, actor_id: str, project_id: str, version_id: str) -> dict:
        async with self._uow() as uow:
            project = await uow.projects.get_for_update(project_id)
            if project is None:
                raise NotFound(object_id=project_id)
            project.assert_owned_by(actor_id)
            version = await self._owned_version(uow, actor_id, version_id)
            reports = await uow.reviews.reports_for(version_id)
            latest = await uow.reviews.latest_for(version_id)
            technical = reports[0]["status"] if reports else "not_run"
            hash_ok = bool(reports) and reports[0]["spec_hash"] == version["spec_hash"]
            content = latest["decision"] if latest else "pending"
            hash_ok = hash_ok and bool(latest) and latest["semantic_hash"] == version["semantic_hash"]
            assert_can_go_stable(
                technical, "approved" if content == "approved" else content, hash_matches=hash_ok, license_ok=True
            )
            project.stable_version_id = version_id
            await uow.projects.save(project)
            await uow.commit()
        return {"project_id": project_id, "stable_version_id": version_id}

    async def create_share(
        self,
        actor_id: str,
        project_id: str,
        *,
        version_id: str,
        license_ack: bool,
        hours: int = DEFAULT_SHARE_HOURS,
    ) -> tuple[Share, str]:
        if not license_ack:
            raise ValidationFailure("LICENSE_ACK_REQUIRED", "创建分享前必须确认素材与引文许可。")
        async with self._uow() as uow:
            project = await uow.projects.get_for_update(project_id)
            if project is None:
                raise NotFound(object_id=project_id)
            project.assert_owned_by(actor_id)
            version = await uow.versions.get(version_id)
            if version is None or version["project_id"] != project_id:
                raise NotFound(object_id=version_id)
            reports = await uow.reviews.reports_for(version_id)
            latest = await uow.reviews.latest_for(version_id)
            technical = reports[0]["status"] if reports else "not_run"
            hash_ok = bool(reports) and reports[0]["spec_hash"] == version["spec_hash"]
            content = latest["decision"] if latest else "pending"
            hash_ok = hash_ok and bool(latest) and latest["semantic_hash"] == version["semantic_hash"]
            assert_can_go_stable(
                technical, "approved" if content == "approved" else content, hash_matches=hash_ok, license_ok=True
            )
            raw, token_hash = issue_share_token()
            share = Share(
                id=new_id(),
                project_id=project_id,
                version_id=version_id,
                token_hash=token_hash,
                expires_at=_now() + timedelta(hours=hours),
                license_ack=True,
            )
            await uow.shares.add(
                share_id=share.id,
                project_id=project_id,
                version_id=version_id,
                token_hash=token_hash,
                expires_at=share.expires_at,
            )
            await uow.commit()
        return share, raw

    async def revoke_share(self, actor_id: str, share_id: str) -> None:
        async with self._uow() as uow:
            record = await uow.shares.get(share_id)
            if record is None:
                raise NotFound(object_id=share_id)
            project = await uow.projects.get(record["project_id"])
            if project is None or project.owner_id != actor_id:
                raise NotFound(object_id=share_id)
            await uow.shares.revoke(share_id)
            await uow.conversations.revoke_sessions_for_share(share_id)
            await uow.experience_sessions.revoke_for_share(share_id)
            await uow.commit()

    async def resolve_share(self, raw_token: str) -> dict:
        """Public entry point for share-scoped reads. Every request re-validates."""
        token_hash = hash_share_token(raw_token)
        async with self._uow() as uow:
            record = await uow.shares.find_by_token_hash(token_hash)
            if record is None or not verify_share_token(raw_token, record["token_hash"]):
                raise NotFound(code="SHARE_NOT_FOUND", message="分享不存在或已失效。")
            revoked = _aware(record["revoked_at"])
            expires = _aware(record["expires_at"])
            if revoked is not None or expires is None or expires <= _now() or not record["license_ack"]:
                raise NotFound(code="SHARE_NOT_FOUND", message="分享不存在或已失效。")
            version = await uow.versions.get(record["version_id"])
            if version is None:
                raise NotFound(code="SHARE_NOT_FOUND", message="分享不存在或已失效。")
            return {"share": record, "version": version}

    async def create_experience_session(self, raw_token: str, actor_id: str) -> dict:
        resolved = await self.resolve_share(raw_token)
        share = resolved["share"]
        version = resolved["version"]
        session_id = new_id()
        async with self._uow() as uow:
            await uow.experience_sessions.add(
                session_id=session_id,
                share_id=share["id"],
                version_id=version["id"],
                project_id=share["project_id"],
                token_hash=hash_share_token(raw_token),
                expires_at=_aware(share["expires_at"]) or _now(),
            )
            await uow.commit()
        return {
            "session_id": session_id,
            "version_id": version["id"],
            "expires_at": _aware(share["expires_at"]).isoformat() if _aware(share["expires_at"]) else None,
        }

    async def export_bundle(self, actor_id: str, version_id: str, *, mode: str) -> dict:
        async with self._uow() as uow:
            version = await self._owned_version(uow, actor_id, version_id)
            if mode not in ("draft", "formal"):
                raise ValidationFailure("INVALID_EXPORT_MODE", "导出模式必须是 draft 或 formal。")
            reports = await uow.reviews.reports_for(version_id)
            latest = await uow.reviews.latest_for(version_id)
            technical = reports[0]["status"] if reports else "not_run"
            content = latest["decision"] if latest else "pending"
            if mode == "formal":
                assert_can_go_stable(
                    technical,
                    "approved" if content == "approved" else content,
                    hash_matches=bool(reports) and reports[0]["spec_hash"] == version["spec_hash"],
                    license_ok=True,
                )
            bundle = {
                "mode": mode,
                "version_id": version_id,
                "spec": version["spec"],
                "dialogue_profile": version["dialogue_profile"],
                "spec_hash": version["spec_hash"],
                "manifest_hash": version["manifest_hash"],
                "pending_review": mode == "draft",
                "has_realtime_ai": False if mode == "draft" else True,
                "notice": "离线资料版不含实时 AI 对话；在线完整版才提供 AI 导览。",
            }
            bundle["bundle_hash"] = canonical_sha256(bundle)
            return bundle
