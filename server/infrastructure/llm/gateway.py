"""Anthropic-compatible model gateway adapter (L4).

The gateway speaks the Messages API (``POST {base}/v1/messages``). Credentials
come from the composition root only; they never reach logs, traces, browser
code or exported bundles.

Budget: every call reserves one slot from the run-wide (or conversation-wide)
ledger *before* the request leaves the process, then settles it afterwards. A
request whose outcome is unknown still settles — an unknown cost is recorded as
``unknown``, never as zero.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx

from server.domain.shared.errors import NotConfigured, DomainError
from server.domain.runs import BudgetLedger, CostStatus

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_TIMEOUT = 120.0


@dataclass(slots=True)
class ProviderUsage:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0


@dataclass(slots=True)
class GatewayResponse:
    text: str
    provider_request_id: str
    model: str
    usage: ProviderUsage
    cost_status: CostStatus
    cost_micros: int | None
    currency: str | None
    stop_reason: str | None = None
    raw_content: list[dict[str, Any]] = field(default_factory=list)


class ProviderError(DomainError):
    def __init__(self, message: str, *, retryable: bool, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="PROVIDER_ERROR",
            message=message,
            status=503 if retryable else 422,
            retryable=retryable,
            details=details or {},
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnthropicGatewayProvider:
    """Real provider adapter. Reports missing credentials as NOT_CONFIGURED."""

    name = "anthropic-gateway"

    def __init__(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        model: str,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
        price_input_micros_per_token: int | None = None,
        price_output_micros_per_token: int | None = None,
        currency: str = "CNY",
        disable_thinking: bool = True,
    ) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._transport = transport
        self._price_in = price_input_micros_per_token
        self._price_out = price_output_micros_per_token
        self._currency = currency
        # The gateway bills reasoning tokens inside max_tokens. For structured
        # JSON artifacts the hidden reasoning only causes truncation, so it is
        # disabled by default and can be re-enabled per deployment.
        self._disable_thinking = disable_thinking

    @property
    def configured(self) -> bool:
        return bool(self._base_url and self._api_key and self._model)

    def _headers(self) -> dict[str, str]:
        assert self._api_key is not None
        return {
            "x-api-key": self._api_key,
            "authorization": f"Bearer {self._api_key}",
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _cost(self, usage: ProviderUsage) -> tuple[CostStatus, int | None, str | None]:
        if self._price_in is None or self._price_out is None:
            return CostStatus.UNKNOWN, None, self._currency
        micros = usage.input_tokens * self._price_in + usage.output_tokens * self._price_out
        return CostStatus.ESTIMATED, micros, self._currency

    def _payload(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        stream: bool,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if stream:
            body["stream"] = True
        if self._disable_thinking:
            body["thinking"] = {"type": "disabled"}
        return body

    async def complete(
        self,
        *,
        role: str,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        budget: BudgetLedger,
        json_schema: dict[str, Any] | None = None,
        temperature: float | None = None,
    ) -> GatewayResponse:
        if not self.configured:
            raise NotConfigured("未配置模型凭据：XUJING_MODEL_BASE_URL / XUJING_MODEL_API_KEY。")
        budget.reserve_call(1)
        body = self._payload(system=system, messages=messages, max_tokens=max_tokens, stream=False)
        if json_schema is not None:
            body["system"] = system + (
                "\n\n输出要求：只输出一个符合以下 JSON Schema 的 JSON 对象，不要输出解释、Markdown 围栏或额外文字。\n"
                + json.dumps(json_schema, ensure_ascii=False, sort_keys=True)
            )
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(f"{self._base_url}/v1/messages", headers=self._headers(), json=body)
        except httpx.TimeoutException as exc:
            # The provider may still have billed; keep the slot settled as unknown.
            budget.settle_call(1)
            raise ProviderError("模型服务超时；用量未知。", retryable=True, details={"role": role}) from exc
        except httpx.HTTPError as exc:
            budget.release_call(1)
            raise ProviderError("无法连接模型服务。", retryable=True, details={"role": role}) from exc

        if response.status_code == 429 or response.status_code >= 500:
            budget.settle_call(1)
            raise ProviderError(
                "模型服务暂时不可用或限流。",
                retryable=True,
                details={"status": response.status_code, "body": response.text[:300]},
            )
        if response.status_code >= 400:
            budget.release_call(1)
            raise ProviderError(
                "模型请求被拒绝。",
                retryable=False,
                details={"status": response.status_code, "body": response.text[:300]},
            )

        budget.settle_call(1)
        payload = response.json()
        text = "".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        usage_payload = payload.get("usage") or {}
        usage = ProviderUsage(
            input_tokens=int(usage_payload.get("input_tokens") or 0),
            output_tokens=int(usage_payload.get("output_tokens") or 0),
            cache_read_tokens=int(usage_payload.get("cache_read_input_tokens") or 0),
        )
        cost_status, cost_micros, currency = self._cost(usage)
        return GatewayResponse(
            text=text,
            provider_request_id=str(payload.get("id") or ""),
            model=str(payload.get("model") or self._model),
            usage=usage,
            cost_status=cost_status,
            cost_micros=cost_micros,
            currency=currency,
            stop_reason=payload.get("stop_reason"),
            raw_content=list(payload.get("content") or []),
        )

    async def stream(
        self,
        *,
        role: str,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        budget: BudgetLedger,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Yield text deltas. Raises ProviderError before the first token on failure."""
        if not self.configured:
            raise NotConfigured("未配置模型凭据：XUJING_MODEL_BASE_URL / XUJING_MODEL_API_KEY。")
        budget.reserve_call(1)
        body = self._payload(system=system, messages=messages, max_tokens=max_tokens, stream=True)
        settled = False
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                async with client.stream(
                    "POST", f"{self._base_url}/v1/messages", headers=self._headers(), json=body
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        budget.release_call(1)
                        settled = True
                        raise ProviderError(
                            "模型流式请求被拒绝。",
                            retryable=response.status_code == 429 or response.status_code >= 500,
                            details={"status": response.status_code, "body": response.text[:300]},
                        )
                    budget.settle_call(1)
                    settled = True
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            event = json.loads(data)
                        except ValueError:
                            continue
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta") or {}
                            if delta.get("type") == "text_delta" and delta.get("text"):
                                yield str(delta["text"])
                        elif event.get("type") == "error":
                            raise ProviderError(
                                "模型流式返回错误。",
                                retryable=False,
                                details={"message": str((event.get("error") or {}).get("message", ""))[:300]},
                            )
        finally:
            if not settled:
                # Never leave a reservation dangling if the stream aborted early.
                try:
                    budget.release_call(1)
                except Exception:  # pragma: no cover - defensive only
                    pass


class MockProvider:
    """Explicit development provider. Every recorded call is marked ``mock``.

    It is never selected automatically: the composition root must opt in with
    XUJING_MODEL_PROVIDER=mock and results must be labelled as simulated.
    """

    name = "mock"
    is_mock = True

    def __init__(self, *, scripted: dict[str, str] | None = None) -> None:
        self._scripted = scripted or {}
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        role: str,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        budget: BudgetLedger,
        json_schema: dict[str, Any] | None = None,
        temperature: float | None = None,
    ) -> GatewayResponse:
        budget.reserve_call(1)
        budget.settle_call(1)
        self.calls.append({"role": role, "messages": len(messages), "mock": True})
        text = self._scripted.get(role, json.dumps({"mock": True, "role": role}, ensure_ascii=False))
        return GatewayResponse(
            text=text,
            provider_request_id=f"mock-{len(self.calls)}",
            model="mock",
            usage=ProviderUsage(input_tokens=0, output_tokens=0),
            cost_status=CostStatus.ACTUAL,
            cost_micros=0,
            currency="CNY",
        )

    async def stream(
        self,
        *,
        role: str,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        budget: BudgetLedger,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        response = await self.complete(
            role=role, system=system, messages=messages, max_tokens=max_tokens, budget=budget
        )
        for chunk in response.text:
            yield chunk
