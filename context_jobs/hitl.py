"""Human-in-the-loop: risky tool approval and memory confirmation."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

import context_jobs.audit as cj_audit
from schemas.context_jobs_model import ContextJobModel, JobRunModel

APPROVAL_TIMEOUT_SECONDS = 1800  # 30 minutes
POLL_INTERVAL_SECONDS = 2
WAITING_ON_APPROVAL_MESSAGE = "I'm waiting on approval."


def _pending_approval_items(pending: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [p for p in (pending or []) if p.get("status") == "pending"]


def waiting_message_for_tools(pending: list[dict[str, Any]] | None) -> str:
    pending_items = _pending_approval_items(pending)
    if not pending_items:
        return WAITING_ON_APPROVAL_MESSAGE
    tools = [p.get("toolName") or p.get("toolId") or "tool" for p in pending_items]
    if len(tools) == 1:
        return f"I'm waiting on approval for {tools[0]}."
    return f"I'm waiting on approval for {', '.join(tools)}."


def summarize_pending_approvals(pending: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Expose which tool is waiting without leaking arguments or partial run output."""
    return [
        {
            "id": item.get("id"),
            "toolId": item.get("toolId"),
            "toolName": item.get("toolName"),
            "reason": item.get("reason"),
            "status": item.get("status"),
            "requestedAt": item.get("requestedAt"),
        }
        for item in _pending_approval_items(pending)
    ]


def build_waiting_run_output_package(pending: list[dict[str, Any]] | None) -> dict[str, Any]:
    message = waiting_message_for_tools(pending)
    return {
        "status": "awaiting_tool_approval",
        "primaryResult": {
            "resultType": "text_output",
            "title": "Waiting for approval",
            "content": message,
        },
        "pendingApprovals": summarize_pending_approvals(pending),
        "nextAction": {
            "type": "request_approval",
            "label": message,
        },
        "auditMetadata": {
            "approvalState": "pending",
        },
    }

_approval_events: dict[str, threading.Event] = {}
_approval_results: dict[str, bool] = {}
_events_lock = threading.Lock()

INHERENT_WRITE_TOOL_IDS = frozenset({"file-write", "docx-generate", "code-exec"})


def coerce_permission_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def is_read_only_permission(permission: dict[str, Any]) -> bool:
    return coerce_permission_bool(
        permission.get("readOnly", permission.get("read_only"))
    )


def should_skip_hitl(tool_id: str, permission: dict[str, Any]) -> bool:
    """
    Read-only tools (e.g. calculator) skip HITL entirely.

    Inherent write tools (file-write, docx-generate, code-exec) never skip HITL
    based on readOnly — that flag must not block them before human review.
    """
    if tool_id in INHERENT_WRITE_TOOL_IDS:
        return False
    if "readOnly" in permission or "read_only" in permission:
        return is_read_only_permission(permission)
    return True


def should_hard_deny_write(
    tool_id: str,
    permission: dict[str, Any],
    is_write_action: bool,
) -> bool:
    """Hard deny only for non-write tools attempting mutations while readOnly."""
    if tool_id in INHERENT_WRITE_TOOL_IDS:
        return False
    if not is_write_action:
        return False
    if "readOnly" in permission or "read_only" in permission:
        return is_read_only_permission(permission)
    return False


def requires_tool_approval(
    permission: dict[str, Any],
    ai_risk_assessment: bool,
    tool_id: str,
) -> bool:
    """
    Determine if a tool call requires human approval.

    Inherent write tools always pause for human review when enabled.
    Other tools use AI assessment and optional requireApproval.
    """
    if tool_id in INHERENT_WRITE_TOOL_IDS:
        return True
    if ai_risk_assessment:
        return True
    return coerce_permission_bool(
        permission.get("requireApproval", permission.get("require_approval"))
    )


def _risk_reason(tool_id: str, arguments: dict[str, Any]) -> str:
    if tool_id == "code-exec":
        return "Executes arbitrary Python code in a sandbox"
    if tool_id in {"file-write", "docx-generate"}:
        return "Writes files to run artifact storage"
    if tool_id == "delegate-to-agent":
        return "Delegates work to a specialist agent with tool access"
    if tool_id == "api-caller":
        return f"Calls external API with method {arguments.get('method', 'GET')}"
    return "Tool marked as requiring human approval"


