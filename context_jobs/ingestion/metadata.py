"""Procurement document metadata — normalize at ingest, match at retrieval."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from context_jobs.ingestion.metadata_inference import normalize_vendor_id

_CONTRACT_ID_RE = re.compile(
    r"\b([A-Z]{2,}-\d{4}-[A-Z]{2,}-\d{4})\b",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_VENDOR_BEFORE_MSA_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9&.\- ]{1,40}?)\s+(?:MSA|SOW|NDA|Agreement)\b",
    re.IGNORECASE,
)
_VENDOR_CAPITALIZED_MSA_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\-]+)\s+(?:MSA|SOW|NDA|Agreement)\b",
)
_VENDOR_PARTIES_RE = re.compile(
    r"\b(?:and|with)\s+(.+?)\s*\((?:Vendor|Supplier)\)",
    re.IGNORECASE,
)
_PROSE_DATE_RE = re.compile(
    r"\b("
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}"
    r")\b",
    re.IGNORECASE,
)
_EXPIRY_CONTEXT_RE = re.compile(
    r"(?:expiry\s+date|contract\s+expiry|expiration\s+date|expir(?:y|es|ing)|"
    r"expires?\s+on|term\s+end(?:s)?|renewal\s+date|end\s+date)"
    r"[ \t]*(?:[:\-]?[ \t]*)?"
    r"("
    r"(?:20\d{2}-\d{2}-\d{2})|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}"
    r")",
    re.IGNORECASE,
)
_CONTRACT_HEADING_RE = re.compile(
    r"(?:^|\n)\s*((?:MASTER\s+)?(?:SERVICE\s+)?(?:AGREEMENT|CONTRACT)[^\n]{0,100})",
    re.IGNORECASE,
)
_VENDOR_ID_LABEL_RE = re.compile(
    r'\bvendor[_\s-]?id\s*[:=]\s*["\']?([A-Za-z0-9][A-Za-z0-9_-]*)',
    re.IGNORECASE,
)
_CONTRACT_RENEWAL_MARKERS = (
    "master service agreement",
    "msa",
    "statement of work",
    "renewal notice",
    "non-renewal",
    "expiry",
    "expires",
    "term end",
    "contract term",
)
_POLICY_MARKERS = (
    "procurement policy",
    "vendor management policy",
    "issued by:",
    "mandatory clause checklist",
    "renewal management",
    "liability standards",
)

_META_LINE_KEYS = (
    "documentType",
    "contractId",
    "contractName",
    "vendor",
    "vendorId",
    "category",
    "expiryDate",
    "complexityTier",
    "chunkIndex",
    "sourceDocId",
)

_VENDOR_PROFILE_RISK_TIERS = frozenset({"low", "medium", "high"})
_VENDOR_PROFILE_SPEND_TIERS = frozenset({"1", "2", "3"})

_SKIP_VENDOR_TOKENS = frozenset(
    {"the", "this", "active", "supplier", "review", "for", "our", "your"}
)


def _first_contract_id(text: str) -> str | None:
    match = _CONTRACT_ID_RE.search(text or "")
    return match.group(1).upper() if match else None


def _coalesce_str(meta: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = meta.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _client_document_name_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only caller-provided document naming fields; infer everything else."""
    meta = dict(metadata or {})
    doc_name = _coalesce_str(meta, "name", "documentName", "document_name", "title")
    if not doc_name:
        return {}
    return {"name": doc_name, "title": doc_name}


