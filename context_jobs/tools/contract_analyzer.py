"""Contract analysis tool — extract structured terms from URL or pasted text."""

from __future__ import annotations

import json
import os
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
import trafilatura
from openai import AsyncOpenAI

from context_jobs.tools.base import BaseTool

_MAX_DOCUMENT_CHARS = 80_000
_VALID_SOURCES = frozenset({"url", "text"})
_VALID_CONTRACT_TYPES = frozenset({"msa", "sow", "nda"})
_RISK_LEVELS = frozenset({"low", "medium", "high"})

# Top-level summary fields → missing clause label when null/empty.
_INFERRED_MISSING_CLAUSES: tuple[tuple[str, str], ...] = (
    ("termination", "Termination"),
    ("pricingEscalation", "Pricing and escalation"),
    ("liabilityCap", "Liability cap"),
    ("aiDataUseLanguage", "AI/data use restrictions"),
)


def _is_empty_field(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _infer_missing_clauses(analysis: dict[str, Any]) -> list[str]:
    """Augment LLM missingClauses from null summaries and absent clause rows."""
    missing: list[str] = []
    seen: set[str] = set()

    def add(label: str) -> None:
        normalized = label.strip()
        if not normalized:
            return
        key = normalized.lower()
        if key in seen:
            return
        seen.add(key)
        missing.append(normalized)

    for item in analysis.get("missingClauses") or []:
        add(str(item))

    for field, label in _INFERRED_MISSING_CLAUSES:
        if _is_empty_field(analysis.get(field)):
            add(label)

    if analysis.get("renewalNoticeDays") is None and _is_empty_field(analysis.get("autoRenewal")):
        add("Renewal notice period")

    for clause in analysis.get("clauses") or []:
        if not isinstance(clause, dict):
            continue
        if clause.get("present"):
            continue
        name = str(clause.get("name") or "").strip()
        if name:
            add(name)

    return missing


def _empty_analysis() -> dict[str, Any]:
    return {
        "parties": [],
        "contractType": None,
        "effectiveDate": None,
        "expiryDate": None,
        "renewalNoticeDays": None,
        "autoRenewal": None,
        "clauses": [],
        "missingClauses": [],
        "aiDataUseLanguage": None,
        "liabilityCap": None,
        "termination": None,
        "pricingEscalation": None,
    }


def _error_payload(reason: str) -> str:
    return json.dumps({"error": reason}, ensure_ascii=False)


def _normalize_analysis(raw: dict[str, Any]) -> dict[str, Any]:
    base = _empty_analysis()
    if not isinstance(raw, dict):
        return base

    parties = raw.get("parties")
    if isinstance(parties, list):
        base["parties"] = [str(p).strip() for p in parties if str(p).strip()]

    contract_type = raw.get("contractType")
    if isinstance(contract_type, str):
        normalized = contract_type.strip().lower()
        base["contractType"] = normalized if normalized in _VALID_CONTRACT_TYPES else None
    elif contract_type is not None:
        base["contractType"] = str(contract_type)

    for key in (
        "effectiveDate",
        "expiryDate",
        "aiDataUseLanguage",
        "liabilityCap",
        "termination",
        "pricingEscalation",
    ):
        value = raw.get(key)
        base[key] = None if value is None else str(value)

    renewal = raw.get("renewalNoticeDays")
    if renewal is not None:
        try:
            base["renewalNoticeDays"] = int(renewal)
        except (TypeError, ValueError):
            base["renewalNoticeDays"] = None

    auto_renewal = raw.get("autoRenewal")
    if isinstance(auto_renewal, bool):
        base["autoRenewal"] = auto_renewal
    elif isinstance(auto_renewal, str):
        base["autoRenewal"] = auto_renewal.strip().lower() in {"true", "yes", "1"}

    clauses = raw.get("clauses")
    if isinstance(clauses, list):
        normalized_clauses = []
        for item in clauses:
            if not isinstance(item, dict):
                continue
            risk = str(item.get("riskLevel") or "low").strip().lower()
            if risk not in _RISK_LEVELS:
                risk = "low"
            normalized_clauses.append(
                {
                    "name": str(item.get("name") or "").strip(),
                    "present": bool(item.get("present")),
                    "summary": str(item.get("summary") or "").strip(),
                    "riskLevel": risk,
                }
            )
        base["clauses"] = normalized_clauses

    missing = raw.get("missingClauses")
    if isinstance(missing, list):
        base["missingClauses"] = [str(m).strip() for m in missing if str(m).strip()]

    base["missingClauses"] = _infer_missing_clauses(base)
    return base


async def _fetch_url_text(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
        raise ValueError("localhost URLs are not allowed")
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only http/https URLs are allowed")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
    text = trafilatura.extract(response.text) or ""
    if not text:
        text = response.text
    text = text.strip()
    if not text:
        raise ValueError("No text could be extracted from the URL")
    return text[:_MAX_DOCUMENT_CHARS]


class ContractAnalyzerTool(BaseTool):
    id = "contract-analyzer"
    name = "Contract Analyzer"
    description = (
        "Analyze a contract from a URL or pasted text and return structured "
        "parties, dates, clauses, risks, and missing terms as JSON."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "enum": ["url", "text"],
                "description": "Whether value is a document URL or raw contract text",
            },
            "value": {
                "type": "string",
                "description": "URL to fetch or contract text to analyze",
            },
            "contractType": {
                "type": "string",
                "enum": ["msa", "sow", "nda"],
                "description": "Optional expected contract type hint",
            },
        },
        "required": ["source", "value"],
    }

    async def execute(self, arguments: dict[str, Any], api_key: Optional[str] = None) -> str:
        try:
            source = str(arguments.get("source") or "").strip().lower()
            value = str(arguments.get("value") or "").strip()
            contract_type_hint = arguments.get("contractType")
            hint = ""
            if contract_type_hint is not None:
                hint = str(contract_type_hint).strip().lower()
                if hint and hint not in _VALID_CONTRACT_TYPES:
                    return _error_payload(
                        f"contractType must be one of: {', '.join(sorted(_VALID_CONTRACT_TYPES))}"
                    )

            if source not in _VALID_SOURCES:
                return _error_payload(f"source must be one of: {', '.join(sorted(_VALID_SOURCES))}")
            if not value:
                return _error_payload("value is required")

            if source == "url":
                document_text = await _fetch_url_text(value)
            else:
                document_text = value[:_MAX_DOCUMENT_CHARS]

            openai_key = api_key or os.environ.get("OPENAI_API_KEY")
            if not openai_key:
                return _error_payload("OPENAI_API_KEY is required for contract analysis")

            hint_line = f"\nExpected contract type hint: {hint}" if hint else ""
            prompt = f"""Analyze the following contract and extract structured metadata.
Return a single JSON object with exactly these keys:
- parties: array of party name strings
- contractType: one of "msa", "sow", "nda", or null if unclear
- effectiveDate: ISO date string or human-readable date, or null
- expiryDate: ISO date string or human-readable date, or null
- renewalNoticeDays: integer days of advance notice required specifically to prevent auto-renewal or to elect non-renewal at term end — NOT termination-for-cause notice, dispute resolution timelines, cure periods, or other general notice clauses; use only the renewal/non-renewal notice period; if no renewal-specific notice period is stated, return null
- autoRenewal: boolean or null
- clauses: array of objects with keys name, present (boolean), summary (string), riskLevel ("low"|"medium"|"high").
  ALWAYS include one object for EACH of these names (use these exact names):
  "Liability Cap", "Termination", "Pricing", "Data Protection", "AI Use Restrictions", "Subprocessors".
  You may include additional clause objects after those six.
  Set present to true ONLY when substantive governing language exists for that topic (rights, obligations, restrictions, or defined terms that control behavior). Set present to false when the topic appears only as a section heading, placeholder, cross-reference, table of contents entry, or passing mention without governing language — summarize accordingly (e.g. that no substantive clause was found). Apply this rule to every clause in the array, not only AI/data use.
  For Subprocessors, present=true when the contract requires approval, notice, flow-downs, or equivalent controls for subprocessors / sub-processors / third-party processors.
- missingClauses: array of important clause names that appear absent (include "Termination" when termination is null, "Pricing and escalation" when pricingEscalation is null, and similar for other null summary fields)
- aiDataUseLanguage: string summary of substantive AI/data use governing language, or null if none exists (a heading or topic reference without governing language does not count)
- liabilityCap: string summary of liability cap/limitation language, or null
- termination: string summary of termination rights, or null
- pricingEscalation: string summary of pricing/escalation terms, or null
- subprocessors: string summary of subprocessor / third-party processor controls, or null
{hint_line}

Contract text:
{document_text}
"""

            client = AsyncOpenAI(api_key=openai_key)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.1,
                max_tokens=4096,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a contract analysis expert. "
                            "Respond only with valid JSON matching the requested schema."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            content = (response.choices[0].message.content or "").strip()
            if not content:
                return _error_payload("LLM returned an empty response")

            parsed = json.loads(content)
            result = _normalize_analysis(parsed)
            return json.dumps(result, ensure_ascii=False)
        except json.JSONDecodeError as exc:
            return _error_payload(f"Failed to parse LLM JSON: {exc}")
        except Exception as exc:
            return _error_payload(str(exc))
