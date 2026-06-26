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


def resolve_budget_settings(job: ContextJobModel) -> dict:
    """Merge job budget settings with workflow-aware defaults."""
    workflow = (job.workflow_type or "standard").lower()
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
