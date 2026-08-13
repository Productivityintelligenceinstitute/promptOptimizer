"""Import a Coupa/Ironclad contract into a Context Job knowledge target."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs.clm.adapters import get_clm_adapter
from context_jobs.clm.url_parser import parse_clm_reference
from context_jobs import clm_connection_services as clm_services
from context_jobs.ingestion.ingestion_service import ingest_documents
from context_jobs.services.job_queries import get_job
from utils.reader import read_file


def _extension_for(filename: str, content_type: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".pdf", ".docx", ".txt", ".md", ".json"}:
        return suffix
    ctype = (content_type or "").lower()
    if "pdf" in ctype:
        return ".pdf"
    if "word" in ctype or "officedocument" in ctype:
        return ".docx"
    if "text/plain" in ctype:
        return ".txt"
    return ".pdf"


def _extract_text(content: bytes, filename: str, content_type: str | None) -> str:
    ext = _extension_for(filename, content_type)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        return read_file(tmp_path)
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def import_clm_contract_into_job(
    db: Session,
    owner: str,
    *,
    job_id: UUID,
    connection_id: UUID,
    url: str | None = None,
    resource_id: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job = get_job(db, job_id, owner)
    if not job:
        raise ValueError("Job not found")

    conn = clm_services.get_active_connection_for_owner(db, connection_id, owner)
    if url and url.strip():
        reference = parse_clm_reference(url, default_provider=conn.provider)
    elif resource_id and resource_id.strip():
        reference = parse_clm_reference(resource_id, default_provider=conn.provider)
    else:
        raise ValueError("Provide a CLM URL or resourceId.")

    if reference.provider != conn.provider:
        raise ValueError(
            f"URL is for {reference.provider}, but the selected connection is {conn.provider}."
        )

    config = clm_services.decrypted_config_for(conn)
    adapter = get_clm_adapter(conn.provider)
    document = adapter.fetch_document(config, reference)
    text = _extract_text(document.content, document.filename, document.content_type)
    if not (text or "").strip():
        raise ValueError(
            "Downloaded the CLM file, but no extractable text was found "
            "(empty file or scanned/image-only PDF)."
        )

    title = (
        (document.metadata or {}).get("name")
        or document.filename
        or f"{conn.provider} contract {document.resource_id}"
    )
    contract_id = (
        (extra_metadata or {}).get("contractId")
        or (document.metadata or {}).get("contractId")
        or document.resource_id
    )

    metadata: dict[str, Any] = {
        "documentType": "contract",
        "documentName": document.filename,
        "name": title,
        "title": title,
        "contractId": str(contract_id),
        "source": f"clm_import_{conn.provider}",
        "clmProvider": conn.provider,
        "clmResourceType": document.resource_type,
        "clmResourceId": document.resource_id,
        "clmConnectionId": str(conn.id),
        "importedAt": datetime.now(timezone.utc).isoformat(),
    }
    for key, value in (document.metadata or {}).items():
        if value is not None and key not in metadata:
            metadata[key] = value
    if extra_metadata:
        for key, value in extra_metadata.items():
            if value is not None:
                metadata[str(key)] = value

    result = ingest_documents(
        job=job,
        documents=[
            {
                "id": f"clm-{conn.provider}-{document.resource_id}".lower()[:120],
                "text": text,
                "metadata": metadata,
            }
        ],
        db=db,
        ingestion_config=None,
    )
    if result.status in {"failed", "escalated", "blocked_by_policy"} or result.error:
        raise ValueError(result.error or f"Ingestion failed with status={result.status}")

    return {
        "provider": conn.provider,
        "resourceType": document.resource_type,
        "resourceId": document.resource_id,
        "filename": document.filename,
        "jobId": job_id,
        "ingestionStatus": result.status,
        "upsertedCount": int(result.upserted_count or 0),
        "warnings": list(result.warnings or []),
        "message": (
            f"Imported {document.filename} from {conn.provider.title()} "
            f"and ingested into this job's knowledge target."
        ),
        "metadata": metadata,
    }
