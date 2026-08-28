from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

import context_jobs.audit as cj_audit
from context_jobs.agents.catalog import DELEGATE_TOOL_ID
from context_jobs.agents.types import SubAgentDefinition
from context_jobs.assembly.prompt_safety import wrap_tool_result_content
from context_jobs.gateway.budget_tracker import BudgetTracker
from context_jobs.gateway.contract_context import consolidate_contract_analyzer_text
from context_jobs.hitl import (
    assess_tool_risk_with_ai,
    requires_tool_approval,
    should_hard_deny_write,
    should_skip_hitl,
    wait_for_tool_approval,
)
from context_jobs.provider_key_services import resolve_tool_api_key
from context_jobs.text_sanitize import (
    compact_tool_arguments_for_db,
    sanitize_db_text,
    sanitize_for_db,
)
from context_jobs.workspace import check_tool_allowlist
from context_jobs.providers.base import ToolCall, ToolResult
from context_jobs.tools import TOOL_IMPLEMENTATIONS, get_tool_implementation
from schemas.context_jobs_model import ContextJobModel, JobRunModel
from schemas.tool_execution_model import ToolExecutionModel

_WRITE_TOOL_IDS = {"file-write", "docx-generate", "contract-patch", DELEGATE_TOOL_ID}
_RUN_CONTEXT_TOOL_IDS = {"file-write", "docx-generate", "contract-patch"}
GATEWAY_TOOL_ALLOWLIST = frozenset(TOOL_IMPLEMENTATIONS.keys())


_LOCALHOST_PATTERN = re.compile(r"^(localhost|127\.0\.0\.1|0\.0\.0\.0)$", re.I)
_RESULT_SUMMARY_MAX = 50_000
_log = logging.getLogger("context_jobs.gateway.tools")


