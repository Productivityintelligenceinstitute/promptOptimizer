from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from context_jobs.tenancy.request_actor import current_request_actor
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
    workspace_id: Optional[str] = None,
) -> AuditEventModel:
    """
    Persist an audit event. Inside a request the verified member is recorded as the
    actor (``actor`` is only the fallback for background work), and the event is
    tagged with the active workspace unless ``workspace_id`` is given.
    """
    request_actor = current_request_actor()
    if request_actor is not None:
        actor = request_actor.firebase_uid
        workspace_id = workspace_id or request_actor.workspace_id
    row = AuditEventModel(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id),
        actor=actor,
        workspace_id=workspace_id,
        timestamp=occurred_at or datetime.now(timezone.utc),
        event_metadata=metadata or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _apply_filters(query, *, entity_id, event_type, from_ts, to_ts):
    if entity_id:
        query = query.filter(AuditEventModel.entity_id == str(entity_id))
    if event_type:
        query = query.filter(AuditEventModel.event_type == event_type)
    if from_ts:
        query = query.filter(AuditEventModel.timestamp >= from_ts)
    if to_ts:
        query = query.filter(AuditEventModel.timestamp <= to_ts)
    return query


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
        filtered = _apply_filters(
            filtered, entity_id=entity_id, event_type=event_type, from_ts=from_ts, to_ts=to_ts
        )
        rows.extend(filtered.all())

    rows.sort(key=lambda row: row.timestamp, reverse=True)
    return rows


def list_workspace_audit_events(
    db: Session,
    *,
    workspace_id: str,
    owner: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    event_type: Optional[str] = None,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
    limit: int = 500,
) -> list[AuditEventModel]:
    """
    Events for one workspace: rows tagged with ``workspace_id`` plus older job/run
    events recorded before tagging (matched through the job's owner partition).
    """
    tagged = db.query(AuditEventModel).filter(AuditEventModel.workspace_id == workspace_id)
    if entity_type:
        tagged = tagged.filter(AuditEventModel.entity_type == entity_type)
    tagged = _apply_filters(
        tagged, entity_id=entity_id, event_type=event_type, from_ts=from_ts, to_ts=to_ts
    )
    rows = {row.id: row for row in tagged.order_by(AuditEventModel.timestamp.desc()).limit(limit)}

    if entity_type in (None, "job", "run"):
        legacy = list_audit_events(
            db,
            owner=owner,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        for row in legacy:
            if row.workspace_id in (None, workspace_id):
                rows.setdefault(row.id, row)

    ordered = sorted(rows.values(), key=lambda row: row.timestamp, reverse=True)
    return ordered[:limit]
