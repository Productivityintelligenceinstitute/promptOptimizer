"""LLM-based document metadata extraction before vector embedding."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_VALID_DOCUMENT_TYPES = frozenset({"contract", "policy", "rate_card", "vendor_profile"})
_VALID_RISK_TIERS = frozenset({"low", "medium", "high"})
_VALID_SPEND_TIERS = frozenset({"1", "2", "3"})

_SYSTEM_PROMPT = """You extract structured metadata from procurement documents for vector search.

Return a single JSON object with ONLY these keys (omit keys or use empty values when not found in the document):
- documentType: one of contract, policy, rate_card, vendor_profile, or ""
- vendorId: stable lowercase identifier (use explicit ID from the document when present; otherwise slug the vendor legal name with underscores, e.g. salesforce, oracle_cloud)
- vendorName: vendor legal or trading name
- vendor: same as vendorName when this is a contract (party name)
- contractId: contract reference code if present (e.g. SF-2022-MSA-0047)
- contractName: full contract title or agreement name
- expiryDate: contract expiry as YYYY-MM-DD when clearly stated
- capabilities: array of capability strings for vendor profiles
- riskTier: low, medium, or high for vendor profiles
- spendTier: 1, 2, or 3 for vendor profiles
- linkedContractIds: array of related contract reference codes

Rules:
- Only include values explicitly supported by the document text.
- Do not guess dates, IDs, or capabilities.
- Use empty string or empty array when unknown.
- Return valid JSON only."""


def _empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return not value
    return False


_EXPLICIT_VENDOR_ID_RE = re.compile(
    r"^[A-Z]{2,}[-_][A-Z0-9][A-Z0-9_-]*$",
    re.IGNORECASE,
)
_LEGAL_ENTITY_SUFFIX_RE = re.compile(
    r"(?:\s+(?:inc|incorporated|ltd|limited|llc|corp|corporation|co|ag|gmbh|plc)\.?)+$",
    re.IGNORECASE,
)


def _strip_legal_entity_suffixes(name: str) -> str:
    text = name.strip()
    while True:
        stripped = _LEGAL_ENTITY_SUFFIX_RE.sub("", text).strip()
        if stripped == text:
            return text
        text = stripped


def normalize_vendor_id(value: str | None) -> str | None:
    """Canonical vendorId slug stored on vector metadata and used for retrieval filters."""
    raw = (value or "").strip()
    if not raw:
        return None
    if _EXPLICIT_VENDOR_ID_RE.match(raw):
        slug = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
        return slug or None
    name = _strip_legal_entity_suffixes(raw)
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or None


def _sanitize_inferred_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}

    doc_type = str(raw.get("documentType") or "").strip().lower()
    if doc_type in _VALID_DOCUMENT_TYPES:
        out["documentType"] = doc_type

    vendor_id = normalize_vendor_id(str(raw.get("vendorId") or ""))
    if vendor_id:
        out["vendorId"] = vendor_id

    for key in ("vendorName", "vendor", "contractName"):
        value = str(raw.get(key) or "").strip()
        if value:
            out[key] = value

    contract_id = str(raw.get("contractId") or "").strip().upper()
    if contract_id:
        out["contractId"] = contract_id

    expiry = str(raw.get("expiryDate") or "").strip()
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", expiry):
        out["expiryDate"] = expiry

    capabilities = raw.get("capabilities")
    if isinstance(capabilities, list):
        cleaned = [str(item).strip() for item in capabilities if str(item).strip()]
        if cleaned:
            out["capabilities"] = cleaned

    risk_tier = str(raw.get("riskTier") or "").strip().lower()
    if risk_tier in _VALID_RISK_TIERS:
        out["riskTier"] = risk_tier

    spend_tier = str(raw.get("spendTier") or "").strip()
    if spend_tier in _VALID_SPEND_TIERS:
        out["spendTier"] = spend_tier

    linked = raw.get("linkedContractIds")
    if isinstance(linked, list):
        cleaned = [str(item).strip().upper() for item in linked if str(item).strip()]
        if cleaned:
            out["linkedContractIds"] = cleaned

    if out.get("documentType") == "contract" and not out.get("vendorId"):
        derived = normalize_vendor_id(out.get("vendorName") or out.get("vendor"))
        if derived:
            out["vendorId"] = derived

    return out


def merge_inferred_metadata(
    client_meta: dict[str, Any] | None,
    inferred: dict[str, Any] | None,
) -> dict[str, Any]:
    """Apply LLM inference, then overlay optional client document name/title."""
    merged: dict[str, Any] = {}
    for key, value in (inferred or {}).items():
        if not _empty(value):
            merged[key] = value

    client = dict(client_meta or {})
    doc_name = (
        client.get("name")
        or client.get("title")
        or client.get("documentName")
        or client.get("document_name")
    )
    if doc_name and str(doc_name).strip():
        title = str(doc_name).strip()
        merged["name"] = title
        merged["title"] = title
    return merged


def infer_document_metadata_from_llm(
    text: str,
    *,
    title_hint: str | None = None,
) -> dict[str, Any]:
    """Extract procurement metadata with gpt-4o-mini; returns {} on failure."""
    sample = (text or "").strip()
    if not sample:
        return {}

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set; skipping LLM metadata inference.")
        return {}

    excerpt = sample[:12000]
    hint_line = f"Document title hint: {title_hint}\n\n" if title_hint else ""

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=512,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"{hint_line}Document text:\n{excerpt}",
                },
            ],
        )
        raw = (response.choices[0].message.content or "{}").strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return {}
        return _sanitize_inferred_metadata(parsed)
    except Exception as exc:
        logger.warning("LLM metadata inference failed: %s", exc)
        return {}
