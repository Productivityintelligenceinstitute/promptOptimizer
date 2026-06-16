"""Validation engine for Context Jobs runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from schemas.context_jobs_model import ContextJobModel


@dataclass
class ValidationEvent:
    rule: str
    passed: bool
    message: str
    severity: str


@dataclass
class ValidationSummary:
    overall_decision: str
    confidence_level: str
    checks: list[dict[str, Any]]
    status: str
    repair_reason: str | None = None


def _citation_present(output_text: str) -> bool:
    return "[source:" in (output_text or "")


def _find_trace(source_traces: list[dict], trusted_source: dict) -> dict | None:
    name = (trusted_source.get("name") or trusted_source.get("value") or "").lower()
    for trace in source_traces:
        if name and name in (trace.get("sourceName") or "").lower():
            return trace
    return None


def _majority_weak(source_traces: list[dict]) -> bool:
    if not source_traces:
        return False
    weak = sum(1 for s in source_traces if s.get("evidenceStrength") == "weak")
    return weak > len(source_traces) / 2


async def run_validation(
    output_text: str,
    job: ContextJobModel,
    source_traces: list[dict],
) -> tuple[list[ValidationEvent], ValidationSummary]:
    rules = [r for r in (job.validation_rules or []) if isinstance(r, dict) and r.get("enabled")]
    events: list[ValidationEvent] = []

    for rule in rules:
        severity = str(rule.get("severity") or "warning")
        rule_type = str(rule.get("type") or "custom")
        rule_name = str(rule.get("name") or "Validation rule")

        if rule_type == "citation":
            passed = "[source:" in (output_text or "")
            message = "Citations present." if passed else "Missing [source:] citations in output."

        elif rule_type == "format":
            passed = bool(job.semantic_blueprint) and any(
                section.strip("#").strip().lower() in (output_text or "").lower()
                for section in (job.semantic_blueprint or "").split("\n")
                if section.startswith("#")
            )
            if not job.semantic_blueprint:
                passed = True
                message = "No semantic blueprint defined, format check skipped."
            else:
                message = (
                    "Output matches expected format."
                    if passed
                    else "Output does not match expected format sections."
                )

        elif rule_type == "groundedness":
            if source_traces:
                source_names = [t.get("sourceName", "") for t in source_traces]
                passed = any(name.lower() in (output_text or "").lower() for name in source_names if name)
            else:
                passed = True
            message = "Output references retrieved sources." if passed else "Output may not be grounded in retrieved sources."

        elif rule_type == "policy":
            forbidden = ["as an ai", "i cannot", "i'm not able to", "i am not able to"]
            violations = [phrase for phrase in forbidden if phrase in (output_text or "").lower()]
            passed = len(violations) == 0
            message = "Policy check passed." if passed else f"Output contains policy violations: {', '.join(violations)}"

        else:
            description = rule.get("description", "").lower()
            passed = bool((output_text or "").strip())
            if description and output_text:
                keywords = [w for w in description.split() if len(w) > 4]
                matched = sum(1 for k in keywords if k.lower() in output_text.lower())
                passed = matched >= max(1, len(keywords) // 3)
            message = "Custom check passed." if passed else rule.get("description") or "Custom check failed."

        events.append(
            ValidationEvent(rule=rule_name, passed=passed, message=message, severity=severity)
        )

    blocking_fails = [e for e in events if not e.passed and e.severity == "blocking"]
    error_fails = [e for e in events if not e.passed and e.severity == "error"]
    warning_fails = [e for e in events if not e.passed and e.severity == "warning"]

    retrieval_config = job.retrieval_config or {}
    grounded_mode = bool(
        (isinstance(retrieval_config, dict) and retrieval_config.get("hybridRetrieval"))
        or (job.trusted_sources and len(job.trusted_sources) > 0)
    )
    grounded_violation = False
    if grounded_mode:
        required_sources = [
            s for s in (job.trusted_sources or []) if isinstance(s, dict) and s.get("trustLevel") == "required"
        ]
        for source in required_sources:
            trace = _find_trace(source_traces, source)
            if not trace or trace.get("evidenceStrength") == "weak":
                grounded_violation = True
                break

    if blocking_fails:
        status = "blocked_by_policy"
        decision = "blocked"
        confidence = "high"
        repair_reason = blocking_fails[0].message
    elif error_fails or grounded_violation:
        status = "needs_repair"
        decision = "failed"
        confidence = "medium"
        repair_reason = error_fails[0].message if error_fails else "Required source evidence is weak or missing."
    elif job.escalation_policy == "always_review" or _majority_weak(source_traces):
        status = "needs_human_review"
        decision = "passed_with_warnings"
        confidence = "low"
        repair_reason = None
    elif warning_fails:
        status = "completed_with_warnings"
        decision = "passed_with_warnings"
        confidence = "medium"
        repair_reason = None
    else:
        status = "completed"
        decision = "passed"
        confidence = "high"
        repair_reason = None

    checks = [
        {
            "name": e.rule,
            "result": "passed"
            if e.passed
            else ("warning" if e.severity == "warning" else "failed"),
            "message": e.message,
        }
        for e in events
    ]
    summary = ValidationSummary(
        overall_decision=decision,
        confidence_level=confidence,
        checks=checks,
        status=status,
        repair_reason=repair_reason,
    )
    return events, summary