def _normalize_vendor_profile_metadata(
    meta: dict[str, Any],
    *,
    doc_id: str | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    """Canonical vendor_profile metadata stored on each vector chunk."""
    _ = text
    meta = dict(meta)
    meta["documentType"] = "vendor_profile"

    vendor_id = _coalesce_str(meta, "vendorId", "vendor_id")
    if vendor_id:
        normalized_id = normalize_vendor_id(vendor_id)
        if normalized_id:
            meta["vendorId"] = normalized_id

    vendor_name = _coalesce_str(meta, "vendorName", "vendor_name", "name", "title")
    if vendor_name:
        meta["vendorName"] = vendor_name
        meta["name"] = vendor_name
        meta["title"] = vendor_name

    capabilities = meta.get("capabilities")
    if isinstance(capabilities, list):
        meta["capabilities"] = [str(item).strip() for item in capabilities if str(item).strip()]
    elif capabilities is not None:
        meta["capabilities"] = []

    risk_tier = (_coalesce_str(meta, "riskTier", "risk_tier") or "").lower()
    if risk_tier in _VENDOR_PROFILE_RISK_TIERS:
        meta["riskTier"] = risk_tier

    spend_tier = _coalesce_str(meta, "spendTier", "spend_tier")
    if spend_tier in _VENDOR_PROFILE_SPEND_TIERS:
        meta["spendTier"] = spend_tier

    linked = meta.get("linkedContractIds") or meta.get("linked_contract_ids")
    if isinstance(linked, list):
        meta["linkedContractIds"] = [
            str(item).strip().upper() for item in linked if str(item).strip()
        ]

    if doc_id:
        meta.setdefault("source_doc_id", doc_id)

    label_parts = [part for part in (vendor_name, vendor_id) if part]
    label = " | ".join(label_parts) if label_parts else "Vendor Profile"
    meta.setdefault("file", label)
    meta.setdefault("source", label)
    return meta


def _normalize_date(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if _ISO_DATE_RE.fullmatch(raw):
        return raw
    for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _extract_expiry_date(text: str) -> str | None:
    sample = text or ""
    for match in _EXPIRY_CONTEXT_RE.finditer(sample[:8000]):
        normalized = _normalize_date(match.group(1))
        if normalized:
            return normalized
    prose_dates = [_normalize_date(m.group(1)) for m in _PROSE_DATE_RE.finditer(sample[:8000])]
    prose_dates = [d for d in prose_dates if d]
    return prose_dates[-1] if prose_dates else None


def _extract_vendor(text: str) -> str | None:
    sample = text or ""
    party_match = _VENDOR_PARTIES_RE.search(sample[:3000])
    if party_match:
        vendor = re.sub(r"\s+", " ", party_match.group(1)).strip(" .,-")
        if len(vendor) >= 3:
            return vendor
    for pattern in (_VENDOR_CAPITALIZED_MSA_RE, _VENDOR_BEFORE_MSA_RE):
        match = pattern.search(sample[:3000])
        if not match:
            continue
        vendor = match.group(1).strip()
        if vendor.lower() in {"master service", "service", "agreement"}:
            continue
        if len(vendor) >= 3 and vendor.lower() not in _SKIP_VENDOR_TOKENS:
            return vendor
    return None


def _extract_contract_name(text: str, vendor: str | None = None) -> str | None:
    sample = (text or "")[:4000]
    heading = _CONTRACT_HEADING_RE.search(sample)
    if heading:
        title = re.sub(r"\s+", " ", heading.group(1)).strip(" -:")
        if len(title) >= 8:
            return title
    if vendor:
        msa = _VENDOR_CAPITALIZED_MSA_RE.search(sample) or _VENDOR_BEFORE_MSA_RE.search(sample)
        if msa:
            return f"{vendor} {msa.group(0).split()[-1].upper()}"
        return f"{vendor} Agreement"
    return None


def _extract_document_name(text: str) -> str | None:
    for line in (text or "").splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip(" -:\t")
        if len(cleaned) >= 8:
            return cleaned[:120]
    return None


def _looks_like_policy(text: str, meta: dict[str, Any]) -> bool:
    sample = " ".join(
        str(part or "")
        for part in (
            text,
            meta.get("name"),
            meta.get("title"),
            meta.get("documentName"),
            meta.get("document_name"),
        )
    ).lower()
    return any(marker in sample for marker in _POLICY_MARKERS)


def _looks_like_contract(text: str, meta: dict[str, Any]) -> bool:
    document_type = (_coalesce_str(meta, "documentType", "document_type", "sourceType") or "").lower()
    if document_type in {"contract", "msa", "sow", "nda", "agreement"}:
        return True
    sample = (text or "").lower()
    return any(marker in sample for marker in _CONTRACT_RENEWAL_MARKERS) or bool(_first_contract_id(text or ""))


def infer_contract_metadata_from_text(text: str) -> dict[str, Any]:
    """Infer contract renewal fields from document body when ingest metadata is sparse."""
    inferred: dict[str, Any] = {}
    contract_id = _first_contract_id(text)
    if contract_id:
        inferred["contractId"] = contract_id

    vendor = _extract_vendor(text)
    if vendor:
        inferred["vendor"] = vendor

    expiry = _extract_expiry_date(text)
    if expiry:
        inferred["expiryDate"] = expiry

    contract_name = _extract_contract_name(text, vendor)
    if contract_name:
        inferred["contractName"] = contract_name
        inferred.setdefault("title", contract_name)

    if inferred:
        inferred.setdefault("documentType", "contract")
    return inferred


def source_label_from_metadata(meta: dict[str, Any] | None, doc_id: str | None = None) -> str:
    """Human-readable retrieval source label (replaces generic Workspace Knowledge)."""
    meta = meta or {}
    contract_id = _coalesce_str(meta, "contractId", "contract_id")
    contract_name = _coalesce_str(meta, "title", "name", "contractName", "contract_name")
    vendor = _coalesce_str(meta, "vendor")
    chunk_index = meta.get("chunk_index")
    if chunk_index is None:
        chunk_index = meta.get("chunkIndex")

    parts: list[str] = []
    if contract_name:
        parts.append(contract_name)
    elif contract_id:
        parts.append(contract_id)
    elif doc_id:
        parts.append(str(doc_id))

    if contract_id and contract_id not in parts:
        parts.append(contract_id)
    if vendor and vendor not in parts:
        parts.append(vendor)

    label = " | ".join(parts) if parts else "Workspace Knowledge"
    if chunk_index is not None:
        try:
            label = f"{label}#chunk-{int(chunk_index)}"
        except (TypeError, ValueError):
            pass
    return label


def normalize_document_metadata(
    metadata: dict[str, Any] | None,
    *,
    doc_id: str | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    """
    Canonical metadata for vector upsert (see JPO spec §4.5).

    Structured fields are normally supplied by LLM inference before this runs;
    regex heuristics fill gaps when inference left a field empty.
    """
    meta = dict(metadata or {})
    if (meta.get("documentType") or "").lower() == "vendor_profile":
        return _normalize_vendor_profile_metadata(meta, doc_id=doc_id, text=text)

    document_name = _coalesce_str(meta, "name", "title") or _extract_document_name(text or "")
    if document_name:
        meta["name"] = document_name
        meta["title"] = document_name

    is_policy = _looks_like_policy(text or "", meta)
    if text and not is_policy and _looks_like_contract(text, meta):
        for key, value in infer_contract_metadata_from_text(text).items():
            meta.setdefault(key, value)

    if is_policy:
        meta.setdefault("documentType", "policy")
    elif _looks_like_contract(text or "", meta):
        meta.setdefault("documentType", "contract")

    contract_id = _coalesce_str(meta, "contractId", "contract_id")
    if contract_id:
        meta["contractId"] = contract_id.upper()

    contract_name = _coalesce_str(meta, "contractName", "contract_name", "title", "name")
    if contract_name:
        meta["contractName"] = contract_name
        meta.setdefault("title", contract_name)

    vendor = _coalesce_str(meta, "vendor", "vendorName", "vendor_name")
    if vendor:
        meta["vendor"] = vendor
        meta.setdefault("vendorName", vendor)

    vendor_id = normalize_vendor_id(_coalesce_str(meta, "vendorId", "vendor_id"))
    if not vendor_id and vendor:
        vendor_id = normalize_vendor_id(vendor)
    if vendor_id:
        meta["vendorId"] = vendor_id

    expiry = _coalesce_str(meta, "expiryDate", "expiry_date")
    if expiry:
        normalized_expiry = _normalize_date(expiry)
        meta["expiryDate"] = normalized_expiry or expiry

    category = _coalesce_str(meta, "category")
    if category:
        meta["category"] = category

    tier = _coalesce_str(meta, "complexityTier", "complexity_tier")
    if tier:
        meta["complexityTier"] = tier

    if doc_id:
        meta.setdefault("source_doc_id", doc_id)

    label = source_label_from_metadata(meta, doc_id)
    meta.setdefault("file", label)
    meta.setdefault("source", label)
    return meta


def extract_retrieval_hints(text: str) -> dict[str, Any]:
    """Pull contract scope signals from goal + userRequest for retrieval filtering."""
    sample = text or ""
    hints: dict[str, Any] = {}

    contract_ids = sorted({m.group(1).upper() for m in _CONTRACT_ID_RE.finditer(sample)})
    if contract_ids:
        hints["contractIds"] = contract_ids

    vendors: list[str] = []
    for match in _VENDOR_CAPITALIZED_MSA_RE.finditer(sample):
        name = match.group(1).strip()
        if len(name) >= 3:
            vendors.append(name)
    if not vendors:
        for match in _VENDOR_BEFORE_MSA_RE.finditer(sample):
            name = match.group(1).strip()
            if len(name) >= 3 and name.lower() not in _SKIP_VENDOR_TOKENS:
                vendors.append(name)
    if vendors:
        hints["vendors"] = list(dict.fromkeys(vendors))

    vendor_ids: list[str] = []
    for match in _VENDOR_ID_LABEL_RE.finditer(sample):
        normalized = normalize_vendor_id(match.group(1))
        if normalized:
            vendor_ids.append(normalized)
    for vendor in vendors:
        normalized = normalize_vendor_id(vendor)
        if normalized and normalized not in vendor_ids:
            vendor_ids.append(normalized)
    if vendor_ids:
        hints["vendorIds"] = list(dict.fromkeys(vendor_ids))

    contract_names: list[str] = []
    for match in _VENDOR_CAPITALIZED_MSA_RE.finditer(sample):
        contract_names.append(match.group(0).strip())
    for match in _CONTRACT_HEADING_RE.finditer(sample):
        title = re.sub(r"\s+", " ", match.group(1)).strip(" -:")
        if len(title) >= 8:
            contract_names.append(title)
    if contract_names:
        hints["contractNames"] = list(dict.fromkeys(contract_names))

    expiry_dates: list[str] = []
    for match in _EXPIRY_CONTEXT_RE.finditer(sample):
        normalized = _normalize_date(match.group(1))
        if normalized:
            expiry_dates.append(normalized)
    for match in _PROSE_DATE_RE.finditer(sample):
        if re.search(r"expir|renewal|term", sample[max(0, match.start() - 40) : match.start()], re.I):
            normalized = _normalize_date(match.group(1))
            if normalized:
                expiry_dates.append(normalized)
    for match in _ISO_DATE_RE.finditer(sample):
        expiry_dates.append(match.group(1))
    if expiry_dates:
        hints["expiryDates"] = list(dict.fromkeys(expiry_dates))

    if any(
        token in sample.lower()
        for token in ("contract renewal", "renewal review", "renewal risk", "expiring")
    ):
        hints["contractRenewal"] = True

    return hints


def _meta_blob(meta: dict[str, Any]) -> str:
    parts = [
        str(meta.get(key) or "")
        for key in (
            "contractId",
            "contract_id",
            "contractName",
            "contract_name",
            "vendor",
            "title",
            "file",
            "source",
            "expiryDate",
            "expiry_date",
            "preview",
            "text",
        )
    ]
    return " ".join(parts).lower()


def metadata_match_score(
    meta: dict[str, Any] | None,
    preview: str,
    hints: dict[str, Any],
) -> float:
    """Higher = better match to scoped hints; 0.5 neutral when no hints."""
    if not hints:
        return 0.5

    meta = meta or {}
    blob = _meta_blob(meta) + " " + (preview or "").lower()
    score = 0.0

    for cid in hints.get("contractIds") or []:
        if cid.lower() in blob:
            score += 3.0

    for vid in hints.get("vendorIds") or []:
        meta_vendor_id = normalize_vendor_id(str(meta.get("vendorId") or ""))
        if meta_vendor_id and meta_vendor_id == vid:
            score += 3.0
        elif vid.lower() in blob:
            score += 2.0

    for vendor in hints.get("vendors") or []:
        if vendor.lower() in blob:
            score += 1.5

    for name in hints.get("contractNames") or []:
        token = name.lower()
        if token in blob or any(part.lower() in blob for part in name.split() if len(part) > 3):
            score += 1.0

    for date in hints.get("expiryDates") or []:
        if date in blob:
            score += 1.0

    doc_type = (meta.get("documentType") or meta.get("document_type") or "").lower()
    if doc_type == "policy" and (hints.get("contractIds") or hints.get("contractRenewal")):
        score -= 2.0

    if hints.get("contractRenewal") and doc_type == "contract":
        score += 0.5

    return score


def metadata_matches_hints(
    meta: dict[str, Any] | None,
    preview: str,
    hints: dict[str, Any],
    *,
    min_score: float = 1.0,
) -> bool:
    scoped = bool(
        hints.get("contractIds")
        or hints.get("vendorIds")
        or hints.get("vendors")
        or hints.get("contractNames")
        or hints.get("expiryDates")
    )
    if not hints or not scoped:
        return True
    return metadata_match_score(meta, preview, hints) >= min_score


def _contract_vendor_filter_candidates(hints: dict[str, Any]) -> list[str]:
    """Ordered vendorId values for metadata-only contract chunk retrieval."""
    candidates: list[str] = []
    for vid in hints.get("vendorIds") or []:
        normalized = normalize_vendor_id(str(vid))
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    for vendor in hints.get("vendors") or []:
        normalized = normalize_vendor_id(vendor)
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return candidates


def resolve_contract_vendor_id_for_filter(hints: dict[str, Any]) -> str | None:
    """Primary vendorId for metadata-only Pinecone contract retrieval."""
    candidates = _contract_vendor_filter_candidates(hints)
    return candidates[0] if candidates else None


def build_contract_vendor_metadata_filter(hints: dict[str, Any]) -> dict[str, Any] | None:
    """
    Pinecone metadata filter on vendorId for contract-scoped retrieval.

    vendorId is inferred at ingestion (LLM + normalization) and stored on every chunk.
    """
    vendor_id = resolve_contract_vendor_id_for_filter(hints)
    if not vendor_id:
        return None
    return {"vendorId": {"$eq": vendor_id}}


# Backward-compatible aliases used by retrieval events.
resolve_contract_name_for_filter = resolve_contract_vendor_id_for_filter
build_contract_name_metadata_filter = build_contract_vendor_metadata_filter


def build_pinecone_metadata_filter(hints: dict[str, Any]) -> dict[str, Any] | None:
    """Pinecone filter for contract-scoped retrieval from prompt hints."""
    clauses: list[dict[str, Any]] = []

    contract_ids = hints.get("contractIds") or []
    if len(contract_ids) == 1:
        clauses.append({"contractId": {"$eq": contract_ids[0]}})
    elif len(contract_ids) > 1:
        clauses.append({"$or": [{"contractId": {"$eq": cid}} for cid in contract_ids]})

    vendors = hints.get("vendors") or []
    if len(vendors) == 1 and not contract_ids:
        clauses.append({"vendor": {"$eq": vendors[0]}})

    expiry_dates = hints.get("expiryDates") or []
    if len(expiry_dates) == 1 and not contract_ids:
        clauses.append({"expiryDate": {"$eq": expiry_dates[0]}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def combine_metadata_filters(*filters: dict[str, Any] | None) -> dict[str, Any] | None:
    """Merge Pinecone-style metadata filters with $and."""
    active = [item for item in filters if item]
    if not active:
        return None
    if len(active) == 1:
        return active[0]
    return {"$and": active}


def build_vendor_metadata_filter(vendor_filter: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Pinecone metadata filter for optional retrieval_config.vendorFilter.

    Matches chunks where metadata.vendorId equals vendorFilter.vendorId and/or
    metadata.capabilities overlaps vendorFilter.capabilities.
    """
    if not isinstance(vendor_filter, dict) or not vendor_filter:
        return None

    vendor_id = _coalesce_str(vendor_filter, "vendorId", "vendor_id")
    capabilities = vendor_filter.get("capabilities")
    capability_values = (
        [str(item).strip() for item in capabilities if str(item).strip()]
        if isinstance(capabilities, list)
        else []
    )

    clauses: list[dict[str, Any]] = []
    if vendor_id:
        clauses.append({"vendorId": {"$eq": vendor_id}})
    if capability_values:
        clauses.append({"capabilities": {"$in": capability_values}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses}


def format_context_block_header(meta: dict[str, Any] | None, match_id: str | None = None) -> str:
    """Source + meta lines prepended to each RAG block."""
    meta = meta or {}
    source = source_label_from_metadata(meta, meta.get("source_doc_id"))
    lines = [f"[source:{source}]"]

    meta_pairs: list[str] = []
    for key, aliases in (
        ("documentType", ("documentType", "document_type")),
        ("contractId", ("contractId", "contract_id")),
        ("contractName", ("title", "name", "contractName", "contract_name")),
        ("vendor", ("vendor",)),
        ("vendorId", ("vendorId", "vendor_id")),
        ("expiryDate", ("expiryDate", "expiry_date")),
        ("category", ("category",)),
    ):
        value = _coalesce_str(meta, *aliases)
        if value:
            meta_pairs.append(f"{key}={value}")

    if match_id:
        meta_pairs.append(f"chunkId={match_id}")
    chunk_index = meta.get("chunk_index")
    if chunk_index is None:
        chunk_index = meta.get("chunkIndex")
    if chunk_index is not None:
        meta_pairs.append(f"chunkIndex={chunk_index}")

    if meta_pairs:
        lines.append(f"[meta:{';'.join(meta_pairs)}]")
    return "\n".join(lines)


def parse_meta_from_context_block(block: str) -> dict[str, str]:
    """Parse [meta:k=v;...] from a retrieved context block."""
    parsed: dict[str, str] = {}
    for line in (block or "").splitlines():
        line = line.strip()
        if not line.lower().startswith("[meta:"):
            continue
        inner = line[6:].rstrip("]").strip()
        for pair in inner.split(";"):
            if "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            parsed[key.strip()] = value.strip()
        break
    return parsed


def trace_metadata_from_match(meta: dict[str, Any] | None, match_id: str | None = None) -> dict[str, Any]:
    """Metadata fields attached to retrieval_events / source_trace_events."""
    meta = meta or {}
    out: dict[str, Any] = {}
    for key in _META_LINE_KEYS:
        aliases = (key, key.replace("Id", "_id") if "Id" in key else key)
        if key == "contractName":
            aliases = ("title", "name", "contractName", "contract_name")
        value = _coalesce_str(meta, *aliases)
        if value:
            out[key] = value
    if match_id:
        out["chunkId"] = match_id
    chunk_index = meta.get("chunk_index")
    if chunk_index is None:
        chunk_index = meta.get("chunkIndex")
    if chunk_index is not None:
        out["chunkIndex"] = chunk_index
    return out
