"""Test providers that derive scripted content from the prompt.

The real database generates random span UUIDs, so a purely static script cannot
reference them. These providers read the ids the orchestration actually sent and
answer with them — everything else stays a fixed script. That keeps the
orchestration, schema checks and validator genuinely exercised.
"""
from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator

from server.domain.runs import BudgetLedger, CostStatus
from server.infrastructure.llm.gateway import ProviderUsage
from server.tests import scripted_agents as script

SPAN_PATTERN = re.compile(r'"span_id":\s*"([0-9a-fA-F-]{36})"')


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
        self.stop_reason = "end_turn"


class SpanAwareProvider:
    """Evidence answers cite the span ids present in the prompt."""

    name = "scripted-mock"
    is_mock = True

    def __init__(self, scripted: dict[str, str] | None = None) -> None:
        self._scripted = scripted or script.scripted()
        self.calls: list[dict[str, Any]] = []

    def _evidence_payload(self, prompt: str) -> str:
        span_ids = SPAN_PATTERN.findall(prompt)
        unique = list(dict.fromkeys(span_ids))
        payload = script.evidence_payload()
        claims = payload["claims"]
        # Assign the real ids in fixture order: tool, A<C, B<C.
        for claim, span in zip(claims, unique):
            claim["evidence_span_ids"] = [span]
        return json.dumps(payload, ensure_ascii=False)

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
        self.calls.append({"role": role, "messages": messages})
        if role == "evidence":
            prompt = messages[-1]["content"] if messages else ""
            return _Response(self._evidence_payload(prompt), len(self.calls))
        if role == "guide":
            span_id = SPAN_PATTERN.search(system)
            return _Response(
                json.dumps(
                    {
                        "answer": "按当前版本的公开资料，这一步的顺序来自材料写明的先后关系。",
                        "citation_span_ids": [span_id.group(1)] if span_id else [],
                        "answerability": "answered" if span_id else "unknown",
                        "suggested_actions": [
                            {"kind": "open_source_card", "label": "查看原文", "scene_id": None, "claim_id": None, "level": None}
                        ],
                    },
                    ensure_ascii=False,
                ),
                len(self.calls),
            )
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
