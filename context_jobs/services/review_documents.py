"""Load full trusted contract + policy text for contract_review runs.

Chunk retrieval still *selects* which documents apply. This module loads those
documents in full so the reviewer is not scoring a 24-chunk sample.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from context_jobs.retrieval.trusted_sources import normalize_trusted_sources
from context_jobs.services.canonical_contract import (
    load_canonical_by_contract_id,
    load_canonical_by_policy_id,
    load_canonical_contract_for_job,
)
from schemas.context_jobs_model import ContextJobModel

_MAX_REVIEW_DOC_CHARS = 80_000


def _looks_like_policy_id(value: str) -> bool:
    upper = (value or "").strip().upper()
    if not upper:
        return False
    return upper.startswith("POL-") or upper.startswith("POLICY-") or "-PROC-" in upper


def _append_unique(bucket: list[str], value: str) -> None:
    text = (value or "").strip()
    if not text:
        return
    upper = text.upper()
    if any(existing.upper() == upper for existing in bucket):
        return
    bucket.append(text.upper())


def merge_review_scope_hints(
    job: ContextJobModel,
    retrieval_hints: dict[str, Any] | None,
) -> dict[str, Any]:
    """Copy contractId / policyId from trusted sources; keep policy IDs out of contractIds."""
    hints = dict(retrieval_hints or {})
    contract_ids = [str(x).strip() for x in (hints.get("contractIds") or []) if str(x).strip()]
    policy_ids = [str(x).strip() for x in (hints.get("policyIds") or []) if str(x).strip()]

    for rule in normalize_trusted_sources(job.trusted_sources):
        key = str(rule.get("key") or "").strip().lower()
        value = str(rule.get("value") or "").strip()
        if not value:
            continue
        if key in {"policyid", "policy_id"}:
            _append_unique(policy_ids, value)
        elif key in {"contractid", "contract_id"}:
            _append_unique(contract_ids, value)

    split_contract: list[str] = []
    for cid in contract_ids:
        if _looks_like_policy_id(cid):
            _append_unique(policy_ids, cid)
        else:
            _append_unique(split_contract, cid)

    if split_contract:
        hints["contractIds"] = split_contract
    else:
        hints.pop("contractIds", None)
    if policy_ids:
        hints["policyIds"] = policy_ids
    else:
        hints.pop("policyIds", None)
    return hints


@dataclass
class ReviewDocumentBundle:
    contract_text: str | None = None
    contract_id: str | None = None
    contract_method: str | None = None
    policy_text: str | None = None
    policy_id: str | None = None
    policy_method: str | None = None

    @property
    def has_contract(self) -> bool:
        return bool(self.contract_text and self.contract_text.strip())

    @property
    def has_policy(self) -> bool:
        return bool(self.policy_text and self.policy_text.strip())


def _clip(text: str | None) -> str | None:
    if not text or not text.strip():
        return None
    trimmed = text.strip()
    if len(trimmed) > _MAX_REVIEW_DOC_CHARS:
        return trimmed[:_MAX_REVIEW_DOC_CHARS]
    return trimmed


def resolve_review_documents(
    db: Session,
    owner: str,
    job: ContextJobModel,
    retrieval_hints: dict[str, Any] | None,
) -> ReviewDocumentBundle:
    """Resolve full contract and policy text from the canonical store."""
    hints = merge_review_scope_hints(job, retrieval_hints)
    bundle = ReviewDocumentBundle()

    for cid in hints.get("contractIds") or []:
        text = load_canonical_by_contract_id(db, owner, cid)
        if text and len(text.strip()) >= 200:
            bundle.contract_text = _clip(text)
            bundle.contract_id = cid
            bundle.contract_method = "canonical_by_contract_id"
            break

    if not bundle.has_contract:
        text = load_canonical_contract_for_job(db, owner, job.id)
        if text and len(text.strip()) >= 200:
            bundle.contract_text = _clip(text)
            bundle.contract_id = (hints.get("contractIds") or [None])[0]
            bundle.contract_method = "canonical_for_job"

    for pid in hints.get("policyIds") or []:
        text = load_canonical_by_policy_id(db, owner, pid)
        if text and len(text.strip()) >= 200:
            bundle.policy_text = _clip(text)
            bundle.policy_id = pid
            bundle.policy_method = "canonical_by_policy_id"
            break

    return bundle


def build_document_level_rag_context(
    bundle: ReviewDocumentBundle,
    chunk_rag: str,
) -> str:
    """Prefer full documents; keep chunk RAG only for whatever is still missing."""
    parts: list[str] = []
    if bundle.has_contract:
        label = bundle.contract_id or "contract"
        parts.append(f"[source:Canonical contract {label}]\n{bundle.contract_text}")
    if bundle.has_policy:
        label = bundle.policy_id or "policy"
        parts.append(f"[source:Canonical policy {label}]\n{bundle.policy_text}")

    leftover = (chunk_rag or "").strip()
    if not parts:
        return leftover

    if bundle.has_contract and bundle.has_policy:
        return "\n\n---\n\n".join(parts)
    if leftover:
        parts.append(leftover)
    return "\n\n---\n\n".join(parts)


def canonical_source_traces(bundle: ReviewDocumentBundle) -> list[dict[str, Any]]:
    """UI traces so the run still shows which full documents were loaded."""
    events: list[dict[str, Any]] = []
    if bundle.has_contract:
        cid = bundle.contract_id or "contract"
        events.append(
            {
                "sourceId": f"canonical-contract-{cid}",
                "sourceName": f"Canonical contract {cid}",
                "sourceType": "contract",
                "factsCited": 1,
                "trustLevel": "required",
                "lastUpdated": None,
                "freshnessStatus": "current",
                "warnings": [],
                "evidenceStrength": "high",
                "preview": (bundle.contract_text or "")[:1200],
                "metadata": {
                    "contractId": cid,
                    "documentType": "contract",
                    "loadMethod": bundle.contract_method,
                },
            }
        )
    if bundle.has_policy:
        pid = bundle.policy_id or "policy"
        events.append(
            {
                "sourceId": f"canonical-policy-{pid}",
                "sourceName": f"Canonical policy {pid}",
                "sourceType": "policy",
                "factsCited": 1,
                "trustLevel": "required",
                "lastUpdated": None,
                "freshnessStatus": "current",
                "warnings": [],
                "evidenceStrength": "high",
                "preview": (bundle.policy_text or "")[:1200],
                "metadata": {
                    "policyId": pid,
                    "documentType": "policy",
                    "loadMethod": bundle.policy_method,
                },
            }
        )
    return events
