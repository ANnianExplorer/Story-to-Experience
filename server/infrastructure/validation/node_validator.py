"""TypeScript validator adapter: controlled JSON over stdin/stdout (ADR-0004).

The Node process receives only data (no commands, paths or URLs) and the service
validates the returned JSON shape before trusting it. A non-zero exit or a
malformed response is a hard failure, never a silent "passed".
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any, Sequence

from server.domain.shared.errors import ValidationFailure

VALIDATOR_PROTOCOL = "1.0.0"
DEFAULT_TIMEOUT_SECONDS = 90


class NodeValidator:
    def __init__(
        self,
        *,
        package_root: str | Path,
        node_binary: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._package_root = Path(package_root)
        self._script = self._package_root / "bin" / "validate.ts"
        self._node = node_binary or shutil.which("node") or "node"
        self._timeout = timeout

    @property
    def script_exists(self) -> bool:
        return self._script.is_file()

    async def validate(
        self,
        spec: dict[str, Any],
        *,
        evidence_span_ids: Sequence[str],
        spec_hash: str,
        semantic_hash: str,
        state_limit: int | None = None,
    ) -> dict[str, Any]:
        if not self.script_exists:
            raise ValidationFailure(
                "VALIDATOR_UNAVAILABLE",
                "未找到 TypeScript 校验器入口，无法进行程序检查。",
                {"path": str(self._script)},
            )
        request: dict[str, Any] = {
            "protocol_version": VALIDATOR_PROTOCOL,
            "spec": spec,
            "evidence_span_ids": list(evidence_span_ids),
            "spec_hash": spec_hash,
            "semantic_hash": semantic_hash,
        }
        if state_limit is not None:
            request["state_limit"] = state_limit
        process = await asyncio.create_subprocess_exec(
            self._node,
            str(self._script),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._package_root),
            env={
                "PATH": os.environ.get("PATH", ""),
                "NODE_OPTIONS": "--no-warnings",
            },
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(json.dumps(request, ensure_ascii=False).encode("utf-8")),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise ValidationFailure("VALIDATOR_TIMEOUT", "程序检查超时，结果未知。")
        try:
            payload = json.loads(stdout.decode("utf-8") or "{}")
        except ValueError as exc:
            raise ValidationFailure(
                "VALIDATOR_PROTOCOL_ERROR",
                "校验器返回了非 JSON 结果。",
                {"stderr": stderr.decode("utf-8", "replace")[:300]},
            ) from exc
        if "error" in payload:
            raise ValidationFailure(
                "VALIDATOR_REJECTED",
                str(payload["error"].get("message", "校验器拒绝请求。")),
                {"code": payload["error"].get("code")},
            )
        report = payload.get("report")
        if not isinstance(report, dict) or report.get("status") not in {"passed", "failed", "inconclusive"}:
            raise ValidationFailure("VALIDATOR_PROTOCOL_ERROR", "校验器报告结构不符合协议。")
        if process.returncode not in (0, None):
            raise ValidationFailure(
                "VALIDATOR_PROTOCOL_ERROR",
                "校验器异常退出。",
                {"exit": process.returncode, "stderr": stderr.decode("utf-8", "replace")[:300]},
            )
        return report
