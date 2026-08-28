"""Post-execution validation: compare revised contract against canonical source."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class RevisionValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Top-level "1. Scope" and nested "7.4 Upon" / "2.2. Right to Use"
_CLAUSE_ID = re.compile(
    r"(?m)^\s*(?:Section\s+)?(\d+(?:\.\d+){0,3})\.?(?:\s+)(?=[A-Za-z\"'(])",
    re.IGNORECASE,
)
_QUOTED_TERM = re.compile(r'["\u201c]([A-Z][A-Za-z0-9][A-Za-z0-9\s&.,/-]{1,}?)["\u201d]')
# ("Provider") / ("Customer") party labels — not glossary definitions.
_PARTY_PAREN = re.compile(
    r'\(\s*["\u201c]([A-Z][A-Za-z][A-Za-z0-9\s/&-]{0,40})["\u201d]\s*\)'
)
_COVER_END = re.compile(r"(?m)^\s*(?:Section\s+)?1[\.\)]\s+")
# Real identifiers like ACME-MSA-2024-001 or POL-PROC-2025-004 — not "industry-standard".
_CONTRACT_ID = re.compile(r"\b([A-Z]{2,}(?:-[A-Z0-9]{2,}){2,})\b")
# Stop at the jurisdiction name. Do not swallow the next cover-page field
# ("Governing Law: State of Delaware\nGeneral Cap Amount: ...").
_GOVERNING_LAW = re.compile(
    r"(?:"
    r"governed\s+by\s+the\s+laws\s+of(?:\s+the)?|"
    r"Governing\s+Law\s*:(?:\s*the\s+laws\s+of(?:\s+the)?)?"
    r")\s+"
    r"(?:State\s+of\s+)?([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)",
    re.IGNORECASE,
)
_COMMON_QUOTED = {
    "a", "an", "the", "or", "and", "of", "to", "for", "in", "on",
}
_GLOSSARY_SKIP = {
    "as is", "as available", "beta product", "embargoed country",
    "high risk activity", "ofac", "standard terms", "variable",
    "framework terms", "cover page", "key terms", "order form",
}


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def extract_clause_ids(text: str) -> list[str]:
    """Return source clause numbers in document order, de-duplicated."""
    seen: set[str] = set()
    ordered: list[str] = []
    for match in _CLAUSE_ID.finditer(text or ""):
        cid = match.group(1)
        if cid not in seen:
            seen.add(cid)
            ordered.append(cid)
    return ordered


def _clause_sort_key(cid: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in cid.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def format_clause_id_checklist(text: str) -> str:
    ids = extract_clause_ids(text)
    if not ids:
        return ""
    return ", ".join(sorted(ids, key=_clause_sort_key))


def _preamble(text: str) -> str:
    m = _COVER_END.search(text or "")
    return (text or "")[: m.start()] if m else (text or "")[:2000]


def _dedupe_terms(matches: list[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for raw in matches:
        cleaned = raw.strip()
        if len(cleaned) < 3 or cleaned.lower() in _COMMON_QUOTED:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            terms.append(cleaned)
    return terms


def _extract_quoted_terms(text: str) -> list[str]:
    return _dedupe_terms([m.group(1) for m in _QUOTED_TERM.finditer(text or "")])


def _extract_required_labels(text: str) -> list[str]:
    """Party labels and cover-page quoted names only — not the definitions glossary."""
    party = [m.group(1) for m in _PARTY_PAREN.finditer(text or "")]
    cover = [m.group(1) for m in _QUOTED_TERM.finditer(_preamble(text))]
    return _dedupe_terms(party + cover)


def _extract_glossary_terms(text: str) -> list[str]:
    required = {t.lower() for t in _extract_required_labels(text)}
    glossary: list[str] = []
    for term in _extract_quoted_terms(text):
        key = term.lower()
        if key in required or key in _GLOSSARY_SKIP:
            continue
        glossary.append(term)
    return glossary


def _extract_contract_ids(text: str) -> list[str]:
    found = [m.group(1).strip() for m in _CONTRACT_ID.finditer(text or "")]
    return [cid for cid in found if any(ch.isdigit() for ch in cid)]


def _extract_governing_law(text: str) -> str | None:
    m = _GOVERNING_LAW.search(text or "")
    if not m:
        return None
    raw = m.group(1).strip()
    raw = re.split(
        r"\n|General Cap|Non-Renewal|Cover Page|Effective Date|excluding",
        raw,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" ,.;")
    if not raw:
        return None
    return _normalize(raw)


def _word_count(text: str) -> int:
    return len((text or "").split())


def _clause_id_present(cid: str, revised_text: str) -> bool:
    """True if the clause number appears as a numbered heading, not as a stray digit."""
    escaped = re.escape(cid)
    return bool(
        re.search(
            rf"(?m)(?:^|\s)(?:Section\s+)?{escaped}\.?(?:\s|$)",
            revised_text,
            re.IGNORECASE,
        )
    )


def validate_revision(
    source_text: str,
    revised_text: str,
    *,
    locked_fields: dict | None = None,
) -> RevisionValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    source_text = source_text or ""
    revised_text = revised_text or ""

    # 1. Nested + top-level clause numbers (catches dropped 7.4 / 11.8)
    source_ids = extract_clause_ids(source_text)
    if source_ids:
        missing = [cid for cid in source_ids if not _clause_id_present(cid, revised_text)]
        if missing:
            sample = missing[:8]
            errors.append(
                f"Missing {len(missing)} clause number(s) from original: "
                + ", ".join(sample)
            )

    # 2. Party labels + cover-page quoted names (not the definitions glossary)
    source_labels = _extract_required_labels(source_text)
    if source_labels:
        revised_lower = revised_text.lower()
        missing_labels = [t for t in source_labels if t.lower() not in revised_lower]
        if missing_labels:
            errors.append(
                "Missing party label(s) from original: "
                + ", ".join(repr(t) for t in missing_labels[:8])
            )
    glossary = _extract_glossary_terms(source_text)
    if glossary:
        revised_lower = revised_text.lower()
        missing_glossary = [t for t in glossary if t.lower() not in revised_lower]
        if missing_glossary:
            warnings.append(
                "Missing glossary term(s) from original (not blocking): "
                + ", ".join(repr(t) for t in missing_glossary[:8])
            )

    # 3. Contract ID
    source_ids_contract = _extract_contract_ids(source_text)
    if source_ids_contract:
        revised_ids = {cid.lower() for cid in _extract_contract_ids(revised_text)}
        missing_ids = [cid for cid in source_ids_contract if cid.lower() not in revised_ids]
        if missing_ids:
            errors.append(
                "Missing contract ID(s) from original: "
                + ", ".join(repr(cid) for cid in missing_ids)
            )

    # 4. Governing law
    source_law = _extract_governing_law(source_text)
    if source_law:
        revised_law = _extract_governing_law(revised_text)
        if revised_law and revised_law != source_law:
            errors.append(
                f"Governing law changed from {source_law!r} to {revised_law!r}"
            )
        elif not revised_law:
            warnings.append("Governing law clause not found in revised text")

    # 5. Length sanity
    source_wc = _word_count(source_text)
    revised_wc = _word_count(revised_text)
    if source_wc > 0 and revised_wc < source_wc * 0.5:
        errors.append(
            f"Document shrank by more than 50% "
            f"(source={source_wc} words, revised={revised_wc} words)"
        )
    elif source_wc > 0 and revised_wc < source_wc * 0.7:
        warnings.append(
            f"Revised document is significantly shorter than original "
            f"(source={source_wc} words, revised={revised_wc} words)"
        )

    # 6. Locked fields (optional caller-supplied overrides)
    if locked_fields:
        revised_lower = revised_text.lower()
        for field_name, expected_value in locked_fields.items():
            if str(expected_value).lower() not in revised_lower:
                errors.append(
                    f"Locked field {field_name!r} value {expected_value!r} missing from revised text"
                )

    return RevisionValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
