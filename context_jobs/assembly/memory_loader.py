"""Load memory context for a run."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from schemas.run_memory_entry_model import RunMemoryEntryModel


def _format_entries(entries: list[RunMemoryEntryModel]) -> str:
    lines = []
    for entry in entries:
        value = entry.value
        if isinstance(value, dict):
            text = value.get("text") or value.get("summary") or str(value)
        else:
            text = str(value)
        lines.append(f"- {entry.key}: {text}")
    return "\n".join(lines)


def load_memory_context(owner: str, job_id, memory_config: dict | None, db: Session) -> str:
    memory_config = memory_config or {}
    now = datetime.now(timezone.utc)
    sections: list[str] = []

    if memory_config.get("sessionMemory"):
        entries = (
            db.query(RunMemoryEntryModel)
            .filter(
                RunMemoryEntryModel.owner == owner,
                RunMemoryEntryModel.job_id == job_id,
                RunMemoryEntryModel.memory_type == "session",
                (RunMemoryEntryModel.expires_at.is_(None))
                | (RunMemoryEntryModel.expires_at > now),
            )
            .order_by(RunMemoryEntryModel.created_at.desc())
            .limit(20)
            .all()
        )
        if entries:
            sections.append("## Session Memory\n" + _format_entries(entries))

    if memory_config.get("projectMemory"):
        entries = (
            db.query(RunMemoryEntryModel)
            .filter(
                RunMemoryEntryModel.owner == owner,
                RunMemoryEntryModel.job_id == job_id,
                RunMemoryEntryModel.memory_type == "project",
                (RunMemoryEntryModel.expires_at.is_(None))
                | (RunMemoryEntryModel.expires_at > now),
            )
            .order_by(RunMemoryEntryModel.created_at.desc())
            .limit(10)
            .all()
        )
        if entries:
            sections.append("## Project Memory\n" + _format_entries(entries))

    if memory_config.get("userProfileMemory"):
        entries = (
            db.query(RunMemoryEntryModel)
            .filter(
                RunMemoryEntryModel.owner == owner,
                RunMemoryEntryModel.job_id.is_(None),
                RunMemoryEntryModel.memory_type == "user_profile",
                (RunMemoryEntryModel.expires_at.is_(None))
                | (RunMemoryEntryModel.expires_at > now),
            )
            .order_by(RunMemoryEntryModel.created_at.desc())
            .limit(10)
            .all()
        )
        if entries:
            sections.append("## User Profile\n" + _format_entries(entries))

    return "\n\n".join(sections)
