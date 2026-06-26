"""Source evidence strength helpers — placeholder vs actionable weak evidence."""

from __future__ import annotations

from typing import Any

# Vector hits below this score are treated as empty-KB noise (not surfaced as WEAK_EVIDENCE).
MIN_VECTOR_RELEVANCE_SCORE = 0.35


def is_placeholder_source_name(name: str | None) -> bool:
    return "placeholder" in str(name or "").lower()


def is_placeholder_source_text(text: str | None) -> bool:
    sample = str(text or "")[:500].lower()
    return "replace this placeholder" in sample or "customer replace-me" in sample


def is_incidental_weak_source(trace: dict[str, Any]) -> bool:
    """Low-relevance workspace KB hit before procurement demo docs are ingested."""
    if trace.get("evidenceStrength") != "weak":
        return False
    name = str(trace.get("sourceName") or "").lower()
    return name in {"workspace knowledge", "workspace kb"}


def is_actionable_weak_evidence(trace: dict[str, Any]) -> bool:
    if trace.get("evidenceStrength") != "weak":
        return False
    if is_placeholder_source_name(trace.get("sourceName")):
        return False
    if is_incidental_weak_source(trace):
        return False
    return True


def actionable_weak_sources(source_traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "sourceId": trace.get("sourceId"),
            "sourceName": trace.get("sourceName"),
            "sourceType": trace.get("sourceType"),
            "evidenceStrength": trace.get("evidenceStrength"),
        }
        for trace in source_traces
        if is_actionable_weak_evidence(trace)
    ]


def majority_actionable_weak(source_traces: list[dict[str, Any]]) -> bool:
    actionable = [
        t
        for t in source_traces
        if t.get("evidenceStrength") not in {None, "informational"}
        and not is_placeholder_source_name(t.get("sourceName"))
    ]
    if not actionable:
        return False
    weak = sum(1 for t in actionable if is_actionable_weak_evidence(t))
    return weak > len(actionable) / 2
