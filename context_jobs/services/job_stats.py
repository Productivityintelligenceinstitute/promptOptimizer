"""Aggregate per-job performance metrics for the Performance Snapshot UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

TERMINAL_STATES = frozenset({"completed", "failed", "escalated", "repair"})
WARNING_OUTCOMES = frozenset({"accepted_with_warnings"})
REVIEW_STATES = frozenset({"escalated", "repair"})
REVIEW_OUTCOMES = frozenset({"needs_review", "escalated"})


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _run_output_package(run: Any) -> dict:
    raw = getattr(run, "run_output_package", None)
    return raw if isinstance(raw, dict) else {}


def _runtime_seconds(run: Any) -> Optional[float]:
    """Prefer latency_ms, then wall clock, then ROP costTimeSummary."""
    latency_ms = getattr(run, "latency_ms", None)
    if latency_ms is not None:
        try:
            ms = float(latency_ms)
            if ms > 0:
                return ms / 1000.0
        except (TypeError, ValueError):
            pass

    started_at = getattr(run, "started_at", None)
    ended_at = getattr(run, "ended_at", None)
    if isinstance(started_at, datetime) and isinstance(ended_at, datetime):
        delta = (ended_at - started_at).total_seconds()
        if delta > 0:
            return delta

    summary = _run_output_package(run).get("costTimeSummary") or {}
    if isinstance(summary, dict):
        rop_runtime = _as_float(summary.get("runtimeSeconds"))
        if rop_runtime is not None and rop_runtime > 0:
            return rop_runtime
    return None


def _cost_usd(run: Any) -> Optional[float]:
    """Prefer estimated_cost_usd, then parse ROP estimatedCost string."""
    direct = _as_float(getattr(run, "estimated_cost_usd", None))
    if direct is not None and direct > 0:
        return direct

    summary = _run_output_package(run).get("costTimeSummary") or {}
    if isinstance(summary, dict):
        raw = summary.get("estimatedCost")
        if isinstance(raw, (int, float)):
            value = float(raw)
            return value if value > 0 else None
        if isinstance(raw, str):
            digits = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
            parsed = _as_float(digits) if digits else None
            if parsed is not None and parsed > 0:
                return parsed
    return None


def _is_warning_run(run: Any) -> bool:
    outcome = str(getattr(run, "outcome", None) or "").strip().lower()
    if outcome in WARNING_OUTCOMES:
        return True
    state = str(getattr(run, "state", None) or "").strip().lower()
    if state == "completed_with_warnings":
        return True
    package = _run_output_package(run)
    status = str(package.get("status") or "").strip().lower()
    return status in {"completed_with_warnings", "accepted_with_warnings"}


def _is_review_or_escalation_run(run: Any) -> bool:
    state = str(getattr(run, "state", None) or "").strip().lower()
    if state in REVIEW_STATES:
        return True
    outcome = str(getattr(run, "outcome", None) or "").strip().lower()
    return outcome in REVIEW_OUTCOMES


def _validation_failure_counts(runs: list[Any]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for run in runs:
        events = getattr(run, "validation_events", None) or []
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("passed") is True:
                continue
            message = str(event.get("message") or "").strip()
            if not message:
                continue
            counts[message] = counts.get(message, 0) + 1
    return [
        {"message": message, "count": count}
        for message, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]


def _started_at_sort_key(run: Any) -> datetime:
    started = getattr(run, "started_at", None)
    if isinstance(started, datetime):
        if started.tzinfo is None:
            return started.replace(tzinfo=timezone.utc)
        return started
    return datetime.min.replace(tzinfo=timezone.utc)


def _serialize_run_summary(run: Any) -> dict[str, Any]:
    started = getattr(run, "started_at", None)
    ended = getattr(run, "ended_at", None)
    return {
        "runId": str(getattr(run, "id", "")),
        "state": getattr(run, "state", None),
        "startedAt": started.isoformat() if isinstance(started, datetime) else None,
        "endedAt": ended.isoformat() if isinstance(ended, datetime) else None,
        "outcome": getattr(run, "outcome", None),
    }


def aggregate_job_stats(runs: list[Any]) -> dict[str, Any]:
    """Build the ContextJobStats payload expected by the frontend."""
    total_runs = len(runs)
    completed_runs = len([r for r in runs if str(getattr(r, "state", "") or "") == "completed"])
    failed_runs = len([r for r in runs if str(getattr(r, "state", "") or "") == "failed"])
    escalated_runs = len([r for r in runs if str(getattr(r, "state", "") or "") == "escalated"])
    repair_runs = len([r for r in runs if str(getattr(r, "state", "") or "") == "repair"])

    terminal_runs = [
        r for r in runs if str(getattr(r, "state", "") or "") in TERMINAL_STATES
    ]
    terminal_count = len(terminal_runs)

    completion_rate = int((completed_runs / terminal_count) * 100) if terminal_count else 0

    warning_runs = len([r for r in terminal_runs if _is_warning_run(r)])
    warning_rate = int((warning_runs / terminal_count) * 100) if terminal_count else 0

    review_runs = len([r for r in terminal_runs if _is_review_or_escalation_run(r)])
    review_escalation_rate = int((review_runs / terminal_count) * 100) if terminal_count else 0

    runtimes = [seconds for seconds in (_runtime_seconds(r) for r in terminal_runs) if seconds is not None]
    costs = [cost for cost in (_cost_usd(r) for r in terminal_runs) if cost is not None]

    average_runtime_seconds = (
        round(sum(runtimes) / len(runtimes), 2) if runtimes else 0.0
    )
    average_cost = round(sum(costs) / len(costs), 4) if costs else 0.0
    average_latency_ms = (
        round(sum((getattr(r, "latency_ms", None) or 0) for r in terminal_runs) / terminal_count, 2)
        if terminal_count
        else 0.0
    )

    recent_runs = sorted(runs, key=_started_at_sort_key, reverse=True)[:5]
    recent_failures = sorted(
        [r for r in runs if str(getattr(r, "state", "") or "") == "failed"],
        key=_started_at_sort_key,
        reverse=True,
    )[:3]

    return {
        "totalRuns": total_runs,
        "completedRuns": completed_runs,
        "failedRuns": failed_runs,
        "escalatedRuns": escalated_runs,
        "repairRuns": repair_runs,
        "completionRate": completion_rate,
        "warningRate": warning_rate,
        "reviewEscalationRate": review_escalation_rate,
        "averageRuntimeSeconds": average_runtime_seconds,
        "averageCost": average_cost,
        # Kept for back-compat / debugging; UI uses averageRuntimeSeconds.
        "averageLatencyMs": average_latency_ms,
        "recentFailures": [_serialize_run_summary(r) for r in recent_failures],
        "recentRuns": [_serialize_run_summary(r) for r in recent_runs],
        "topValidationFailures": _validation_failure_counts(runs),
    }
