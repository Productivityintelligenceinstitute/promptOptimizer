"""Validation engine for Context Jobs runs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
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


def _extract_template_keys(template: str) -> list[str]:
    keys: list[str] = []
    for raw_line in (template or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = re.match(r"^#+\s+(.+)$", line)
        if heading:
            keys.append(heading.group(1).strip().lower())
            continue
        pair = re.match(r"^([A-Za-z0-9_\-\s]+)\s*:", line)
        if pair:
            keys.append(pair.group(1).strip().lower())
    return keys


def _output_template_matches(output_text: str, template: str) -> bool:
    output = (output_text or "").strip()
    template = (template or "").strip()
    if not output or not template:
        return True

    if template.startswith("{") or template.startswith("["):
        try:
            expected = json.loads(template)
            actual = json.loads(output)
        except Exception:
            return False

        def shape_matches(expected_value: Any, actual_value: Any) -> bool:
            if isinstance(expected_value, dict):
                if not isinstance(actual_value, dict):
                    return False
                for key, nested in expected_value.items():
                    if key not in actual_value:
                        return False
                    if not shape_matches(nested, actual_value[key]):
                        return False
                return True
            if isinstance(expected_value, list):
                if not isinstance(actual_value, list):
                    return False
                if not expected_value:
                    return True
                if not actual_value:
                    return False
                return shape_matches(expected_value[0], actual_value[0])
            return True

        return shape_matches(expected, actual)

    required_keys = _extract_template_keys(template)
    if not required_keys:
        return True

    lower_output = output.lower()
    for key in required_keys:
        if f"{key}:" not in lower_output and f"#{key}" not in lower_output:
            return False
    return True


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
            template = (job.output_template or "").strip()
            if not template:
                template = (job.semantic_blueprint or "").strip()
            passed = _output_template_matches(output_text, template)
            if not template:
                passed = True
                message = "No output template defined, format check skipped."
            else:
                message = (
                    "Output matches expected format."
                    if passed
                    else "Output does not match expected format sections."
                )

        elif rule_type == "groundedness":
            if source_traces:
                source_names = [t.get("sourceName", "") for t in source_traces]
                try:
                    import os
                    from openai import AsyncOpenAI
                    source_context = "\n".join(
                        f"- {t.get('sourceName', '')}: {t.get('preview', '')}"
                        for t in source_traces[:5]
                    )
                    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                    judge_response = await client.chat.completions.create(
                        model="gpt-4o-mini",
                        max_tokens=128,
                        temperature=0,
                        messages=[
                            {
                                "role": "user",
                                "content": (
                                    f"You are a groundedness judge. Determine if the output is supported by the sources.\n\n"
                                    f"Sources:\n{source_context}\n\n"
                                    f"Output (first 1000 chars):\n{(output_text or '')[:1000]}\n\n"
                                    f"Reply with exactly one word: GROUNDED or UNGROUNDED"
                                ),
                            }
                        ],
                    )
                    verdict = (judge_response.choices[0].message.content or "").strip().upper()
                    passed = "GROUNDED" in verdict
                    message = "LLM judge: output is grounded in retrieved sources." if passed else "LLM judge: output may not be grounded in retrieved sources."
                except Exception:
                    passed = any(name.lower() in (output_text or "").lower() for name in source_names if name)
                    message = "Output references retrieved sources." if passed else "Output may not be grounded in retrieved sources."
            else:
                passed = True
                message = "No sources retrieved, groundedness check skipped."

        elif rule_type == "policy":
            forbidden = ["as an ai", "i cannot", "i'm not able to", "i am not able to"]
            violations = [phrase for phrase in forbidden if phrase in (output_text or "").lower()]
            passed = len(violations) == 0
            message = "Policy check passed." if passed else f"Output contains policy violations: {', '.join(violations)}"

        else:
            description = rule.get("description", "")
            if description and output_text:
                try:
                    import os
                    from openai import AsyncOpenAI
                    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                    judge_response = await client.chat.completions.create(
                        model="gpt-4o-mini",
                        max_tokens=128,
                        temperature=0,
                        messages=[
                            {
                                "role": "user",
                                "content": (
                                    f"You are a quality judge. Evaluate if the output meets this requirement:\n"
                                    f"Requirement: {description}\n\n"
                                    f"Output (first 1000 chars):\n{(output_text or '')[:1000]}\n\n"
                                    f"Reply with exactly one word: PASS or FAIL"
                                ),
                            }
                        ],
                    )
                    verdict = (judge_response.choices[0].message.content or "").strip().upper()
                    passed = "PASS" in verdict
                    message = f"LLM judge: {description} — {'passed' if passed else 'failed'}."
                except Exception:
                    keywords = [w for w in description.lower().split() if len(w) > 4]
                    matched = sum(1 for k in keywords if k.lower() in (output_text or "").lower())
                    passed = matched >= max(1, len(keywords) // 3)
                    message = "Custom check passed." if passed else description or "Custom check failed."
            else:
                passed = bool((output_text or "").strip())
                message = "Custom check passed." if passed else "Custom check failed."

        events.append(
            ValidationEvent(rule=rule_name, passed=passed, message=message, severity=severity)
        )

    # Auto-check required glossary terms
    if job.glossary_terms:
        required_terms = [
            t for t in job.glossary_terms
            if isinstance(t, dict) and t.get("required")
        ]
        for term in required_terms:
            term_text = term.get("term", "")
            synonyms = term.get("synonyms") or []
            all_variants = [term_text] + synonyms
            found = any(
                v.lower() in (output_text or "").lower()
                for v in all_variants if v
            )
            events.append(
                ValidationEvent(
                    rule=f"glossary_required_{term_text.lower().replace(' ', '_')}",
                    passed=found,
                    message=(
                        f"Required term '{term_text}' present in output."
                        if found
                        else f"Required term '{term_text}' missing from output."
                    ),
                    severity="warning",
                )
            )

    # Auto-check relationships are respected in output
    if job.relationships:
        for rel in job.relationships:
            if not isinstance(rel, dict):
                continue
            from_term = rel.get("fromTerm", "")
            to_term = rel.get("toTerm", "")
            relation = rel.get("relation", "")
            if not from_term or not to_term:
                continue
            # Check both terms appear in output
            from_present = from_term.lower() in (output_text or "").lower()
            to_present = to_term.lower() in (output_text or "").lower()
            passed = from_present and to_present
            events.append(
                ValidationEvent(
                    rule=f"relationship_{from_term.lower().replace(' ', '_')}_{to_term.lower().replace(' ', '_')}",
                    passed=passed,
                    message=(
                        f"Relationship '{from_term} {relation} {to_term}' reflected in output."
                        if passed
                        else f"Terms '{from_term}' or '{to_term}' missing from output."
                    ),
                    severity="warning",
                )
            )

    # Auto-check policy profile constraints
    if job.policy_profile == "strict_compliance":
        strict_forbidden = [
            "i cannot guarantee",
            "i am not able to",
            "as an ai",
            "i don't have access to",
            "i'm unable to",
            "please consult a",
            "this is not legal advice",
            "this is not financial advice",
        ]
        violations = [p for p in strict_forbidden if p in (output_text or "").lower()]
        passed = len(violations) == 0
        events.append(ValidationEvent(
            rule="strict_compliance_policy",
            passed=passed,
            message="Output meets strict compliance policy." if passed
                    else f"Strict compliance violations: {', '.join(violations)}",
            severity="blocking",
        ))

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
