"""Contract expiry monitor — scan vector metadata and create procurement alerts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterator

from sqlalchemy.orm import Session

from context_jobs.retrieval.factory import get_retrieval_adapter
from context_jobs.retrieval.metadata_filters import adapter_supports_metadata_filter
from context_jobs.retrieval.security import decrypt_config
from schemas.context_jobs_model import ContextJobModel, ProcurementAlertModel
from schemas.context_vector_connection_model import ContextVectorConnectionModel
from schemas.managed_jet_kb_namespace_model import ManagedJetKbNamespaceModel

logger = logging.getLogger(__name__)

SYSTEM_OWNER = "__system__"
CONTRACT_DOCUMENT_FILTER = {"documentType": {"$eq": "contract"}}
LEAD_MONTHS_BY_TIER = {"low": 6, "medium": 12, "high": 18}
_VALID_COMPLEXITY_TIERS = frozenset(LEAD_MONTHS_BY_TIER.keys())
_SCAN_TOP_K = 10_000


@dataclass(frozen=True)
class ContractDocumentRecord:
    owner: str
    workspace_id: str | None
    contract_document_id: str
    vendor: str | None
    expiry_date: date
    complexity_tier: str
    complexity_tier_defaulted: bool
    lead_months_threshold: int


def _subtract_months(value: date, months: int) -> date:
    year = value.year
    month = value.month - months
    while month <= 0:
        month += 12
        year -= 1
    last_day = _days_in_month(year, month)
    return date(year, month, min(value.day, last_day))


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    first = date(year, month, 1)
    return (next_month - first).days


def _parse_expiry_date(raw: Any) -> date | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _resolve_complexity_tier(raw: Any) -> tuple[str, bool]:
    tier = str(raw or "").strip().lower()
    if tier in _VALID_COMPLEXITY_TIERS:
        return tier, False
    return "medium", True


def _contract_id(meta: dict[str, Any]) -> str | None:
    contract_id = meta.get("contractId") or meta.get("contract_id")
    if contract_id is not None and str(contract_id).strip():
        return str(contract_id).strip().upper()
    return None


def _vendor_display_name(meta: dict[str, Any]) -> str | None:
    for key in ("vendor", "vendorName", "vendor_name"):
        value = meta.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _workspace_id(meta: dict[str, Any]) -> str | None:
    for key in ("workspace_id", "workspaceId"):
        value = meta.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _group_contract_documents(
    matches: list[Any],
    *,
    owner: str,
) -> dict[str, ContractDocumentRecord]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for match in matches:
        meta = dict(getattr(match, "metadata", None) or {})
        doc_type = str(meta.get("documentType") or meta.get("document_type") or "").lower()
        if doc_type != "contract":
            continue

        vector_id = str(getattr(match, "id", "") or "")
        group_key = _contract_id(meta)
        if group_key is None:
            logger.debug(
                "Skipping contract chunk %s for owner %s: missing contractId metadata.",
                vector_id,
                owner,
            )
            continue
        buckets.setdefault(group_key, []).append(meta)

    grouped: dict[str, ContractDocumentRecord] = {}
    for group_key, chunk_metas in buckets.items():
        first_meta = chunk_metas[0]
        expiry_dates: list[date] = []
        for meta in chunk_metas:
            expiry = _parse_expiry_date(meta.get("expiryDate") or meta.get("expiry_date"))
            if expiry is not None:
                expiry_dates.append(expiry)

        if not expiry_dates:
            logger.warning(
                "Skipping contract document %s for owner %s: missing expiryDate metadata.",
                group_key,
                owner,
            )
            continue

        tier, defaulted = _resolve_complexity_tier(
            first_meta.get("complexityTier") or first_meta.get("complexity_tier")
        )
        lead_months = LEAD_MONTHS_BY_TIER[tier]
        grouped[group_key] = ContractDocumentRecord(
            owner=owner,
            workspace_id=_workspace_id(first_meta),
            contract_document_id=group_key,
            vendor=_vendor_display_name(first_meta),
            expiry_date=min(expiry_dates),
            complexity_tier=tier,
            complexity_tier_defaulted=defaulted,
            lead_months_threshold=lead_months,
        )
    return grouped


def _scan_adapter_contracts(adapter: Any, *, owner: str) -> dict[str, ContractDocumentRecord]:
    if not adapter_supports_metadata_filter(adapter):
        provider = getattr(adapter, "provider", "unknown")
        logger.warning(
            "Skipping vector scan for owner %s: provider %r does not support metadata filters.",
            owner,
            provider,
        )
        return {}

    search_fn = getattr(adapter, "search_by_metadata_filter", None)
    if not callable(search_fn):
        return {}

    try:
        matches = search_fn(CONTRACT_DOCUMENT_FILTER, top_k=_SCAN_TOP_K) or []
    except Exception as exc:
        logger.error(
            "Vector scan failed for owner %s (provider=%s): %s",
            owner,
            getattr(adapter, "provider", "unknown"),
            exc,
        )
        return {}

    return _group_contract_documents(matches, owner=owner)


def _iter_managed_namespace_scans(db: Session) -> Iterator[tuple[str, Any]]:
    rows = db.query(ManagedJetKbNamespaceModel).all()
    for row in rows:
        try:
            adapter = get_retrieval_adapter("jet_kb", {"namespace": row.namespace})
            yield row.owner, adapter
        except Exception as exc:
            logger.error(
                "Failed to initialize managed Jet KB adapter for owner %s: %s",
                row.owner,
                exc,
            )


def _iter_external_connection_scans(db: Session) -> Iterator[tuple[str, Any]]:
    connections = (
        db.query(ContextVectorConnectionModel)
        .filter(ContextVectorConnectionModel.status == "active")
        .all()
    )
    for conn in connections:
        provider = (conn.provider or "").lower().strip()
        if provider != "pinecone":
            continue
        try:
            config = decrypt_config(conn.encrypted_config or {})
            adapter = get_retrieval_adapter(provider, config)
            yield conn.owner, adapter
        except Exception as exc:
            logger.error(
                "Failed to initialize external vector adapter for owner %s (connection=%s): %s",
                conn.owner,
                conn.id,
                exc,
            )


def _collect_contract_documents(db: Session) -> list[ContractDocumentRecord]:
    merged: dict[tuple[str, str], ContractDocumentRecord] = {}

    for owner, adapter in _iter_managed_namespace_scans(db):
        for doc_id, record in _scan_adapter_contracts(adapter, owner=owner).items():
            merged[(owner, doc_id)] = record

    for owner, adapter in _iter_external_connection_scans(db):
        for doc_id, record in _scan_adapter_contracts(adapter, owner=owner).items():
            merged[(owner, doc_id)] = record

    return list(merged.values())


def _get_suggested_contract_review_job_id(db: Session):
    job = (
        db.query(ContextJobModel)
        .filter(
            ContextJobModel.owner == SYSTEM_OWNER,
            ContextJobModel.workflow_type == "contract_review",
        )
        .order_by(ContextJobModel.created_at.asc())
        .first()
    )
    return job.id if job else None


def _has_active_alert(db: Session, owner: str, contract_id: str) -> bool:
    existing = (
        db.query(ProcurementAlertModel.id)
        .filter(
            ProcurementAlertModel.owner == owner,
            ProcurementAlertModel.contract_document_id == contract_id,
            ProcurementAlertModel.dismissed.is_(False),
        )
        .first()
    )
    return existing is not None


def _should_alert(record: ContractDocumentRecord, today: date) -> bool:
    threshold_date = _subtract_months(record.expiry_date, record.lead_months_threshold)
    return today >= threshold_date


def run_contract_expiry_monitor(db: Session) -> dict[str, int]:
    """
    Scan contract vector metadata and create idempotent procurement alerts.

    Safe to run repeatedly; undismissed alerts are not duplicated per contractId.
    """
    today = datetime.now(timezone.utc).date()
    suggested_job_id = _get_suggested_contract_review_job_id(db)
    scanned = 0
    created = 0
    skipped_existing = 0
    skipped_not_due = 0

    try:
        records = _collect_contract_documents(db)
    except Exception as exc:
        logger.exception("Contract expiry monitor failed during vector scan: %s", exc)
        return {
            "scanned": 0,
            "created": 0,
            "skipped_existing": 0,
            "skipped_not_due": 0,
            "error": 1,
        }

    for record in records:
        scanned += 1
        if not _should_alert(record, today):
            skipped_not_due += 1
            continue
        if _has_active_alert(db, record.owner, record.contract_document_id):
            skipped_existing += 1
            continue

        alert = ProcurementAlertModel(
            owner=record.owner,
            workspace_id=record.workspace_id,
            vendor=record.vendor,
            contract_document_id=record.contract_document_id,
            expiry_date=record.expiry_date,
            complexity_tier=record.complexity_tier,
            lead_months_threshold=record.lead_months_threshold,
            complexity_tier_defaulted=record.complexity_tier_defaulted,
            suggested_job_id=suggested_job_id,
            dismissed=False,
        )
        db.add(alert)
        db.commit()
        created += 1
        logger.info(
            "Created procurement alert owner=%s contract_document_id=%s expiry_date=%s "
            "complexity_tier=%s complexity_tier_defaulted=%s lead_months=%s",
            record.owner,
            record.contract_document_id,
            record.expiry_date.isoformat(),
            record.complexity_tier,
            record.complexity_tier_defaulted,
            record.lead_months_threshold,
        )

    logger.info(
        "Contract expiry monitor complete scanned=%s created=%s skipped_existing=%s skipped_not_due=%s",
        scanned,
        created,
        skipped_existing,
        skipped_not_due,
    )
    return {
        "scanned": scanned,
        "created": created,
        "skipped_existing": skipped_existing,
        "skipped_not_due": skipped_not_due,
    }
