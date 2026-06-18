"""Governance helpers: escalation mapping and identity matching."""

from __future__ import annotations

from typing import Any, Optional

from schemas.context_jobs_model import ContextJobModel

# Prototype UI labels ↔ backend runtime values
ESCALATION_TO_BACKEND = {
    "notify": "always_review",
    "pause": "on_failure",
    "reject": "always_review",
    "always_review": "always_review",
    "never": "never",
    "on_failure": "on_failure",
}


def normalize_escalation_policy(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = str(value).strip().lower()
    return ESCALATION_TO_BACKEND.get(key, key)


def suggest_identity_matches(job: ContextJobModel, query: str) -> list[dict[str, Any]]:
    """Basic glossary/relationship matching suggestions."""
    q = (query or "").strip().lower()
    if not q:
        return []
    suggestions: list[dict[str, Any]] = []
    for term in job.glossary_terms or []:
        if not isinstance(term, dict):
            continue
        name = str(term.get("term") or "").lower()
        syns = [str(s).lower() for s in (term.get("synonyms") or [])]
        if q in name or name in q or any(q in s or s in q for s in syns):
            suggestions.append(
                {
                    "type": "glossary_term",
                    "term": term.get("term"),
                    "definition": term.get("definition"),
                    "confidence": "high" if q == name else "medium",
                }
            )
    for rel in job.relationships or []:
        if not isinstance(rel, dict):
            continue
        from_t = str(rel.get("fromTerm") or rel.get("from_term") or "").lower()
        to_t = str(rel.get("toTerm") or rel.get("to_term") or "").lower()
        if q in from_t or q in to_t:
            suggestions.append(
                {
                    "type": "relationship",
                    "fromTerm": rel.get("fromTerm") or rel.get("from_term"),
                    "relation": rel.get("relation"),
                    "toTerm": rel.get("toTerm") or rel.get("to_term"),
                    "confidence": "medium",
                }
            )
    return suggestions[:20]
