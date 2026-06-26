"""Procurement validation checkers dispatched from validation rules."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from context_jobs.validation.tool_output import find_tool_output
from schemas.context_jobs_model import ContextJobModel

CheckerFn = Callable[["ProcurementCheckContext", dict[str, Any]], "ProcurementCheckResult"]

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_RISK_TIER_RE = re.compile(
    r'"riskTier"\s*:\s*"(low|medium|high|critical)"',
    re.IGNORECASE,
)


@dataclass
class ProcurementCheckContext:
    output_text: str
    job: ContextJobModel
    source_traces: list[dict[str, Any]]
    tool_executions: list[dict[str, Any]] | None = None
    tool_events: list[dict[str, Any]] | None = None


@dataclass
class ProcurementCheckResult:
    passed: bool
    message: str
    checker: str
    expected: Any
    found: Any


def _normalize_clause_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


_MANDATORY_CLAUSE_ALIASES: dict[str, tuple[str, ...]] = {
    "liability_cap": (
        "liability_cap",
        "liability",
        "liability cap",
        "limitation of liability",
        "limitation on liability",
        "indemnification",
        "limitation of remedies",
    ),
    "termination": (
        "termination",
        "termination rights",
        "termination for convenience",
        "termination for cause",
        "material breach",
        "cure period",
    ),
    "data_protection": (
        "data_protection",
        "data protection",
        "data privacy",
        "privacy",
        "gdpr",
        "data processing",
        "cross border transfer",
        "standard contractual clauses",
        "scc",
        "breach notification",
        "confidentiality",
    ),
    "subprocessor_controls": (
        "subprocessor_controls",
        "subprocessor",
        "subprocessors",
        "flow down",
        "flow-down",
        "subprocessor approval",
        "subprocessor notice",
        "right to object",
    ),
    "ai_use_restrictions": (
        "ai_use_restrictions",
        "ai use restrictions",
        "ai restrictions",
        "ai use",
        "ai data use",
        "ai/data use",
        "artificial intelligence",
        "model training",
        "training prohibitions",
        "customer data training",
        "ai generated outputs",
        "ai-generated outputs",
    ),
}


def _clause_id_variants(clause: dict[str, Any]) -> set[str]:
    variants: set[str] = set()
    for key in ("id", "clauseId", "clause_id", "name", "title", "summary", "evidence", "text"):
        raw = clause.get(key)
        if raw is None:
            continue
        normalized = _normalize_clause_id(str(raw))
        if normalized:
            variants.add(normalized)
    return variants


def _clause_matches_required_id(clause: dict[str, Any], required_id: str) -> bool:
    variants = _clause_id_variants(clause)
    if required_id in variants:
        return True

    aliases = {
        _normalize_clause_id(alias)
        for alias in _MANDATORY_CLAUSE_ALIASES.get(required_id, (required_id,))
        if alias
    }
    if variants & aliases:
        return True

    # Allow phrase-level matches after normalization, e.g.
    # "Liability cap, indemnification..." -> liability_cap.
    return any(
        alias and (alias in variant or variant in alias)
        for alias in aliases
        for variant in variants
    )


def _top_level_clause_present(analysis: dict[str, Any], required_id: str) -> bool:
    """Fallback for contract-analyzer summary fields when clause rows use unexpected names."""
    field_map = {
        "liability_cap": ("liabilityCap",),
        "termination": ("termination",),
        "ai_use_restrictions": ("aiDataUseLanguage",),
    }
    for field in field_map.get(required_id, ()):
        value = analysis.get(field)
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return True
        if value and not isinstance(value, str):
            return True
    return False


def _format_failure(
    checker: str,
    expected: Any,
    found: Any,
    detail: str = "",
) -> str:
    suffix = f" {detail}" if detail else ""
    return f"{checker}: expected {expected}; found {found}.{suffix}".rstrip()


def _format_success(checker: str, detail: str = "") -> str:
    if detail:
        return f"{checker}: passed. {detail}"
    return f"{checker}: passed."


def check_mandatory_clause(
    ctx: ProcurementCheckContext,
    params: dict[str, Any],
) -> ProcurementCheckResult:
    checker = "mandatory_clause"
    required_ids = [
        _normalize_clause_id(str(item))
        for item in (params.get("requiredClauseIds") or [])
        if str(item).strip()
    ]
    expected = {
        "requiredClauseIds": required_ids,
        "present": True,
    }
    if not required_ids:
        return ProcurementCheckResult(
            passed=True,
            message=_format_success(checker, "No requiredClauseIds configured."),
            checker=checker,
            expected=expected,
            found={"clauses": []},
        )

    analysis = find_tool_output(
        "contract-analyzer",
        tool_executions=ctx.tool_executions,
        tool_events=ctx.tool_events,
    )
    if analysis is None:
        return ProcurementCheckResult(
            passed=False,
            message=_format_failure(
                checker,
                expected,
                "no contract-analyzer tool output",
                "Run contract-analyzer before validation.",
            ),
            checker=checker,
            expected=expected,
            found=None,
        )

    clauses = [c for c in (analysis.get("clauses") or []) if isinstance(c, dict)]
    found_by_id: dict[str, dict[str, Any]] = {}
    for clause_id in required_ids:
        matched = None
        for clause in clauses:
            if _clause_matches_required_id(clause, clause_id):
                matched = clause
                break
        fallback_present = matched is None and _top_level_clause_present(analysis, clause_id)
        found_by_id[clause_id] = {
            "present": bool((matched and matched.get("present")) or fallback_present),
            "matchedClause": (
                matched.get("name")
                or matched.get("title")
                if matched
                else "contract-analyzer summary field"
                if fallback_present
                else None
            ),
        }

    missing = [
        clause_id
        for clause_id, state in found_by_id.items()
        if not state.get("present")
    ]
    if missing:
        return ProcurementCheckResult(
            passed=False,
            message=_format_failure(checker, expected, found_by_id),
            checker=checker,
            expected=expected,
            found=found_by_id,
        )

    return ProcurementCheckResult(
        passed=True,
        message=_format_success(checker),
        checker=checker,
        expected=expected,
        found=found_by_id,
    )


def _benchmark_for_row(row: dict[str, Any], rows: list[dict[str, Any]]) -> float | None:
    rate = row.get("rate")
    if rate is None:
        return None
    role = row.get("mappedRole")
    level = row.get("mappedLevel")
    if role and level:
        peers = [
            r
            for r in rows
            if r.get("mappedRole") == role
            and r.get("mappedLevel") == level
            and r.get("rate") is not None
        ]
        if peers:
            return min(float(r["rate"]) for r in peers)
    title = row.get("title")
    if title:
        peers = [r for r in rows if r.get("title") == title and r.get("rate") is not None]
        if peers:
            return min(float(r["rate"]) for r in peers)
    return None


def check_rate_benchmark(
    ctx: ProcurementCheckContext,
    params: dict[str, Any],
) -> ProcurementCheckResult:
    checker = "rate_benchmark"
    try:
        threshold_percent = float(params.get("thresholdPercent", 15))
    except (TypeError, ValueError):
        threshold_percent = 15.0
    expected = {
        "thresholdPercent": threshold_percent,
        "rule": "no normalizedRows rate may exceed peer benchmark by more than thresholdPercent",
    }

    analysis = find_tool_output(
        "spend-analyzer",
        tool_executions=ctx.tool_executions,
        tool_events=ctx.tool_events,
    )
    if analysis is None:
        return ProcurementCheckResult(
            passed=False,
            message=_format_failure(
                checker,
                expected,
                "no spend-analyzer tool output",
                "Run spend-analyzer before validation.",
            ),
            checker=checker,
            expected=expected,
            found=None,
        )

    rows = [r for r in (analysis.get("normalizedRows") or []) if isinstance(r, dict)]
    violations: list[dict[str, Any]] = []
    for row in rows:
        rate = row.get("rate")
        if rate is None:
            continue
        benchmark = _benchmark_for_row(row, rows)
        if benchmark is None or benchmark <= 0:
            continue
        rate_val = float(rate)
        limit = benchmark * (1 + (threshold_percent / 100))
        if rate_val > limit:
            violations.append(
                {
                    "vendor": row.get("vendor"),
                    "title": row.get("title"),
                    "rate": rate_val,
                    "benchmark": round(benchmark, 4),
                    "limit": round(limit, 4),
                    "variancePercent": round(((rate_val - benchmark) / benchmark) * 100, 2),
                }
            )

    if violations:
        return ProcurementCheckResult(
            passed=False,
            message=_format_failure(checker, expected, violations),
            checker=checker,
            expected=expected,
            found=violations,
        )

    return ProcurementCheckResult(
        passed=True,
        message=_format_success(checker),
        checker=checker,
        expected=expected,
        found={"normalizedRowCount": len(rows), "violations": []},
    )


def _normalize_risk_tier(value: Any) -> str | None:
    if value is None:
        return None
    tier = str(value).strip().lower()
    if tier in _RISK_ORDER:
        return tier
    return None


def _collect_risk_tiers(ctx: ProcurementCheckContext) -> list[str]:
    tiers: list[str] = []

    try:
        parsed_output = json.loads((ctx.output_text or "").strip())
        if isinstance(parsed_output, dict):
            tier = _normalize_risk_tier(parsed_output.get("riskTier"))
            if tier:
                tiers.append(tier)
            for vendor in parsed_output.get("vendors") or []:
                if isinstance(vendor, dict):
                    tier = _normalize_risk_tier(vendor.get("riskTier"))
                    if tier:
                        tiers.append(tier)
    except json.JSONDecodeError:
        pass

    for match in _RISK_TIER_RE.finditer(ctx.output_text or ""):
        tier = _normalize_risk_tier(match.group(1))
        if tier:
            tiers.append(tier)

    for trace in ctx.source_traces or []:
        if not isinstance(trace, dict):
            continue
        preview = str(trace.get("preview") or "")
        for match in _RISK_TIER_RE.finditer(preview):
            tier = _normalize_risk_tier(match.group(1))
            if tier:
                tiers.append(tier)
        metadata = trace.get("metadata")
        if isinstance(metadata, dict):
            tier = _normalize_risk_tier(metadata.get("riskTier"))
            if tier:
                tiers.append(tier)

    for tool_id in ("contract-analyzer", "spend-analyzer"):
        payload = find_tool_output(
            tool_id,
            tool_executions=ctx.tool_executions,
            tool_events=ctx.tool_events,
        )
        if not isinstance(payload, dict):
            continue
        tier = _normalize_risk_tier(payload.get("riskTier"))
        if tier:
            tiers.append(tier)
        for vendor in payload.get("vendors") or []:
            if isinstance(vendor, dict):
                tier = _normalize_risk_tier(vendor.get("riskTier"))
                if tier:
                    tiers.append(tier)

    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for tier in tiers:
        if tier in seen:
            continue
        seen.add(tier)
        unique.append(tier)
    return unique


def check_risk_threshold(
    ctx: ProcurementCheckContext,
    params: dict[str, Any],
) -> ProcurementCheckResult:
    checker = "risk_threshold"
    max_tier = _normalize_risk_tier(params.get("maxRiskTier")) or "medium"
    expected = {"maxRiskTier": max_tier}

    tiers = _collect_risk_tiers(ctx)
    if not tiers:
        return ProcurementCheckResult(
            passed=False,
            message=_format_failure(
                checker,
                expected,
                "no vendor riskTier metadata found",
                "Provide riskTier in retrieval context, tool output, or structured output.",
            ),
            checker=checker,
            expected=expected,
            found=[],
        )

    max_allowed = _RISK_ORDER[max_tier]
    violating = [tier for tier in tiers if _RISK_ORDER.get(tier, 0) > max_allowed]
    found = {"riskTiers": tiers, "violating": violating}
    if violating:
        return ProcurementCheckResult(
            passed=False,
            message=_format_failure(checker, expected, found),
            checker=checker,
            expected=expected,
            found=found,
        )

    return ProcurementCheckResult(
        passed=True,
        message=_format_success(checker),
        checker=checker,
        expected=expected,
        found=found,
    )


PROCUREMENT_CHECKERS: dict[str, CheckerFn] = {
    "mandatory_clause": check_mandatory_clause,
    "rate_benchmark": check_rate_benchmark,
    "risk_threshold": check_risk_threshold,
}


def run_procurement_checker(
    checker: str,
    rule: dict[str, Any],
    ctx: ProcurementCheckContext,
) -> ProcurementCheckResult:
    name = (checker or "").strip()
    fn = PROCUREMENT_CHECKERS.get(name)
    params = rule.get("params") if isinstance(rule.get("params"), dict) else {}
    if not fn:
        return ProcurementCheckResult(
            passed=False,
            message=_format_failure(
                name or "procurement",
                "registered procurement checker",
                name or "(missing checker)",
            ),
            checker=name or "procurement",
            expected="registered procurement checker",
            found=name or "(missing checker)",
        )
    return fn(ctx, params)
