"""Persist and retrieve full-text canonical contracts for amendment fidelity."""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from schemas.canonical_contract_model import CanonicalContractModel

logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def persist_canonical(
    db: Session,
    owner: str,
    text: str,
    *,
    source_doc_id: str | None = None,
    contract_id: str | None = None,
    job_id: UUID | None = None,
    source_type: str = "jet_ingest",
    metadata: dict[str, Any] | None = None,
) -> CanonicalContractModel:
    """Upsert a canonical contract by (owner, source_doc_id). Skip write if hash unchanged."""
    content_hash = _sha256(text)

    existing: CanonicalContractModel | None = None
    if source_doc_id:
        existing = (
            db.query(CanonicalContractModel)
            .filter(
                CanonicalContractModel.owner == owner,
                CanonicalContractModel.source_doc_id == source_doc_id,
            )
            .first()
        )

    if existing:
        if existing.content_hash == content_hash:
            dirty = False
            if job_id and existing.job_id != job_id:
                existing.job_id = job_id
                dirty = True
            if contract_id and existing.contract_id != contract_id:
                existing.contract_id = contract_id
                dirty = True
            if dirty:
                db.add(existing)
                db.commit()
                db.refresh(existing)
            return existing
        existing.text = text
        existing.content_hash = content_hash
        existing.source_type = source_type
        if contract_id:
            existing.contract_id = contract_id
        if job_id:
            existing.job_id = job_id
        if metadata is not None:
            existing.metadata_ = metadata
        db.add(existing)
        db.commit()
        db.refresh(existing)
        logger.info("Updated canonical contract %s for owner=%s", source_doc_id, owner)
        return existing

    row = CanonicalContractModel(
        owner=owner,
        job_id=job_id,
        source_doc_id=source_doc_id,
        contract_id=contract_id,
        text=text,
        content_hash=content_hash,
        source_type=source_type,
        metadata_=metadata,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("Persisted canonical contract %s for owner=%s", source_doc_id, owner)
    return row


def load_canonical_for_job(db: Session, owner: str, job_id: UUID) -> str | None:
    """Find canonical contract text by the job that ingested it."""
    row = (
        db.query(CanonicalContractModel)
        .filter(
            CanonicalContractModel.owner == owner,
            CanonicalContractModel.job_id == job_id,
        )
        .order_by(CanonicalContractModel.updated_at.desc())
        .first()
    )
    return row.text if row else None


def load_canonical_by_contract_id(db: Session, owner: str, contract_id: str) -> str | None:
    """Find canonical contract text by contract identifier."""
    row = (
        db.query(CanonicalContractModel)
        .filter(
            CanonicalContractModel.owner == owner,
            CanonicalContractModel.contract_id == contract_id,
        )
        .order_by(CanonicalContractModel.updated_at.desc())
        .first()
    )
    return row.text if row else None


def load_canonical_by_source_doc_id(db: Session, owner: str, source_doc_id: str) -> str | None:
    """Find canonical contract text by source document identifier."""
    row = (
        db.query(CanonicalContractModel)
        .filter(
            CanonicalContractModel.owner == owner,
            CanonicalContractModel.source_doc_id == source_doc_id,
        )
        .first()
    )
    return row.text if row else None


def load_canonical_by_policy_id(db: Session, owner: str, policy_id: str) -> str | None:
    """Find ingested policy text by policyId (column or metadata) or contract_id."""
    needle = (policy_id or "").strip()
    if not needle:
        return None

    by_id = load_canonical_by_contract_id(db, owner, needle)
    if by_id:
        return by_id

    rows = (
        db.query(CanonicalContractModel)
        .filter(CanonicalContractModel.owner == owner)
        .order_by(CanonicalContractModel.updated_at.desc())
        .limit(80)
        .all()
    )
    upper = needle.upper()
    for row in rows:
        meta = row.metadata_ if isinstance(row.metadata_, dict) else {}
        candidates = (
            row.contract_id,
            meta.get("policyId"),
            meta.get("policy_id"),
        )
        if any(str(item or "").strip().upper() == upper for item in candidates):
            return row.text
        head = (row.text or "")[:1200]
        doc_type = str(meta.get("documentType") or meta.get("document_type") or "").lower()
        if upper not in head.upper():
            continue
        if doc_type == "policy" or "policy id" in head.lower():
            return row.text
    return None


def load_canonical_contract_for_job(db: Session, owner: str, job_id: UUID) -> str | None:
    """Job-scoped canonical text, skipping policy documents."""
    rows = (
        db.query(CanonicalContractModel)
        .filter(
            CanonicalContractModel.owner == owner,
            CanonicalContractModel.job_id == job_id,
        )
        .order_by(CanonicalContractModel.updated_at.desc())
        .limit(20)
        .all()
    )
    for row in rows:
        meta = row.metadata_ if isinstance(row.metadata_, dict) else {}
        doc_type = str(meta.get("documentType") or meta.get("document_type") or "").lower()
        if doc_type == "policy":
            continue
        cid = str(row.contract_id or "")
        if cid.upper().startswith("POL-") or "-PROC-" in cid.upper():
            continue
        if row.text and len(row.text.strip()) >= 200:
            return row.text
    return None