def _parse_risk_assessment_response(response_text: str) -> dict[str, Any]:
    text = (response_text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if "```" in text:
            text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


def _assessment_failure_fallback(
    tool_id: str,
    arguments: dict[str, Any],
    error: str,
) -> tuple[bool, str]:
    """If the risk LLM call fails, pause mutating tools instead of silently skipping HITL."""
    reason = f"Risk assessment unavailable; defaulting to human review. ({error[:100]})"
    if tool_id in {"file-write", "docx-generate", "code-exec", "delegate-to-agent"}:
        return True, reason
    if tool_id == "api-caller":
        method = str(arguments.get("method", "GET")).upper()
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            return True, reason
    return False, f"Risk assessment unavailable ({error[:100]})"


async def _call_risk_assessment_llm(
    provider: str,
    model: str,
    api_key: str,
    prompt: str,
) -> str:
    provider_norm = (provider or "openai").lower()

    if provider_norm == "openai":
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            max_tokens=300,
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": "You are a security expert. Respond only with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or ""

    if provider_norm == "anthropic":
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=model,
            max_tokens=300,
            temperature=0.3,
            system="You are a security expert. Respond only with valid JSON.",
            messages=[{"role": "user", "content": prompt}],
        )
        parts = []
        for block in response.content:
            if getattr(block, "text", None):
                parts.append(block.text)
        return "".join(parts)

    if provider_norm == "google":
        import asyncio

        from google import genai
        from google.genai import types

        use_async_client = hasattr(genai, "AsyncClient")
        client = genai.AsyncClient(api_key=api_key) if use_async_client else genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=300,
            system_instruction="You are a security expert. Respond only with valid JSON.",
        )
        if use_async_client:
            response = await client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
        else:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                ),
            )
        return response.text or ""

    raise ValueError(f"Unsupported provider for risk assessment: {provider}")


async def assess_tool_risk_with_ai(
    db: Session,
    tool_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    job: ContextJobModel,
) -> tuple[bool, str]:
    """
    Ask AI whether this specific tool call (id + arguments only) needs human approval.

    Returns: (is_risky: bool, reasoning: str)
    """
    risk_assessment_prompt = f"""Evaluate whether THIS SINGLE tool call needs human approval before it runs.

Tool call under review (judge only this call — ignore any other planned or future steps):
- Tool ID: {tool_id}
- Tool name: {tool_name}
- Arguments: {json.dumps(arguments, indent=2)}

Rules:
- Judge only what this specific call does with these exact arguments.
- Do NOT flag a call because some other tool might run later (e.g. do not flag calculator because a file-write may happen afterward).
- Do NOT use job goals, user requests, or multi-step plans — only this tool invocation.
- Read-only operations (calculations, lookups, reads) are NOT risky.
- Flag only if THIS call itself performs writes, external mutations, code execution, delegation, or similar high-impact effects.

Respond in JSON format:
{{
  "is_risky": boolean,
  "risk_level": "low|medium|high|critical",
  "reasoning": "brief explanation about THIS call only",
  "requires_approval": boolean
}}

Set requires_approval to true only when THIS specific call needs human review.
IMPORTANT: Return ONLY valid JSON, no markdown, no extra text."""

    try:
        from context_jobs.provider_key_services import resolve_llm_api_key
        from context_jobs.providers.registry import get_default_model

        provider = (job.execution_provider or "openai").lower()
        model = job.execution_model or get_default_model(provider)
        _, api_key = resolve_llm_api_key(db, job.owner, job.llm_key_id, provider)

        response_text = await _call_risk_assessment_llm(
            provider=provider,
            model=model,
            api_key=api_key,
            prompt=risk_assessment_prompt,
        )
        assessment = _parse_risk_assessment_response(response_text)
        is_risky = bool(
            assessment.get("requires_approval", assessment.get("is_risky", False))
        )
        reasoning = str(assessment.get("reasoning") or "AI-based risk assessment")
        return is_risky, reasoning
    except json.JSONDecodeError as exc:
        return _assessment_failure_fallback(
            tool_id,
            arguments,
            f"parse error: {exc}",
        )
    except Exception as exc:
        return _assessment_failure_fallback(tool_id, arguments, str(exc))


def wait_for_tool_approval(
    db: Session,
    run: JobRunModel,
    job: ContextJobModel,
    tool_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    risk_reason: Optional[str] = None,
) -> bool:
    """Block until human approves/denies a risky tool call. Returns True if approved."""
    approval_id = str(uuid.uuid4())
    record = {
        "id": approval_id,
        "toolId": tool_id,
        "toolName": tool_name,
        "arguments": arguments,
        "reason": risk_reason or _risk_reason(tool_id, arguments),
        "status": "pending",
        "requestedAt": datetime.now(timezone.utc).isoformat(),
    }
    pending = list(getattr(run, "pending_approvals", None) or [])
    pending.append(record)
    run.pending_approvals = pending
    run.state = "awaiting_tool_approval"
    run.output_text = waiting_message_for_tools(pending)
    run.run_output_package = build_waiting_run_output_package(pending)
    db.add(run)
    db.commit()

    event = threading.Event()
    with _events_lock:
        _approval_events[approval_id] = event

    cj_audit.write_audit_event(
        db,
        event_type="tool.approval_requested",
        entity_type="run",
        entity_id=str(run.id),
        actor=job.owner,
        metadata={"approvalId": approval_id, "toolId": tool_id, "toolName": tool_name},
    )

    deadline = time.time() + APPROVAL_TIMEOUT_SECONDS
    approved = False
    while time.time() < deadline:
        with _events_lock:
            if approval_id in _approval_results:
                approved = _approval_results.pop(approval_id)
                break
        # Also check DB for decisions made via API on another process
        db.refresh(run)
        for item in run.pending_approvals or []:
            if item.get("id") == approval_id and item.get("status") in {"approved", "denied"}:
                approved = item.get("status") == "approved"
                with _events_lock:
                    _approval_results.pop(approval_id, None)
                break
        else:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        break

    with _events_lock:
        _approval_events.pop(approval_id, None)

    if not approved:
        _update_approval_status(db, run, approval_id, "denied", "timeout", job.owner)
    return approved


