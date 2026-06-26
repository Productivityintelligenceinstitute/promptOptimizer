"""Spend analysis tool — normalize vendor spend data and flag rate variance."""

from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from typing import Any, Optional

from context_jobs.tools.base import BaseTool

_VALID_FORMATS = frozenset({"csv", "json"})
_VARIANCE_THRESHOLD = 0.15
_MAX_DATA_CHARS = 500_000
_MAP_SCORE_THRESHOLD = 0.55

_TITLE_ALIASES = ("title", "job_title", "jobtitle", "vendor_title", "position", "role_title")
_RATE_ALIASES = ("rate", "hourly_rate", "unit_rate", "bill_rate", "hourlyrate")
_AMOUNT_ALIASES = ("amount", "spend", "total", "cost", "total_spend", "spend_amount", "total_amount")
_HOURS_ALIASES = (
    "hours",
    "hour",
    "qty",
    "quantity",
    "headcount",
    "fte",
    "billable_hours",
    "annual_hours",
    "hours_per_month",
)
_DEFAULT_HOURS_FOR_CONCENTRATION = 1.0
_VENDOR_ALIASES = ("vendor", "supplier", "vendor_name", "company", "vendorname")
_ROLE_ALIASES = ("role", "job_role", "mapped_role")
_LEVEL_ALIASES = ("level", "seniority", "job_level", "grade")

# Role label → title keywords used when taxonomy entries omit explicit title strings.
_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "engineering": ("engineer", "engineering", "developer", "development", "architect", "devops", "sre"),
    "analytics": ("analyst", "analytics", "data", "bi", "business intelligence"),
    "design": ("designer", "design", "ux", "ui"),
    "product": ("product", "pm", "product manager"),
    "project management": ("project manager", "program manager", "scrum", "delivery manager"),
}


def _empty_result() -> dict[str, Any]:
    return {
        "normalizedRows": [],
        "unmappedTitles": [],
        "varianceFlags": [],
        "spendConcentration": [],
    }


def _error_payload(reason: str) -> str:
    return json.dumps({"error": reason}, ensure_ascii=False)


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key or "").strip().lower())


