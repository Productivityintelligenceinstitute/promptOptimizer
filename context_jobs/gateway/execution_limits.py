"""Resolve per-run execution limits from job config and workflow type."""

from __future__ import annotations

from schemas.context_jobs_model import ContextJobModel

# Defaults when job.budget_settings is empty
_DEFAULT_BUDGET = {
    "maxTokens": 4096,
    "maxTotalTokens": 32000,
    "maxCostUsd": 0.50,
    "maxToolCalls": 20,
    "maxLatencyMs": 300000,
}

_ANALYSIS_BUDGET = {
    "maxTokens": 4096,
    "maxTotalTokens": 24000,
    "maxCostUsd": 0.08,
    "maxToolCalls": 3,
    "maxLatencyMs": 300000,
}

# Full conformed DOCX is one tool-call JSON payload. 4096 output tokens
# cuts mid-size MSAs (~3k words). Floor is below typical 4o-mini max output.
AMENDMENT_BUDGET_FLOOR = {
    "maxTokens": 16384,
    "maxTotalTokens": 64000,
    "maxCostUsd": 0.50,
    "maxToolCalls": 8,
    "maxLatencyMs": 300000,
}


def merge_amendment_budget(parent: dict | None) -> dict:
    """Parent budget with amendment floors. Parent wins only when it is higher."""
    merged = dict(AMENDMENT_BUDGET_FLOOR)
    for key, value in dict(parent or {}).items():
        floor = AMENDMENT_BUDGET_FLOOR.get(key)
        if floor is None:
            merged[key] = value
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            merged[key] = value
            continue
        raised = max(numeric, float(floor))
        merged[key] = int(raised) if isinstance(floor, int) else raised
    return merged


def resolve_budget_settings(job: ContextJobModel) -> dict:
    """Merge job budget settings with workflow-aware defaults."""
    workflow = (job.workflow_type or "standard").lower()
    if workflow == "contract_amendment":
        return merge_amendment_budget(job.budget_settings)
    base = dict(_ANALYSIS_BUDGET if workflow == "analysis" else _DEFAULT_BUDGET)
    user = dict(job.budget_settings or {})
    base.update(user)
    return base


def resolve_max_agent_turns(job: ContextJobModel) -> int:
    explicit = int(job.max_agent_turns or 10)
    workflow = (job.workflow_type or "standard").lower()
    if workflow == "analysis":
        # Honor per-job limits (rate card templates use 15); cap at 20 for safety.
        return min(explicit, 20)
    return explicit


def resolve_per_request_max_tokens(budget_settings: dict) -> int:
    return int(budget_settings.get("maxTokens") or 4096)
