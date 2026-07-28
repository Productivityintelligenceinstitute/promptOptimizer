"""Trusted-sources normalization, store-side filters, and post-retrieval matching."""

from __future__ import annotations

from typing import Any


_LEGACY_META_KEYS = ("file", "source", "url", "title", "name", "documentName")
_SAFE_KEY = __import__("re").compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def normalize_trusted_source(raw: Any) -> dict[str, Any] | None:
    """
    Normalize a trusted-source entry.

    Supported shapes:
      {"key": "contractId", "value": "ACME-1"}           # exact match (default op=eq)
      {"key": "file", "value": "msa", "op": "contains"}  # substring match
      {"name": "policy.pdf"}                             # legacy → contains on file/source/url/title
    """
    if not isinstance(raw, dict):
        return None

    key = raw.get("key") or raw.get("metadataKey") or raw.get("metadata_key")
    key = str(key).strip() if key is not None else ""
    value = raw.get("value")
    if value is None:
        value = raw.get("name") or raw.get("label")
    value = str(value).strip() if value is not None else ""
    if not value:
        return None

    op = str(raw.get("op") or raw.get("operator") or "eq").strip().lower()
    if op not in {"eq", "equals", "exact", "contains", "substring"}:
        op = "eq"
    if op in {"equals", "exact"}:
        op = "eq"
    if op == "substring":
        op = "contains"

    out: dict[str, Any] = {
        "value": value,
        "op": op,
    }
    if key:
        if not _SAFE_KEY.match(key):
            return None
        out["key"] = key
    else:
        # Legacy name-only: keep name for UI/validation compatibility.
        out["name"] = value
        out["op"] = "contains"

    trust = raw.get("trustLevel") or raw.get("trust_level")
    if isinstance(trust, str) and trust.strip():
        out["trustLevel"] = trust.strip()
    for copy_key in ("id", "sourceType", "priority", "freshness"):
        if raw.get(copy_key) is not None:
            out[copy_key] = raw[copy_key]
    return out


def normalize_trusted_sources(raw: list[Any] | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        normalized = normalize_trusted_source(item)
        if normalized:
            out.append(normalized)
    return out


def build_trusted_sources_metadata_filter(
    trusted_sources: list[dict] | None,
) -> dict[str, Any] | None:
    """
    Build a store-side Pinecone-dialect filter for exact (eq) keyed rules only.

    Contains / legacy name-only rules are applied in post-filter (substring),
    not at the vector store.
    """
    rules = normalize_trusted_sources(trusted_sources)
    eq_clauses: list[dict[str, Any]] = []
    for rule in rules:
        key = rule.get("key")
        if not key or rule.get("op") != "eq":
            continue
        eq_clauses.append({str(key): {"$eq": rule["value"]}})

    if not eq_clauses:
        return None
    if len(eq_clauses) == 1:
        return eq_clauses[0]
    # Multiple trusted docs → any of them may ground the run.
    return {"$or": eq_clauses}


def _meta_value(meta: dict[str, Any], key: str) -> str:
    raw = meta.get(key)
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple)):
        return " ".join(str(x) for x in raw).lower()
    return str(raw).lower()


def metadata_matches_trusted_rule(meta: dict[str, Any], rule: dict[str, Any]) -> bool:
    value = str(rule.get("value") or "").lower()
    if not value:
        return False
    op = rule.get("op") or "eq"
    key = rule.get("key")

    if key:
        candidate = _meta_value(meta, str(key))
        if op == "contains":
            return bool(candidate) and (value in candidate or candidate in value)
        return candidate == value

    # Legacy: match against common source labels
    haystacks = [_meta_value(meta, k) for k in _LEGACY_META_KEYS]
    haystacks = [h for h in haystacks if h]
    if not haystacks:
        return False
    return any(value in h or h in value for h in haystacks)


def apply_trusted_sources_filter(
    matches: list[Any],
    trusted_sources: list[dict] | None,
    *,
    hard: bool = True,
) -> list[Any]:
    """
    Post-retrieval gate for trusted sources.

    When ``hard`` is True (default) and rules are configured, zero matches stay empty
    (no silent unfilter). Soft fallback remains available for callers that need it.
    """
    rules = normalize_trusted_sources(trusted_sources)
    if not rules:
        return matches

    filtered: list[Any] = []
    for match in matches:
        meta = getattr(match, "metadata", None) or {}
        if not isinstance(meta, dict):
            meta = {}
        if any(metadata_matches_trusted_rule(meta, rule) for rule in rules):
            filtered.append(match)

    if filtered:
        return filtered
    return [] if hard else matches
