"""Register contracts into the caller's Jet managed KB for expiry monitoring."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from context_jobs.ingestion.ingestion_service import ingest_to_target
from context_jobs.ingestion.target_resolver import resolve_ingestion_target
from context_jobs.managed_jet_kb import ensure_managed_namespace
from context_jobs.workspace import ensure_default_workspace
from schemas.context_jobs_model import ContextJobModel

_VALID_TIERS = frozenset({"low", "medium", "high"})
_CONTRACT_ID_SAFE = re.compile(r"[^A-Z0-9_-]+")


def _normalize_contract_id(raw: str | None) -> str:
    text = (raw or "").strip().upper()
    if text:
        cleaned = _CONTRACT_ID_SAFE.sub("-", text).strip("-")
        if cleaned:
            return cleaned[:80]
    return f"ALERT-{uuid.uuid4().hex[:12].upper()}"


def _parse_expiry(value: str | date) -> date:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        raise ValueError("expiryDate is required (YYYY-MM-DD).")
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError("expiryDate must be YYYY-MM-DD.") from exc


def _resolve_tier(raw: str | None) -> str:
    tier = str(raw or "medium").strip().lower()
    return tier if tier in _VALID_TIERS else "medium"


def _ephemeral_jet_kb_job(db: Session, owner: str) -> ContextJobModel:
    """
    Build an unsaved job shell so resolve_ingestion_target uses the caller's Jet KB.

    Not persisted — only used to select the managed namespace + embedding config.
    """
    ws = ensure_default_workspace(db, owner)
    return ContextJobModel(
        name="__procurement_alert_ingest__",
        status="draft",
        retrieval_mode="jet_kb",
        owner=owner,
        workspace_id=ws.id,
        execution_provider="openai",
        execution_model="gpt-4o-mini",
    )


def register_contract_for_alerts(
    db: Session,
    owner: str,
    *,
    text: str,
    expiry_date: str | date,
    description: str,
    vendor: str | None = None,
    contract_id: str | None = None,
    complexity_tier: str | None = None,
    document_name: str | None = None,
) -> dict[str, Any]:
    """
    Ingest a contract into the caller's Jet managed KB with forced alert metadata.

    Does NOT run the expiry monitor immediately — the scheduled monitor picks it up.
    """
    body = (text or "").strip()
    if not body:
        raise ValueError("Contract text is empty.")

    expiry = _parse_expiry(expiry_date)
    desc = (description or "").strip()
    if not desc:
        raise ValueError("description is required so you can recognize this contract later.")

    vendor_name = (vendor or "").strip() or None
    tier = _resolve_tier(complexity_tier)
    contract_document_id = _normalize_contract_id(contract_id)
    title = (document_name or "").strip() or f"Alert contract {contract_document_id}"
    namespace = ensure_managed_namespace(db, owner)
    ws = ensure_default_workspace(db, owner)

    metadata: dict[str, Any] = {
        "name": title,
        "title": title,
        "documentName": title,
        "documentType": "contract",
        "contractId": contract_document_id,
        "expiryDate": expiry.isoformat(),
        "complexityTier": tier,
        "description": desc,
        "workspace_id": ws.id,
        "workspaceId": ws.id,
        "source": "procurement_alerts_register",
        "registeredAt": datetime.now(timezone.utc).isoformat(),
    }
    if vendor_name:
        metadata["vendor"] = vendor_name
        metadata["vendorName"] = vendor_name

    job = _ephemeral_jet_kb_job(db, owner)
    target = resolve_ingestion_target(db, job)
    result = ingest_to_target(
        target,
        [
            {
                "id": f"alert-{contract_document_id.lower()}",
                "text": body,
                "metadata": metadata,
            }
        ],
        db,
        ingestion_config={"auto_create_target": True},
    )

    if result.status in {"failed", "escalated"} or result.error:
        raise ValueError(result.error or "Contract ingestion failed.")

    return {
        "contractDocumentId": contract_document_id,
        "expiryDate": expiry,
        "vendor": vendor_name,
        "description": desc,
        "complexityTier": tier,
        "namespace": namespace,
        "ingestionStatus": result.status,
        "upsertedCount": int(result.upserted_count or 0),
        "warnings": list(result.warnings or []),
        "message": "Your contract was added. It will show under Alerts when its renewal window opens.",
    }
