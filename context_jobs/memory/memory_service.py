"""Memory persistence for Context Jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from schemas.context_jobs_model import ContextJobModel, JobRunModel
from schemas.run_memory_entry_model import RunMemoryEntryModel


def _extract_facts(output_text: str, memory_type: str) -> list[dict]:
    text = (output_text or "").strip()
    if not text:
        return []
    snippet = text[:500]
    return [
        {
            "key": f"{memory_type}_summary",
            "value": {"text": snippet, "memoryType": memory_type},
        }
    ]


async def persist_memory_updates(
    run: JobRunModel,
    job: ContextJobModel,
    output_text: str,
    db: Session,
) -> list[dict]:
    memory_config = job.memory_config or {}
    retention_days = int(memory_config.get("retentionDays") or 30)
    expires_at = datetime.now(timezone.utc) + timedelta(days=retention_days)
    changes: list[dict] = []

    for memory_type, enabled_key in (
        ("session", "sessionMemory"),
        ("project", "projectMemory"),
        ("user_profile", "userProfileMemory"),
    ):
        if not memory_config.get(enabled_key):
            continue
        facts = _extract_facts(output_text, memory_type)
        for fact in facts:
            entry = RunMemoryEntryModel(
                owner=job.owner,
                job_id=job.id if memory_type != "user_profile" else None,
                memory_type=memory_type,
                key=fact["key"],
                value=fact["value"],
                source_run_id=run.id,
                expires_at=expires_at,
            )
            db.add(entry)
            changes.append(
                {
                    "type": "memory_write",
                    "destination": memory_type,
                    "reason": f"Persisted from run {run.id}",
                }
            )
    db.commit()
    return changes
