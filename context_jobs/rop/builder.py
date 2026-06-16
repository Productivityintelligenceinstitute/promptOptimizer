"""Run Output Package builder."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from context_jobs.gateway.budget_tracker import BudgetTracker
from context_jobs.gateway.guardrail_gateway import GatewayToolExecutor
from context_jobs.providers.base import ProviderResponse
from context_jobs.validation.engine import ValidationSummary
from schemas.context_jobs_model import ContextJobModel, JobRunModel


RESULT_TYPE_MAP = {
    "standard": "text_output",
    "analysis": "structured_summary",
    "research": "citation_backed_answer",
    "generation": "formatted_prompt",
    "decision": "decision_memo",
    "extraction": "extracted_fields",
    "review": "recommendation",
    "monitoring": "checklist",
}

NEXT_ACTION_MAP = {
    "completed": ("use_result", "Result is ready to use"),
    "completed_with_warnings": ("review_result", "Review result before using"),
    "needs_repair": ("repair_and_rerun", "Fix validation issues and re-run"),
    "needs_human_review": ("request_approval", "Request approval to proceed"),
    "blocked_by_policy": ("escalate", "Escalate for policy review"),
    "failed": ("retry_later", "Retry when issue is resolved"),
}


def determine_terminal_state(rop_status: str) -> tuple[str, str]:
    mapping = {
        "completed": ("completed", "accepted"),
        "completed_with_warnings": ("completed", "accepted_with_warnings"),
        "needs_repair": ("repair", "needs_review"),
        "needs_human_review": ("escalated", "needs_review"),
        "blocked_by_policy": ("escalated", "escalated"),
        "failed": ("failed", "error"),
    }
    return mapping.get(rop_status, ("failed", "error"))


def build_run_output_package(
    run: JobRunModel,
    job: ContextJobModel,
    validation_summary: ValidationSummary,
    source_traces: list[dict[str, Any]],
    tool_executor: GatewayToolExecutor,
    budget_tracker: BudgetTracker,
    response: ProviderResponse,
    started_at: datetime,
    ended_at: datetime,
    ) -> dict[str, Any]:
    status = validation_summary.status
    next_type, next_label = NEXT_ACTION_MAP.get(status, ("retry_later", "Retry"))
    grounded_mode = bool(source_traces) or bool(run.tool_events and any(
        e.get("toolName") in {"web-search", "doc-reader"} and e.get("status") == "success"
        for e in (run.tool_events or [])
    ))

    warnings = []
    for trace in source_traces:
        for code in trace.get("warnings") or []:
            warnings.append(
                {
                    "code": code,
                    "severity": "low",
                    "message": f"Source {trace.get('sourceName')} flagged as {code}",
                    "relatedStep": "retrieving",
                    "suggestedAction": "Review source quality",
                }
            )

    exceptions = []
    if status == "blocked_by_policy":
        exceptions.append(
            {
                "code": "POLICY_BLOCK",
                "severity": "critical",
                "message": validation_summary.repair_reason or "Blocking policy validation failed",
                "relatedStep": "validating",
                "suggestedAction": "Escalate for policy review",
            }
        )
    elif status == "needs_repair":
        exceptions.append(
            {
                "code": "VALIDATION_FAILURE",
                "severity": "high",
                "message": validation_summary.repair_reason or "Validation failed",
                "relatedStep": "validating",
                "suggestedAction": "Repair and re-run",
            }
        )

    return {
        "status": status,
        "primaryResult": {
            "resultType": RESULT_TYPE_MAP.get(job.workflow_type or "standard", "text_output"),
            "title": f"{job.name} — Run Result",
            "content": response.content or "",
        },
        "validationSummary": {
            "overallDecision": validation_summary.overall_decision,
            "confidenceLevel": validation_summary.confidence_level,
            "checks": validation_summary.checks,
            "repairReason": validation_summary.repair_reason,
        },
        "sourceSummary": {
            "groundedMode": grounded_mode,
            "sourcesUsed": [
                {
                    "sourceId": st.get("sourceId"),
                    "title": st.get("sourceName"),
                    "sourceType": st.get("sourceType"),
                    "freshness": st.get("freshnessStatus"),
                    "evidenceStrength": st.get("evidenceStrength"),
                    "trustLevel": st.get("trustLevel"),
                }
                for st in source_traces
            ],
            "overallEvidenceStrength": "sufficient" if grounded_mode else "unavailable",
        },
        "warnings": warnings,
        "exceptions": exceptions,
        "nextAction": {"type": next_type, "label": next_label},
        "traceSummary": {
            "stages": [log.get("step") for log in (run.step_logs or []) if isinstance(log, dict)],
            "toolEvents": tool_executor.total_calls,
            "retrievalEvents": len(run.retrieval_events or []),
            "repairCycles": 0,
            "replayAvailable": True,
        },
        "memoryStateChanges": {
            "updated": bool(
                job.memory_config
                and any(
                    job.memory_config.get(k)
                    for k in ("sessionMemory", "projectMemory", "userProfileMemory")
                )
            ),
            "changes": [],
        },
        "costTimeSummary": {
            "startedAt": started_at.isoformat(),
            "endedAt": ended_at.isoformat(),
            "runtimeSeconds": round((ended_at - started_at).total_seconds(), 2),
            "estimatedCost": f"${budget_tracker.cost_usd:.4f}",
            "modelUsageSummary": f"{response.model}: {response.input_tokens}in/{response.output_tokens}out",
            "toolUsageCount": tool_executor.total_calls,
            "retrievalUsageCount": len(run.retrieval_events or []),
        },
        "auditMetadata": {
            "runId": str(run.id),
            "jobId": str(job.id),
            "jobVersion": job.version,
            "workspaceId": "default",
            "actor": job.owner,
            "environment": os.environ.get("ENVIRONMENT", "development"),
            "approvalState": "pending" if job.approval_required else "not_required",
            "policyProfile": job.policy_profile,
            "executionMode": getattr(job, "execution_mode", "single_agent"),
        },
        "artifacts": list(getattr(tool_executor, "artifacts", []) or []),
    }
