"""Procurement demo knowledge base — synthetic documents for pilot and sales demos."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs.ingestion.ingestion_service import ingest_documents
from context_jobs.ingestion.types import IngestionResult
from context_jobs.managed_jet_kb import (
    get_demo_kb_bundle_version,
    is_demo_kb_seeded,
    mark_demo_kb_seeded,
)
from context_jobs.procurement_templates_seed import SYSTEM_OWNER
from context_jobs.services.job_queries import get_job
from context_jobs.services.jobs import instantiate_template_job
from schemas.context_jobs_model import ContextJobModel

DEMO_KB_DIR = Path(__file__).resolve().parent.parent / "docs" / "demo_kb"

DEFAULT_TEMPLATE_NAME = "Contract Review & Renewal"

# Bump when demo_kb_documents() gains files. Already-seeded owners ingest only the delta.
DEMO_KB_BUNDLE_VERSION = 2
# Document ids introduced in each bundle version (for delta ingest).
_DEMO_KB_DELTA_BY_VERSION: dict[int, frozenset[str]] = {
    2: frozenset({"demo-job-taxonomy"}),
}


def _read_text(filename: str) -> str:
    path = DEMO_KB_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Demo KB file not found: {path}")
    return path.read_text(encoding="utf-8")


def demo_kb_documents() -> list[dict[str, Any]]:
    """Return demo documents with explicit procurement metadata for reliable ingestion."""
    return [
        {
            "id": "demo-msa-acme-2024",
            "text": _read_text("msa_acme_corp_2024.txt"),
            "metadata": {
                "title": "Acme Cloud Services MSA 2024",
                "documentType": "contract",
                "contractId": "ACME-MSA-2024-001",
                "vendor": "Acme Cloud Services Inc.",
                "category": "Cloud Infrastructure",
                "expiryDate": "2026-12-31",
                "complexityTier": "medium",
            },
        },
        {
            "id": "demo-procurement-policy",
            "text": _read_text("procurement_policy.txt"),
            "metadata": {
                "title": "Jet Industries Procurement Policy v2.1",
                "documentType": "policy",
                "category": "Procurement",
            },
        },
        {
            "id": "demo-rate-card-acme-2024",
            "text": _read_text("rate_card_acme_2024.csv"),
            "metadata": {
                "title": "Acme Cloud Services Rate Card 2024",
                "documentType": "rate_card",
                "vendor": "Acme Cloud Services Inc.",
                "category": "Professional Services",
            },
        },
        {
            "id": "demo-job-taxonomy",
            "text": _read_text("job_taxonomy.txt"),
            "metadata": {
                "title": "Jet Industries Job Taxonomy",
                "documentType": "policy",
                "category": "Procurement",
                "taxonomyType": "job_taxonomy",
            },
        },
        {
            "id": "demo-vendor-nexgen",
            "text": _read_text("vendor_profile_nexgen.txt"),
            "metadata": {
                "title": "NexGen Analytics Vendor Profile",
                "documentType": "vendor_profile",
                "vendorId": "VND-NEXGEN-042",
                "vendorName": "NexGen Analytics Ltd.",
                "vendor": "NexGen Analytics Ltd.",
                "capabilities": ["analytics", "ml", "data-platform"],
                "riskTier": "medium",
                "spendTier": "2",
                "linkedContractIds": ["ACME-MSA-2024-001"],
            },
        },
        {
            "id": "demo-vendor-cloudco",
            "text": _read_text("vendor_profile_cloudco.txt"),
            "metadata": {
                "title": "CloudCo Systems Vendor Profile",
                "documentType": "vendor_profile",
                "vendorId": "VND-CLOUDCO-017",
                "vendorName": "CloudCo Systems AG",
                "vendor": "CloudCo Systems AG",
                "capabilities": ["cloud", "security", "finops"],
                "riskTier": "low",
                "spendTier": "1",
                "linkedContractIds": [],
            },
        },
    ]


def find_system_template(
    db: Session,
    template_name: str = DEFAULT_TEMPLATE_NAME,
) -> ContextJobModel | None:
    return (
        db.query(ContextJobModel)
        .filter(
            ContextJobModel.owner == SYSTEM_OWNER,
            ContextJobModel.name == template_name,
        )
        .first()
    )


def _skipped_demo_ingestion_result() -> IngestionResult:
    return IngestionResult(
        status="completed",
        outcome="skipped_already_present",
        next_action={"type": "use_result", "label": "Demo KB already available"},
        upserted_count=0,
        failed_count=0,
        warnings=[
            "Demo knowledge base was already seeded for your workspace; skipped re-ingest. "
            "The new job still uses the same Jet managed KB."
        ],
        ingested_sources=[{"id": doc["id"], "skipped": True} for doc in demo_kb_documents()],
    )


def _delta_document_ids(from_version: int, to_version: int) -> frozenset[str]:
    ids: set[str] = set()
    for version in range(from_version + 1, to_version + 1):
        ids.update(_DEMO_KB_DELTA_BY_VERSION.get(version, frozenset()))
    return frozenset(ids)


def seed_demo_kb_for_job(
    db: Session,
    owner: str,
    job_id: UUID,
    *,
    documents: list[dict[str, Any]] | None = None,
    ingestion_config: dict[str, Any] | None = None,
    force: bool = False,
) -> IngestionResult:
    """
    Ingest the demo KB bundle into a user-owned job's configured vector target.

    For Jet managed KB (shared per owner), skip full re-ingest after a successful seed
    at the current bundle version. If the bundle version is newer (new demo files),
    only the delta documents are upserted. Pass force=True to re-seed the full bundle.
    """
    job = get_job(db, job_id, owner)
    if not job:
        raise ValueError(f"Job {job_id} not found for owner {owner!r}")

    docs = documents if documents is not None else demo_kb_documents()
    uses_shared_jet_kb = (job.retrieval_mode or "jet_kb").strip().lower() == "jet_kb"

    if uses_shared_jet_kb and not force and is_demo_kb_seeded(db, owner):
        current_version = get_demo_kb_bundle_version(db, owner)
        if current_version >= DEMO_KB_BUNDLE_VERSION:
            return _skipped_demo_ingestion_result()
        delta_ids = _delta_document_ids(current_version, DEMO_KB_BUNDLE_VERSION)
        docs = [doc for doc in docs if doc.get("id") in delta_ids]
        if not docs:
            mark_demo_kb_seeded(db, owner, bundle_version=DEMO_KB_BUNDLE_VERSION)
            return _skipped_demo_ingestion_result()

    result = ingest_documents(job, docs, db, ingestion_config=ingestion_config)

    if (
        uses_shared_jet_kb
        and result.status in {"completed", "completed_with_warnings"}
        and not result.error
    ):
        mark_demo_kb_seeded(db, owner, bundle_version=DEMO_KB_BUNDLE_VERSION)

    return result

def seed_demo_kb_for_owner(
    db: Session,
    owner: str,
    *,
    template_name: str = DEFAULT_TEMPLATE_NAME,
    job_id: UUID | None = None,
    instantiate_if_missing: bool = True,
    ingestion_config: dict[str, Any] | None = None,
    force: bool = False,
) -> tuple[ContextJobModel, IngestionResult]:
    """
    Ingest demo KB into a job owned by ``owner``.

    When ``job_id`` is omitted, uses an existing job with ``template_name`` or
    instantiates that system template when ``instantiate_if_missing`` is True.
    """
    job: ContextJobModel | None = None
    if job_id is not None:
        job = get_job(db, job_id, owner)
        if not job:
            raise ValueError(f"Job {job_id} not found for owner {owner!r}")
    else:
        job = (
            db.query(ContextJobModel)
            .filter(
                ContextJobModel.owner == owner,
                ContextJobModel.name == template_name,
            )
            .order_by(ContextJobModel.created_at.desc())
            .first()
        )
        if not job and instantiate_if_missing:
            template = find_system_template(db, template_name)
            if not template:
                raise ValueError(f"System template not found: {template_name!r}")
            job = instantiate_template_job(db, owner, template.id)
        if not job:
            raise ValueError(
                f"No job named {template_name!r} for owner {owner!r}; "
                "pass --job-id or allow template instantiation."
            )

    result = seed_demo_kb_for_job(
        db,
        owner,
        job.id,
        ingestion_config=ingestion_config,
        force=force,
    )
    return job, result
