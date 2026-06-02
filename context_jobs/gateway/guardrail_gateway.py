"""Guardrail gateway for provider tool calls."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from context_jobs.gateway.budget_tracker import BudgetTracker
from context_jobs.provider_key_services import resolve_tool_api_key
from context_jobs.providers.base import ToolCall, ToolResult
from context_jobs.tools import get_tool_implementation
from schemas.context_jobs_model import ContextJobModel, JobRunModel
from schemas.tool_execution_model import ToolExecutionModel


_LOCALHOST_PATTERN = re.compile(r"^(localhost|127\.0\.0\.1|0\.0\.0\.0)$", re.I)


@dataclass
class GatewayToolExecutor:
    job: ContextJobModel
    run: JobRunModel
    budget_tracker: BudgetTracker
    db: Session
    executed_calls: list[dict[str, Any]] = field(default_factory=list)
    turns: int = 0

    @property
    def total_calls(self) -> int:
        return len(self.executed_calls)

    async def __call__(self, tool_call: ToolCall) -> ToolResult:
        self.turns += 1
        return await self.check_and_execute(tool_call)

    async def check_and_execute(self, tool_call: ToolCall) -> ToolResult:
        if not self._is_tool_allowed(tool_call.tool_id):
            return self._deny(tool_call, "TOOL_NOT_PERMITTED", "Tool is not permitted for this job")

        perm = self._get_permission(tool_call.tool_id)
        if perm.get("readOnly") and self._is_write_action(tool_call):
            return self._deny(tool_call, "WRITE_DENIED", "Tool is read-only for this job")

        if self.budget_tracker.is_exceeded():
            return self._deny(
                tool_call,
                "BUDGET_EXCEEDED",
                f"Budget limit reached: {self.budget_tracker.reason()}",
            )

        sanitized_args, issues = self._sanitize_arguments(tool_call.arguments or {})
        if issues:
            return self._deny(
                tool_call,
                "UNSAFE_ARGUMENTS",
                f"Arguments failed sanitization: {'; '.join(issues)}",
            )

        try:
            tool_impl = get_tool_implementation(tool_call.tool_id)
            tool_api_key = None
            if tool_impl.requires_external_key:
                tool_api_key = resolve_tool_api_key(self.db, self.job.owner, tool_call.tool_id)
            result_text = await tool_impl.execute(sanitized_args, api_key=tool_api_key)
            self.budget_tracker.record_tool_call()
            self._log_execution(tool_call, sanitized_args, result_text, "success", None)
            self.executed_calls.append(
                {
                    "toolName": tool_call.tool_name,
                    "action": "execute",
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return ToolResult(tool_call_id=tool_call.id, content=result_text, is_error=False)
        except Exception as exc:
            self._log_execution(tool_call, sanitized_args, str(exc), "error", None)
            self.executed_calls.append(
                {
                    "toolName": tool_call.tool_name,
                    "action": "execute",
                    "status": "error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"Tool error: {exc}",
                is_error=True,
            )

    def _deny(self, tool_call: ToolCall, code: str, reason: str) -> ToolResult:
        self._log_execution(tool_call, tool_call.arguments or {}, reason, "denied", reason)
        self.executed_calls.append(
            {
                "toolName": tool_call.tool_name,
                "action": "denied",
                "status": "denied",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return ToolResult(tool_call_id=tool_call.id, content=f"{code}: {reason}", is_error=True)

    def _is_tool_allowed(self, tool_id: str) -> bool:
        perms = self.job.tool_permissions or []
        for perm in perms:
            if not isinstance(perm, dict):
                continue
            pid = perm.get("toolId") or perm.get("tool_id")
            if pid == tool_id and perm.get("enabled"):
                return True
        return False

    def _get_permission(self, tool_id: str) -> dict:
        for perm in self.job.tool_permissions or []:
            if isinstance(perm, dict) and (perm.get("toolId") or perm.get("tool_id")) == tool_id:
                return perm
        return {}

    def _is_write_action(self, tool_call: ToolCall) -> bool:
        method = (tool_call.arguments or {}).get("method", "GET")
        return str(method).upper() in {"POST", "PUT", "PATCH", "DELETE"}

    def _sanitize_arguments(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        issues: list[str] = []
        sanitized = dict(arguments)
        for key in ("url", "endpoint"):
            value = sanitized.get(key)
            if not value:
                continue
            from urllib.parse import urlparse

            parsed = urlparse(str(value))
            host = parsed.hostname or ""
            if _LOCALHOST_PATTERN.match(host):
                issues.append("localhost access is not allowed")
            if parsed.scheme not in {"http", "https", ""}:
                issues.append("only http/https URLs are allowed")
        return sanitized, issues

    def _log_execution(
        self,
        tool_call: ToolCall,
        arguments: dict[str, Any],
        result_summary: str,
        status: str,
        denial_reason: str | None,
    ) -> None:
        row = ToolExecutionModel(
            run_id=self.run.id,
            tool_id=tool_call.tool_id,
            tool_name=tool_call.tool_name,
            action="denied" if status == "denied" else "execute",
            status=status,
            arguments=arguments,
            result_summary=(result_summary or "")[:3000],
            denial_reason=denial_reason,
        )
        self.db.add(row)
        self.db.commit()
