"""Inline knowledgeSources retrieval and hybrid search."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from context_jobs.evidence import is_placeholder_source_name, is_placeholder_source_text
from schemas.context_jobs_model import ContextAssetModel, ContextJobModel


@dataclass
class InlineSourceMatch:
    source_id: str
    source_name: str
    source_type: str
    text: str
    score: float


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _keyword_score(query: str, text: str) -> float:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.0
    t_tokens = _tokenize(text)
    if not t_tokens:
        return 0.0
    overlap = len(q_tokens & t_tokens)
    return overlap / max(len(q_tokens), 1)


def _load_asset_text(db: Session, asset_id: str) -> str:
    try:
        from uuid import UUID

        row = db.query(ContextAssetModel).filter(ContextAssetModel.id == UUID(asset_id)).first()
    except Exception:
        return ""
    if not row:
        return ""
    content = row.content or {}
    if isinstance(content, dict):
        body = content.get("body") or ""
        if body:
            return str(body)
        return str(content)[:4000]
    return str(content)[:4000]


def collect_knowledge_sources(
    job: ContextJobModel,
    db: Session,
) -> list[dict[str, Any]]:
    rc = job.retrieval_config or {}
    sources = list(rc.get("knowledgeSources") or [])
    # Legacy hydration: sources: string[]
    legacy = rc.get("sources") or []
    for i, ref in enumerate(legacy):
        if isinstance(ref, str) and ref.strip():
            sources.append({"id": f"legacy_{i}", "type": "text", "label": ref, "value": ref})
    return [s for s in sources if isinstance(s, dict)]


def retrieve_from_knowledge_sources(
    job: ContextJobModel,
    query: str,
    db: Session,
    max_documents: int = 8,
) -> tuple[str, list[dict], list[dict]]:
    """Return (rag_context, retrieval_events, source_trace_events) from inline sources."""
    sources = collect_knowledge_sources(job, db)
    if not sources:
        return "", [], []

    matches: list[InlineSourceMatch] = []
    for src in sources:
        stype = (src.get("type") or "text").lower()
        label = src.get("label") or src.get("id") or "source"
        value = str(src.get("value") or "")
        text = ""
        if stype == "text":
            text = value
        elif stype == "url":
            text = f"[URL source: {value}]"
        elif stype == "asset":
            text = _load_asset_text(db, value)
        if not text.strip():
            continue
        score = _keyword_score(query, text)
        if score <= 0 and stype == "text":
            score = 0.3  # include pasted text even with weak keyword overlap
        matches.append(
            InlineSourceMatch(
                source_id=str(src.get("id") or label),
                source_name=label,
                source_type=stype,
                text=text[:2000],
                score=score,
            )
        )

    matches.sort(key=lambda m: m.score, reverse=True)
    matches = matches[:max_documents]

    now_iso = datetime.now(timezone.utc).isoformat()
    context_blocks: list[str] = []
    retrieval_events: list[dict] = []
    source_trace_events: list[dict] = []

    for m in matches:
        context_blocks.append(f"[source:{m.source_name}]\n{m.text}")
        retrieval_events.append(
            {
                "query": query,
                "source": m.source_name,
                "resultCount": 1,
                "timestamp": now_iso,
                "origin": "knowledgeSources",
            }
        )
        strength = "strong" if m.score >= 0.5 else "moderate" if m.score >= 0.25 else "weak"
        if is_placeholder_source_name(m.source_name) or is_placeholder_source_text(m.text):
            strength = "informational"
        source_trace_events.append(
            {
                "sourceId": m.source_id,
                "sourceName": m.source_name,
                "sourceType": m.source_type,
                "factsCited": 1,
                "trustLevel": "preferred",
                "freshnessStatus": "current",
                "warnings": [],
                "evidenceStrength": strength,
            }
        )

    rag = "\n\n---\n\n".join(context_blocks)
    return rag, retrieval_events, source_trace_events


def merge_retrieval_results(
    vector_rag: str,
    vector_events: list[dict],
    vector_traces: list[dict],
    inline_rag: str,
    inline_events: list[dict],
    inline_traces: list[dict],
    hybrid: bool,
) -> tuple[str, list[dict], list[dict]]:
    if not hybrid or not inline_rag:
        if inline_rag and not vector_rag.strip():
            return inline_rag, inline_events, inline_traces
        return vector_rag, vector_events, vector_traces
    parts = [p for p in (vector_rag, inline_rag) if p and p.strip()]
    merged_rag = "\n\n---\n\n".join(parts) if parts else "No context retrieved."
    return (
        merged_rag,
        vector_events + inline_events,
        vector_traces + inline_traces,
    )
