from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from schemas.context_jobs_model import AuditEventModel, ContextJobModel, JobRunModel


def write_audit_event(
    db: Session,
    *,
    event_type: str,
    entity_type: str,
    entity_id: str,
    actor: str,
    metadata: Optional[dict[str, Any]] = None,
    occurred_at: Optional[datetime] = None,
) -> AuditEventModel:
    row = AuditEventModel(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id),
        actor=actor,
        timestamp=occurred_at or datetime.now(timezone.utc),
        event_metadata=metadata or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_audit_events(
    db: Session,
    *,
    owner: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    event_type: Optional[str] = None,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
) -> list[AuditEventModel]:
    job_query = db.query(AuditEventModel).join(
        ContextJobModel,
        (AuditEventModel.entity_type == "job")
        & (AuditEventModel.entity_id == cast(ContextJobModel.id, String)),
    )
    run_query = db.query(AuditEventModel).join(
        JobRunModel,
        (AuditEventModel.entity_type == "run")
        & (AuditEventModel.entity_id == cast(JobRunModel.id, String)),
    ).join(
        ContextJobModel,
        JobRunModel.job_id == ContextJobModel.id,
    )

    queries = []
    if entity_type == "job":
        queries = [job_query]
    elif entity_type == "run":
        queries = [run_query]
    else:
        queries = [job_query, run_query]

    rows: list[AuditEventModel] = []
    for query in queries:
        filtered = query
        if owner:
            filtered = filtered.filter(ContextJobModel.owner == owner)
        if entity_id:
            filtered = filtered.filter(AuditEventModel.entity_id == str(entity_id))
        if event_type:
            filtered = filtered.filter(AuditEventModel.event_type == event_type)
        if from_ts:
            filtered = filtered.filter(AuditEventModel.timestamp >= from_ts)
        if to_ts:
            filtered = filtered.filter(AuditEventModel.timestamp <= to_ts)
        rows.extend(filtered.all())

    rows.sort(key=lambda row: row.timestamp, reverse=True)
    return rows
