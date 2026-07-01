import json
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

import context_jobs.audit as cj_audit
from context_jobs.errors import ContextJobsNotFoundError
from context_jobs.services._constants import JOB_VERSION_SNAPSHOT_FIELDS
from context_jobs.services.job_queries import get_job
from schemas.context_jobs_model import (
    ContextJobModel,
    ContextJobVersionModel,
    PublishHistoryModel,
)


def job_snapshot(job: ContextJobModel) -> dict[str, Any]:
    raw = {field: getattr(job, field) for field in JOB_VERSION_SNAPSHOT_FIELDS}
    return json.loads(json.dumps(raw, default=str))


def apply_job_snapshot(job: ContextJobModel, snapshot: dict[str, Any]) -> None:
    for field in JOB_VERSION_SNAPSHOT_FIELDS:
        if field in snapshot:
            value = snapshot[field]
            if field in {"vector_connection_id", "llm_key_id"} and value:
                value = UUID(str(value))
            setattr(job, field, value)


def ensure_job_version_seed(db: Session, job: ContextJobModel, created_by: Optional[str] = None) -> None:
    existing = (
        db.query(ContextJobVersionModel)
        .filter(ContextJobVersionModel.job_id == job.id)
        .first()
    )
    if existing:
        return
    seed_version = int(job.version or 1)
    db.add(
        ContextJobVersionModel(
            job_id=job.id,
            version=seed_version,
            snapshot=job_snapshot(job),
            created_by=created_by or job.owner,
            change_type="seed",
            is_current=True,
        )
    )
    db.commit()


def clear_current_version_flags(db: Session, job_id: UUID) -> None:
    (
        db.query(ContextJobVersionModel)
        .filter(ContextJobVersionModel.job_id == job_id)
        .update({"is_current": False}, synchronize_session=False)
    )


def set_current_version(db: Session, job_id: UUID, version: int) -> None:
    clear_current_version_flags(db, job_id)
    row = (
        db.query(ContextJobVersionModel)
        .filter(
            ContextJobVersionModel.job_id == job_id,
            ContextJobVersionModel.version == version,
        )
        .first()
    )
    if row:
        row.is_current = True


def get_version_rows(db: Session, job_id: UUID) -> list[ContextJobVersionModel]:
    return (
        db.query(ContextJobVersionModel)
        .filter(ContextJobVersionModel.job_id == job_id)
        .order_by(ContextJobVersionModel.version.desc(), ContextJobVersionModel.created_at.desc())
        .all()
    )


def normalize_current_version(db: Session, job: ContextJobModel) -> None:
    rows = get_version_rows(db, job.id)
    if not rows:
        return
    current_rows = [row for row in rows if bool(row.is_current)]
    if len(current_rows) == 1 and int(job.version or 0) == int(current_rows[0].version or 0):
        return
    target = next(
        (row for row in current_rows if int(row.version or 0) == int(job.version or 0)),
        None,
    )
    if not target:
        target = next((row for row in rows if int(row.version or 0) == int(job.version or 0)), None)
    if not target:
        target = current_rows[0] if current_rows else rows[0]
    clear_current_version_flags(db, job.id)
    target.is_current = True
    db.commit()


def latest_job_version_number(db: Session, job_id: UUID) -> int:
    rows = get_version_rows(db, job_id)
    if rows:
        return int(rows[0].version or 1)
    job = db.query(ContextJobModel).filter(ContextJobModel.id == job_id).first()
    return int(job.version or 1) if job else 1


def serialize_job_version(
    job: ContextJobModel,
    version_row: ContextJobVersionModel,
) -> dict[str, Any]:
    return {
        "id": version_row.id,
        "jobId": version_row.job_id,
        "version": version_row.version,
        "createdAt": version_row.created_at,
        "createdBy": version_row.created_by,
        "changeType": version_row.change_type,
        "rollbackFromVersion": version_row.rollback_from_version,
        "notes": version_row.notes,
        "isCurrent": bool(version_row.is_current),
        "jobSnapshot": version_row.snapshot or {},
    }


