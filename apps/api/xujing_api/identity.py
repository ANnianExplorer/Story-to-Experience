"""Authentication port and local development adapter.

``DevIdentity`` accepts the ``X-Actor-Id`` header but only when the app was
started in development mode on a loopback address. It is explicitly *not* a
production authentication mechanism.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from server.domain.errors import Unauthorized

DEV_HEADER = "x-actor-id"
DEFAULT_DEV_ACTOR = "00000000-0000-4000-8000-000000000001"


@dataclass(frozen=True, slots=True)
class Actor:
    id: str
    display_name: str = ""
    kind: str = "human"


class DevIdentity:
    """Development-only identity: header value is a UUID supplied by the caller."""

    def __init__(self, *, enabled: bool) -> None:
        self.enabled = enabled

    async def actor_from_request(self, request: Request) -> Actor:
        if not self.enabled:
            raise Unauthorized("未配置身份提供方。")
        raw = request.headers.get(DEV_HEADER, DEFAULT_DEV_ACTOR).strip()
        if not raw:
            raise Unauthorized("缺少开发身份头。")
        try:
            from uuid import UUID

            actor_id = str(UUID(raw))
        except ValueError as exc:
            raise Unauthorized("开发身份必须是 UUID。") from exc
        return Actor(id=actor_id, display_name="开发用户", kind="human")