@dataclass
class GatewayToolExecutor:
    job: ContextJobModel
    run: JobRunModel
    budget_tracker: BudgetTracker
    db: Session
    agent_catalog: dict[str, SubAgentDefinition] = field(default_factory=dict)
    delegate_runner: Any | None = None
    allow_delegation: bool = False
    executed_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    approval_state: str = "not_required"
    turns: int = 0
    retrieved_context: str = ""

    @property
    def total_calls(self) -> int:
        return len(self.executed_calls)

    async def __call__(self, tool_call: ToolCall) -> ToolResult:
        self.turns += 1
        return await self.check_and_execute(tool_call)

    def _record_tool_output(self, tool_call: ToolCall, result_text: str, status: str) -> None:
        """Full tool JSON for validation — independent of DB audit logging."""
        self.tool_outputs.append(
            {
                "toolId": tool_call.tool_id,
                "toolName": tool_call.tool_name,
                "status": status,
                "resultSummary": sanitize_db_text(result_text),
            }
        )

    async def check_and_execute(self, tool_call: ToolCall) -> ToolResult:
        if not self._is_tool_allowed(tool_call.tool_id):
            return self._deny(tool_call, "TOOL_NOT_PERMITTED", "Tool is not permitted for this job")

        perm = self._get_permission(tool_call.tool_id)
        if should_hard_deny_write(
            tool_call.tool_id,
            perm,
            self._is_write_action(tool_call),
        ):
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

        if tool_call.tool_id == "contract-analyzer":
            source = str((sanitized_args or {}).get("source") or "").strip().lower()
            if source == "text" and (self.retrieved_context or "").strip():
                sanitized_args = dict(sanitized_args)
                sanitized_args["value"] = sanitize_db_text(
                    consolidate_contract_analyzer_text(
                        str(sanitized_args.get("value") or ""),
                        self.retrieved_context,
                    )
                )

        if not should_skip_hitl(tool_call.tool_id, perm):
            workflow = (getattr(self.job, "workflow_type", None) or "").lower()
            skip_second_gate = workflow == "contract_amendment"
            ai_is_risky, ai_reasoning = (False, "Amendment follow-up after human approve")
            if not skip_second_gate:
                ai_is_risky, ai_reasoning = await assess_tool_risk_with_ai(
                    self.db,
                    tool_id=tool_call.tool_id,
                    tool_name=tool_call.tool_name,
                    arguments=sanitized_args,
                    job=self.job,
                )

            if not skip_second_gate and requires_tool_approval(
                perm, ai_is_risky, tool_call.tool_id, job=self.job
            ):
                self.approval_state = "pending"
                cj_audit.write_audit_event(
                    self.db,
                    event_type="tool.risk_assessed",
                    entity_type="run",
                    entity_id=str(self.run.id),
                    actor=self.job.owner,
                    metadata={
                        "toolId": tool_call.tool_id,
                        "toolName": tool_call.tool_name,
                        "aiRisky": ai_is_risky,
                        "reasoning": ai_reasoning,
                    },
                )
                self.budget_tracker.pause()
                try:
                    approved = wait_for_tool_approval(
                        self.db,
                        self.run,
                        self.job,
                        tool_call.tool_id,
                        tool_call.tool_name,
                        sanitized_args,
                        risk_reason=ai_reasoning,
                    )
                finally:
                    self.budget_tracker.resume()
                if not approved:
                    self.approval_state = "denied"
                    return self._deny(
                        tool_call,
                        "TOOL_APPROVAL_DENIED",
                        "Human denied or timed out on risky tool execution",
                    )
                if self.approval_state != "denied":
                    self.approval_state = "approved"

        if tool_call.tool_id != DELEGATE_TOOL_ID and tool_call.tool_id not in GATEWAY_TOOL_ALLOWLIST:
            return self._deny(
                tool_call,
                "TOOL_NOT_REGISTERED",
                f"Tool {tool_call.tool_id!r} is not registered for gateway execution",
            )

        try:
            check_tool_allowlist(self.db, self.job, tool_call.tool_id)
        except ValueError as exc:
            return self._deny(tool_call, "TOOL_NOT_ALLOWLISTED", str(exc))

        try:
            if tool_call.tool_id == DELEGATE_TOOL_ID:
                result_text = await self._execute_delegation(sanitized_args)
            else:
                tool_impl = get_tool_implementation(tool_call.tool_id)
                tool_api_key = None
                if tool_impl.requires_external_key:
                    tool_api_key = resolve_tool_api_key(self.db, self.job.owner, tool_call.tool_id)
                if tool_call.tool_id in _RUN_CONTEXT_TOOL_IDS:
                    result_text = await tool_impl.execute(
                        sanitized_args,
                        api_key=tool_api_key,
                        owner=self.job.owner,
                        run_id=str(self.run.id),
                    )
                else:
                    result_text = await tool_impl.execute(sanitized_args, api_key=tool_api_key)
                self._maybe_record_artifact(tool_call.tool_id, sanitized_args, result_text)
            self.budget_tracker.record_tool_call()
            self._record_tool_output(tool_call, result_text, "success")
            self._log_execution(tool_call, sanitized_args, result_text, "success", None)
            self.executed_calls.append(
                {
                    "toolId": tool_call.tool_id,
                    "toolName": tool_call.tool_name,
                    "action": "execute",
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                content=wrap_tool_result_content(result_text),
                is_error=False,
            )
        except Exception as exc:
            error_text = str(exc)
            self._record_tool_output(
                tool_call,
                json.dumps({"error": error_text}, ensure_ascii=False),
                "error",
            )
            self._log_execution(tool_call, sanitized_args, error_text, "error", None)
            self.executed_calls.append(
                {
                    "toolId": tool_call.tool_id,
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
                "toolId": tool_call.tool_id,
                "action": "denied",
                "status": "denied",
                "denialCode": code,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return ToolResult(tool_call_id=tool_call.id, content=f"{code}: {reason}", is_error=True)

    async def _execute_delegation(self, arguments: dict[str, Any]) -> str:
        if not self.allow_delegation or not self.delegate_runner:
            raise ValueError("Agent delegation is not enabled for this run")
        agent_name = str(arguments.get("agent_name", "")).strip()
        task = str(arguments.get("task", "")).strip()
        if not agent_name or not task:
            raise ValueError("agent_name and task are required for delegation")
        return await self.delegate_runner.delegate(agent_name, task, self)

    def _maybe_record_artifact(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        result_text: str,
    ) -> None:
        if tool_id not in _RUN_CONTEXT_TOOL_IDS:
            return
        rel_path = str(arguments.get("path", "")).strip()
        if not rel_path:
            return
        self.artifacts.append(
            {
                "path": rel_path,
                "toolId": tool_id,
                "message": (result_text or "")[:500],
            }
        )

    def _is_tool_allowed(self, tool_id: str) -> bool:
        if tool_id == DELEGATE_TOOL_ID:
            return self.allow_delegation and bool(self.agent_catalog)
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
        if tool_call.tool_id in _WRITE_TOOL_IDS:
            return True
        method = (tool_call.arguments or {}).get("method", "GET")
        return str(method).upper() in {"POST", "PUT", "PATCH", "DELETE"}

    def _sanitize_arguments(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        issues: list[str] = []
        sanitized = sanitize_for_db(dict(arguments))
        url_keys = ["url", "endpoint"]
        if str(sanitized.get("source") or "").strip().lower() == "url":
            url_keys.append("value")
        for key in url_keys:
            value = sanitized.get(key)
            if not value:
                continue
            from urllib.parse import urlparse

            parsed = urlparse(str(value))
            if not parsed.scheme and not parsed.hostname:
                continue
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
        safe_args = compact_tool_arguments_for_db(tool_call.tool_id, arguments)
        safe_summary = sanitize_db_text(result_summary)[:_RESULT_SUMMARY_MAX]
        safe_denial = sanitize_db_text(denial_reason) if denial_reason else None
        try:
            row = ToolExecutionModel(
                run_id=self.run.id,
                tool_id=tool_call.tool_id,
                tool_name=tool_call.tool_name,
                action="denied" if status == "denied" else "execute",
                status=status,
                arguments=safe_args,
                result_summary=safe_summary,
                denial_reason=safe_denial,
            )
            self.db.add(row)
            self.db.commit()
            try:
                cj_audit.write_audit_event(
                    self.db,
                    event_type="tool.executed",
                    entity_type="run",
                    entity_id=str(self.run.id),
                    actor=self.job.owner,
                    metadata={
                        "toolId": tool_call.tool_id,
                        "toolName": tool_call.tool_name,
                        "action": "denied" if status == "denied" else "execute",
                        "status": status,
                        "denialReason": safe_denial,
                        "arguments": safe_args,
                    },
                )
            except Exception as audit_exc:
                self.db.rollback()
                _log.warning(
                    "tool audit event failed for %s on run %s: %s",
                    tool_call.tool_id,
                    self.run.id,
                    audit_exc,
                )
        except Exception as exc:
            self.db.rollback()
            _log.warning(
                "tool execution DB log failed for %s on run %s: %s",
                tool_call.tool_id,
                self.run.id,
                exc,
            )