def _pick_field(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    normalized_row = {_normalize_key(k): v for k, v in row.items()}
    for alias in aliases:
        value = normalized_row.get(_normalize_key(alias))
        if value is not None and str(value).strip() != "":
            return value
    return None


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("$", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_rows(format_name: str, data: str) -> list[dict[str, Any]]:
    if format_name == "json":
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            for key in ("rows", "data", "records", "items"):
                if isinstance(parsed.get(key), list):
                    parsed = parsed[key]
                    break
            else:
                parsed = [parsed]
        if not isinstance(parsed, list):
            raise ValueError("JSON data must be an array of row objects")
        rows = [item for item in parsed if isinstance(item, dict)]
        if not rows:
            raise ValueError("JSON data contains no row objects")
        return rows

    reader = csv.DictReader(io.StringIO(data))
    rows = [dict(row) for row in reader if any(str(v or "").strip() for v in row.values())]
    if not rows:
        raise ValueError("CSV data contains no rows")
    return rows


def _normalize_title_key(title: str) -> str:
    return re.sub(r"\s+", " ", str(title or "").strip().lower())


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def _collect_entry_titles(entry: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    for key in ("titles", "aliases", "examples", "titlePatterns"):
        raw = entry.get(key)
        if isinstance(raw, str) and raw.strip():
            titles.append(raw.strip())
        elif isinstance(raw, list):
            titles.extend(str(item).strip() for item in raw if str(item).strip())
    single = entry.get("title")
    if isinstance(single, str) and single.strip():
        titles.append(single.strip())
    description = str(entry.get("description") or "").strip()
    if description and ";" in description:
        for part in description.split(";"):
            part = part.strip()
            if part and "->" not in part:
                titles.append(part)
    return titles


def _role_keywords(role: str) -> tuple[str, ...]:
    role_key = _normalize_title_key(role)
    if role_key in _ROLE_KEYWORDS:
        return _ROLE_KEYWORDS[role_key]
    role_token = role_key.replace(" ", "")
    return (role_key, role_token) if role_key else ()


def _taxonomy_match_score(title: str, entry: dict[str, Any]) -> float:
    title_key = _normalize_title_key(title)
    if not title_key:
        return 0.0

    for mapped_title in _collect_entry_titles(entry):
        mapped_key = _normalize_title_key(mapped_title)
        if not mapped_key:
            continue
        if title_key == mapped_key or title_key in mapped_key or mapped_key in title_key:
            return 1.0

    title_lower = title_key
    title_tokens = _tokenize(title_lower)
    score = 0.0

    level = str(entry.get("level") or "").strip().lower()
    if level:
        if level in title_lower or any(token == level for token in title_tokens):
            score += 0.45

    role = str(entry.get("role") or "").strip()
    if role:
        role_lower = role.lower()
        if role_lower in title_lower:
            score += 0.35
        elif any(keyword in title_lower for keyword in _role_keywords(role)):
            score += 0.4

    description = str(entry.get("description") or "").strip()
    if description:
        if "->" in description:
            left = description.split("->", 1)[0].strip().lower()
            if left and (left == title_key or left in title_lower or title_key in left):
                return 1.0
        desc_tokens = _tokenize(description)
        if desc_tokens and title_tokens:
            overlap = len(title_tokens & desc_tokens) / max(len(title_tokens), 1)
            score = max(score, overlap)

    entry_tokens = _tokenize(" ".join([str(entry.get("role") or ""), str(entry.get("level") or ""), description]))
    if title_tokens and entry_tokens:
        overlap = len(title_tokens & entry_tokens) / max(len(title_tokens), 1)
        score = max(score, overlap)

    return min(1.0, score)


def _map_title(title: str, taxonomy: list[dict[str, Any]]) -> tuple[Optional[str], Optional[str], bool]:
    if not title:
        return None, None, False

    best_entry: Optional[dict[str, Any]] = None
    best_score = 0.0
    for entry in taxonomy:
        if not isinstance(entry, dict):
            continue
        score = _taxonomy_match_score(title, entry)
        if score > best_score:
            best_score = score
            best_entry = entry

    if not best_entry or best_score < _MAP_SCORE_THRESHOLD:
        return None, None, False

    role = str(best_entry.get("role") or "").strip() or None
    level = str(best_entry.get("level") or "").strip() or None
    return role, level, True


def _normalize_taxonomy(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        titles = _collect_entry_titles(entry)
        normalized.append(
            {
                "role": str(entry.get("role") or "").strip(),
                "level": str(entry.get("level") or "").strip(),
                "description": str(entry.get("description") or "").strip(),
                "titles": titles,
            }
        )
    return normalized


def _append_variance_flag(
    flags: list[dict[str, Any]],
    seen: set[tuple[Any, ...]],
    *,
    vendor: Any,
    title: Any,
    role: Any,
    level: Any,
    rate: float,
    benchmark_rate: float,
    benchmark_type: str,
) -> None:
    dedupe_key = (vendor, title, benchmark_type)
    if dedupe_key in seen:
        return
    if benchmark_rate <= 0 or rate <= benchmark_rate * (1 + _VARIANCE_THRESHOLD):
        return
    seen.add(dedupe_key)
    variance_percent = ((rate - benchmark_rate) / benchmark_rate) * 100
    flags.append(
        {
            "vendor": vendor,
            "title": title,
            "role": role,
            "level": level,
            "rate": round(rate, 4),
            "groupMeanRate": round(benchmark_rate, 4),
            "variancePercent": round(variance_percent, 2),
            "benchmarkType": benchmark_type,
            "reason": "Rate exceeds peer benchmark by more than 15%",
        }
    )


def _flag_group_variance(
    rows: list[dict[str, Any]],
    flags: list[dict[str, Any]],
    seen: set[tuple[Any, ...]],
    *,
    benchmark_type: str,
    group_key_fn,
) -> None:
    grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rate = row.get("rate")
        if rate is None:
            continue
        key = group_key_fn(row)
        if key is None:
            continue
        grouped[key].append(row)

    for group_rows in grouped.values():
        rates = [float(row["rate"]) for row in group_rows if row.get("rate") is not None]
        if len(rates) < 2:
            continue
        benchmark_rate = min(rates)
        for row in group_rows:
            rate = row.get("rate")
            if rate is None:
                continue
            _append_variance_flag(
                flags,
                seen,
                vendor=row.get("vendor"),
                title=row.get("title"),
                role=row.get("mappedRole"),
                level=row.get("mappedLevel"),
                rate=float(rate),
                benchmark_rate=benchmark_rate,
                benchmark_type=benchmark_type,
            )


def _implied_spend_for_row(row: dict[str, Any]) -> tuple[Optional[float], str]:
    """Derive a spend weight for concentration when explicit amount is absent."""
    amount = _parse_float(row.get("amount"))
    if amount is not None and amount > 0:
        return amount, "amount"

    rate = _parse_float(row.get("rate"))
    if rate is None or rate <= 0:
        return None, "none"

    hours = _parse_float(row.get("hours"))
    if hours is not None and hours > 0:
        return rate * hours, "rate_x_hours"

    return rate * _DEFAULT_HOURS_FOR_CONCENTRATION, "rate_x_default_hours"


def _build_spend_concentration(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    basis_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    grand_total = 0.0

    for row in rows:
        vendor = str(row.get("vendor") or "Unknown").strip() or "Unknown"
        weight, basis = _implied_spend_for_row(row)
        if weight is None or weight <= 0:
            continue
        totals[vendor] += weight
        counts[vendor] += 1
        basis_counts[vendor][basis] += 1
        grand_total += weight

    if grand_total <= 0:
        return []

    concentration = []
    for vendor, total in totals.items():
        vendor_basis = basis_counts[vendor]
        basis = (
            "amount"
            if vendor_basis.get("amount")
            and not vendor_basis.get("rate_x_hours")
            and not vendor_basis.get("rate_x_default_hours")
            else "rate_x_hours"
            if vendor_basis.get("rate_x_hours")
            else "rate_x_default_hours"
        )
        concentration.append(
            {
                "vendor": vendor,
                "totalSpend": round(total, 2),
                "sharePercent": round((total / grand_total) * 100, 2),
                "rowCount": counts[vendor],
                "basis": basis,
            }
        )
    concentration.sort(key=lambda item: item["totalSpend"], reverse=True)
    return concentration[:10]


def _analyze_spend(
    raw_rows: list[dict[str, Any]],
    taxonomy: list[dict[str, Any]],
) -> dict[str, Any]:
    result = _empty_result()
    normalized_rows: list[dict[str, Any]] = []
    unmapped: set[str] = set()

    for raw in raw_rows:
        title = str(_pick_field(raw, _TITLE_ALIASES) or "").strip()
        vendor = str(_pick_field(raw, _VENDOR_ALIASES) or "").strip() or None
        rate = _parse_float(_pick_field(raw, _RATE_ALIASES))
        amount = _parse_float(_pick_field(raw, _AMOUNT_ALIASES))
        hours = _parse_float(_pick_field(raw, _HOURS_ALIASES))

        mapped_role = str(_pick_field(raw, _ROLE_ALIASES) or "").strip() or None
        mapped_level = str(_pick_field(raw, _LEVEL_ALIASES) or "").strip() or None

        if title and taxonomy:
            taxonomy_role, taxonomy_level, was_mapped = _map_title(title, taxonomy)
            if was_mapped:
                if not mapped_role:
                    mapped_role = taxonomy_role
                if not mapped_level:
                    mapped_level = taxonomy_level
            elif not mapped_role and not mapped_level:
                unmapped.add(title)
        elif title and not taxonomy and not mapped_role and not mapped_level:
            unmapped.add(title)

        mapped = bool(mapped_role or mapped_level)

        row = {
            "vendor": vendor,
            "title": title or None,
            "mappedRole": mapped_role,
            "mappedLevel": mapped_level,
            "rate": rate,
            "amount": amount,
            "hours": hours,
            "mapped": mapped,
        }
        normalized_rows.append(row)

    variance_flags: list[dict[str, Any]] = []
    seen_flags: set[tuple[Any, ...]] = set()
    _flag_group_variance(
        normalized_rows,
        variance_flags,
        seen_flags,
        benchmark_type="role_level",
        group_key_fn=lambda row: (
            (row.get("mappedRole"), row.get("mappedLevel"))
            if row.get("mappedRole") and row.get("mappedLevel")
            else None
        ),
    )
    _flag_group_variance(
        normalized_rows,
        variance_flags,
        seen_flags,
        benchmark_type="title",
        group_key_fn=lambda row: _normalize_title_key(str(row.get("title") or "")) or None,
    )

    result["normalizedRows"] = normalized_rows
    result["unmappedTitles"] = sorted(unmapped)
    result["varianceFlags"] = variance_flags
    result["spendConcentration"] = _build_spend_concentration(normalized_rows)
    return result


class SpendAnalyzerTool(BaseTool):
    id = "spend-analyzer"
    name = "Spend Analyzer"
    description = (
        "Parse CSV or JSON vendor spend data, map titles to a taxonomy, "
        "flag unmapped titles and high rate variance, and summarize spend concentration."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "enum": ["csv", "json"],
                "description": "Input data format",
            },
            "data": {
                "type": "string",
                "description": "Raw CSV or JSON spend data",
            },
            "taxonomy": {
                "type": "array",
                "description": (
                    "Job taxonomy for title mapping. Each entry should include role, level, "
                    "and title strings (titles/aliases/examples) or descriptions like "
                    "'Senior Software Engineer -> Engineering/Senior'."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string"},
                        "level": {"type": "string"},
                        "description": {"type": "string"},
                        "titles": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Vendor title strings mapped to this role/level",
                        },
                        "aliases": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
        "required": ["format", "data"],
    }

    async def execute(self, arguments: dict[str, Any], api_key: Optional[str] = None) -> str:
        try:
            format_name = str(arguments.get("format") or "").strip().lower()
            data = str(arguments.get("data") or "").strip()
            taxonomy = _normalize_taxonomy(arguments.get("taxonomy"))

            if format_name not in _VALID_FORMATS:
                return _error_payload(
                    f"format must be one of: {', '.join(sorted(_VALID_FORMATS))}"
                )
            if not data:
                return _error_payload("data is required")
            if len(data) > _MAX_DATA_CHARS:
                return _error_payload(f"data exceeds maximum length of {_MAX_DATA_CHARS} characters")

            raw_rows = _parse_rows(format_name, data)
            result = _analyze_spend(raw_rows, taxonomy)
            return json.dumps(result, ensure_ascii=False)
        except json.JSONDecodeError as exc:
            return _error_payload(f"Failed to parse JSON data: {exc}")
        except Exception as exc:
            return _error_payload(str(exc))