def resolve_tool_approval(
    db: Session,
    run: JobRunModel,
    approval_id: str,
    decision: str,
    actor: str,
    notes: Optional[str] = None,
) -> JobRunModel:
    decision_norm = str(decision or "").strip().lower()
    if decision_norm not in {"approved", "denied", "approve", "deny"}:
        raise ValueError("decision must be approved or denied")
    approved = decision_norm in {"approved", "approve"}
    status = "approved" if approved else "denied"
    _update_approval_status(db, run, approval_id, status, actor, notes)
    db.refresh(run)

    with _events_lock:
        event = _approval_events.get(approval_id)
        _approval_results[approval_id] = approved
        if event:
            event.set()

    cj_audit.write_audit_event(
        db,
        event_type="tool.approval_decided",
        entity_type="run",
        entity_id=str(run.id),
        actor=actor,
        metadata={"approvalId": approval_id, "decision": status, "notes": notes},
    )
    if run.state == "awaiting_tool_approval":
        pending = [p for p in (run.pending_approvals or []) if p.get("status") == "pending"]
        if not pending:
            run.state = "executing"
            run.output_text = None
            run.run_output_package = None
            db.add(run)
            db.commit()
    db.refresh(run)
    return run


def _update_approval_status(
    db: Session,
    run: JobRunModel,
    approval_id: str,
    status: str,
    decided_by: str,
    notes: Optional[str],
) -> None:
    db.refresh(run)
    updated_pending: list[dict[str, Any]] = []
    found = False
    for item in run.pending_approvals or []:
        entry = dict(item)
        if entry.get("id") == approval_id:
            entry["status"] = status
            entry["decidedBy"] = decided_by
            entry["decidedAt"] = datetime.now(timezone.utc).isoformat()
            if notes:
                entry["notes"] = notes
            found = True
        updated_pending.append(entry)
    if not found:
        raise ValueError(f"Approval {approval_id} not found for this run")

    run.pending_approvals = updated_pending
    flag_modified(run, "pending_approvals")
    db.add(run)
    db.commit()
    db.refresh(run)


def list_pending_tool_approvals(run: JobRunModel) -> list[dict[str, Any]]:
    return [p for p in (run.pending_approvals or []) if p.get("status") == "pending"]


def memory_requires_confirmation(job: ContextJobModel) -> bool:
    mc = job.memory_config or {}
    return bool(mc.get("requireConfirmation") or mc.get("require_confirmation") or job.approval_required)


def set_pending_memory_changes(
    db: Session,
    run: JobRunModel,
    changes: list[dict[str, Any]],
    facts: list[dict[str, Any]],
) -> None:
    run.pending_memory_changes = {"changes": changes, "facts": facts}
    run.state = "awaiting_memory_approval"
    db.add(run)
    db.commit()


def confirm_memory_changes(
    db: Session,
    run: JobRunModel,
    job: ContextJobModel,
    approved: bool,
    actor: str,
) -> list[dict[str, Any]]:
    pending = dict(run.pending_memory_changes or {})
    if not pending:
        raise ValueError("No pending memory changes for this run")
    changes: list[dict[str, Any]] = []
    if approved:
        from datetime import timedelta

        from schemas.run_memory_entry_model import RunMemoryEntryModel

        memory_config = job.memory_config or {}
        retention_days = int(memory_config.get("retentionDays") or 30)
        expires_at = datetime.now(timezone.utc) + timedelta(days=retention_days)
        for fact in pending.get("facts") or []:
            entry = RunMemoryEntryModel(
                owner=job.owner,
                job_id=job.id if fact.get("memory_type") != "user_profile" else None,
                memory_type=fact.get("memory_type", "session"),
                key=fact["key"],
                value=fact["value"],
                source_run_id=run.id,
                expires_at=expires_at,
            )
            db.add(entry)
            changes.append(
                {
                    "type": "memory_write",
                    "destination": fact.get("memory_type", "session"),
                    "reason": f"Confirmed from run {run.id}",
                }
            )
        db.commit()
        cj_audit.write_audit_event(
            db,
            event_type="memory.written",
            entity_type="run",
            entity_id=str(run.id),
            actor=actor,
            metadata={"writeCount": len(changes), "confirmed": True},
        )
    else:
        cj_audit.write_audit_event(
            db,
            event_type="memory.rejected",
            entity_type="run",
            entity_id=str(run.id),
            actor=actor,
            metadata={"factCount": len(pending.get("facts") or [])},
        )
    run.pending_memory_changes = None
    if run.state == "awaiting_memory_approval":
        run.state = "completed"
    # Update outcome to reflect memory approval status
    if approved:
        run.outcome = "accepted"
    else:
        run.outcome = "needs_review"  # Keep as needs_review if rejected
    db.add(run)
    db.commit()
    return changes