def record_job_version(
    db: Session,
    job: ContextJobModel,
    *,
    created_by: Optional[str] = None,
    change_type: str = "save",
    rollback_from_version: Optional[int] = None,
    notes: Optional[str] = None,
) -> ContextJobVersionModel:
    clear_current_version_flags(db, job.id)
    entry = ContextJobVersionModel(
        job_id=job.id,
        version=int(job.version or 1),
        snapshot=job_snapshot(job),
        created_by=created_by or job.owner,
        change_type=change_type,
        is_current=True,
        rollback_from_version=rollback_from_version,
        notes=notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def record_publish_history(
    db: Session,
    *,
    job_id: UUID,
    from_status: str,
    to_status: str,
    changed_by: str,
    notes: Optional[str] = None,
) -> PublishHistoryModel:
    row = PublishHistoryModel(
        job_id=job_id,
        from_status=from_status,
        to_status=to_status,
        changed_by=changed_by,
        notes=notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_publish_history(db: Session, owner: str, job_id: UUID) -> list[dict[str, Any]]:
    job = get_job(db, job_id, owner)
    if not job:
        raise ContextJobsNotFoundError("Job not found")
    rows = (
        db.query(PublishHistoryModel)
        .filter(PublishHistoryModel.job_id == job_id)
        .order_by(PublishHistoryModel.changed_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "jobId": row.job_id,
            "fromStatus": row.from_status,
            "toStatus": row.to_status,
            "changedBy": row.changed_by,
            "changedAt": row.changed_at,
            "notes": row.notes,
        }
        for row in rows
    ]


def list_job_versions(db: Session, owner: str, job_id: UUID) -> List[dict[str, Any]]:
    job = get_job(db, job_id, owner)
    if not job:
        raise ContextJobsNotFoundError("Job not found")
    ensure_job_version_seed(db, job, created_by=owner)
    normalize_current_version(db, job)
    return [serialize_job_version(job, row) for row in get_version_rows(db, job.id)]


def get_job_version(db: Session, owner: str, job_id: UUID, version: int) -> dict[str, Any]:
    job = get_job(db, job_id, owner)
    if not job:
        raise ContextJobsNotFoundError("Job not found")
    ensure_job_version_seed(db, job, created_by=owner)
    normalize_current_version(db, job)
    row = (
        db.query(ContextJobVersionModel)
        .filter(
            ContextJobVersionModel.job_id == job.id,
            ContextJobVersionModel.version == version,
        )
        .first()
    )
    if not row:
        raise ContextJobsNotFoundError("Version not found")
    return serialize_job_version(job, row)


def get_latest_job_version(db: Session, owner: str, job_id: UUID) -> dict[str, Any]:
    job = get_job(db, job_id, owner)
    if not job:
        raise ContextJobsNotFoundError("Job not found")
    ensure_job_version_seed(db, job, created_by=owner)
    normalize_current_version(db, job)
    row = (
        db.query(ContextJobVersionModel)
        .filter(ContextJobVersionModel.job_id == job.id, ContextJobVersionModel.is_current.is_(True))
        .order_by(ContextJobVersionModel.created_at.desc(), ContextJobVersionModel.version.desc())
        .first()
    )
    if not row:
        row = (
            db.query(ContextJobVersionModel)
            .filter(ContextJobVersionModel.job_id == job.id)
            .order_by(ContextJobVersionModel.created_at.desc(), ContextJobVersionModel.version.desc())
            .first()
        )
    if not row:
        raise ContextJobsNotFoundError("Version not found")
    return serialize_job_version(job, row)


def publish_job(
    db: Session,
    owner: str,
    job_id: UUID,
    notes: Optional[str] = None,
) -> ContextJobModel:
    job = get_job(db, job_id, owner)
    if not job:
        raise ContextJobsNotFoundError("Job not found")
    from_status = (job.status or "draft").lower()
    if from_status == "published":
        raise ValueError("Job is already published")
    if from_status not in {"draft", "archived"}:
        raise ValueError(f"Cannot publish a job from status {job.status!r}")
    job.status = "published"
    db.add(job)
    db.commit()
    db.refresh(job)
    record_publish_history(
        db,
        job_id=job.id,
        from_status=from_status,
        to_status="published",
        changed_by=owner,
        notes=notes,
    )
    cj_audit.write_audit_event(
        db,
        event_type="job.published",
        entity_type="job",
        entity_id=str(job.id),
        actor=owner,
        metadata={
            "fromStatus": from_status,
            "toStatus": "published",
            "notes": notes,
            "jobVersion": job.version,
        },
    )
    return job


def archive_job(
    db: Session,
    owner: str,
    job_id: UUID,
    notes: Optional[str] = None,
) -> ContextJobModel:
    job = get_job(db, job_id, owner)
    if not job:
        raise ContextJobsNotFoundError("Job not found")
    from_status = (job.status or "draft").lower()
    if from_status == "archived":
        raise ValueError("Job is already archived")
    job.status = "archived"
    db.add(job)
    db.commit()
    db.refresh(job)
    record_publish_history(
        db,
        job_id=job.id,
        from_status=from_status,
        to_status="archived",
        changed_by=owner,
        notes=notes,
    )
    cj_audit.write_audit_event(
        db,
        event_type="job.archived",
        entity_type="job",
        entity_id=str(job.id),
        actor=owner,
        metadata={
            "fromStatus": from_status,
            "toStatus": "archived",
            "notes": notes,
            "jobVersion": job.version,
        },
    )
    return job


def rollback_job_version(
    db: Session,
    owner: str,
    job_id: UUID,
    target_version: int,
    notes: Optional[str] = None,
) -> ContextJobModel:
    job = get_job(db, job_id, owner)
    if not job:
        raise ContextJobsNotFoundError("Job not found")
    ensure_job_version_seed(db, job, created_by=owner)
    row = (
        db.query(ContextJobVersionModel)
        .filter(
            ContextJobVersionModel.job_id == job.id,
            ContextJobVersionModel.version == target_version,
        )
        .first()
    )
    if not row:
        raise ContextJobsNotFoundError("Version not found")
    previous_version = int(job.version or 1)
    snapshot = dict(row.snapshot or {})
    apply_job_snapshot(job, snapshot)
    set_current_version(db, job.id, target_version)
    job.version = int(target_version)
    job.owner = owner
    db.add(job)
    db.commit()
    db.refresh(job)
    cj_audit.write_audit_event(
        db,
        event_type="job.rolled_back",
        entity_type="job",
        entity_id=str(job.id),
        actor=owner,
        metadata={
            "fromVersion": previous_version,
            "toVersion": target_version,
            "notes": notes,
        },
    )
    return job
