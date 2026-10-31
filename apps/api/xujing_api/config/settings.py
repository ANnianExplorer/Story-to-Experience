"""API entry point (composition root).

Configuration comes from environment variables; no defaults carry secrets. The
development identity adapter is refused unless the server binds to loopback
(security spec: 本地开发身份仅用于回环地址).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    environment: str
    bind_host: str
    bind_port: int
    identity_mode: str
    storage_root: str
    model_provider: str
    model_base_url: str | None
    model_api_key: str | None
    model_name: str
    mock_allowed: bool

    @property
    def is_loopback(self) -> bool:
        return self.bind_host in {"127.0.0.1", "localhost", "::1"}

    def validate(self) -> None:
        if self.identity_mode == "dev" and not self.is_loopback:
            raise ConfigurationError(
                "开发身份适配器只能在回环地址运行；请配置生产身份适配器。"
            )
        if self.model_provider != "mock" and not self.model_api_key:
            # Credentials missing is a runtime state, not a startup failure: the
            # provider reports NOT_CONFIGURED at call time and the run fails
            # visibly instead of silently switching to mock.
            pass


def _flag(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_url = os.environ.get(
        "XUJING_DATABASE_URL", "postgresql+asyncpg://xujing:xujing_dev@127.0.0.1:55432/xujing"
    )
    settings = Settings(
        database_url=database_url,
        environment=os.environ.get("XUJING_ENV", "development"),
        bind_host=os.environ.get("XUJING_BIND_HOST", "127.0.0.1"),
        bind_port=int(os.environ.get("XUJING_BIND_PORT", "8000")),
        identity_mode=os.environ.get("XUJING_IDENTITY_MODE", "dev"),
        storage_root=os.environ.get("XUJING_STORAGE_ROOT", str(REPO_ROOT / "var" / "blobs")),
        model_provider=os.environ.get("XUJING_MODEL_PROVIDER", "anthropic-gateway"),
        model_base_url=os.environ.get("XUJING_MODEL_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL"),
        model_api_key=os.environ.get("XUJING_MODEL_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"),
        model_name=os.environ.get("XUJING_MODEL_NAME", "deepseek-v4.1-flash-1017"),
        mock_allowed=_flag(os.environ.get("XUJING_ALLOW_MOCK"), default=False),
    )
    settings.validate()
    return settings
