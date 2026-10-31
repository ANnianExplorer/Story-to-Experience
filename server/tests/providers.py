"""Mock model provider with scripted, role-specific responses.

Unlike ``server.infrastructure.llm.gateway.MockProvider`` this one returns real
structured payloads so the orchestration, JSON-schema validation, engine and
validator all run for real. Every response records ``mock=True``.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from server.domain.run import BudgetLedger, CostStatus
from server.infrastructure.llm.gateway import ProviderUsage


class _Response:
    def __init__(self, text: str, index: int) -> None:
        self.text = text
        self.provider = "scripted-mock"
        self.model = "scripted-mock"
        self.provider_request_id = f"mock-{index}"
        self.usage = ProviderUsage(input_tokens=120, output_tokens=240)
        self.cost_status = CostStatus.UNKNOWN
        self.cost_micros = None
        self.currency = "CNY"


class ScriptedProvider:
    """Explicit simulated provider for tests only."""

    name = "scripted-mock"
    is_mock = True

    def __init__(self, scripted: dict[str, str]) -> None:
        self._scripted = scripted
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
    ) -> _Response:
        budget.reserve_call(1)
        budget.settle_call(1)
        self.calls.append({"role": role, "system_chars": len(system), "messages": messages})
        if role not in self._scripted:
            raise KeyError(f"no scripted response for role {role}")
        return _Response(self._scripted[role], len(self.calls))

    async def stream(
        self,
        *,
        role: str,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        budget: BudgetLedger,
    ) -> AsyncIterator[str]:
        response = await self.complete(
            role=role, system=system, messages=messages, max_tokens=max_tokens, budget=budget
        )
        for char in response.text:
            yield char
