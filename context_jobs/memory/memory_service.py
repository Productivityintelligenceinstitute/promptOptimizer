"""Memory persistence for Context Jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

import context_jobs.audit as cj_audit
from schemas.context_jobs_model import ContextJobModel, JobRunModel
from schemas.run_memory_entry_model import RunMemoryEntryModel


async def _extract_facts(output_text: str, memory_type: str, job_goal: str = "") -> list[dict]:
    text = (output_text or "").strip()
    if not text:
        return []
    try:
        import os
        import json
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        prompt = (
            f"Extract 3-5 key facts or decisions from this AI output that would be useful "
            f"to remember for future runs of the same job.\n"
            f"Job goal: {job_goal or 'general'}\n"
            f"Memory type: {memory_type}\n\n"
            f"Output to extract from:\n{text[:3000]}\n\n"
            f"Return ONLY a JSON array of objects with 'key' and 'value' fields. "
            f"Keys should be short snake_case identifiers. "
            f"Values should be concise strings. "
            f"Example: [{{'key': 'main_finding', 'value': 'EU AI Act requires conformity assessment for high-risk systems'}}]"
        )
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=512,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = (response.choices[0].message.content or "").strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        facts_raw = json.loads(raw.strip())
        if not isinstance(facts_raw, list):
            raise ValueError("Not a list")
        return [
            {
                "key": f"{memory_type}_{str(f.get('key', f'fact_{i}')).lower().replace(' ', '_')}",
                "value": {"text": str(f.get("value", "")), "memoryType": memory_type},
            }
            for i, f in enumerate(facts_raw[:5])
            if isinstance(f, dict)
        ]
    except Exception:
        # Fall back to paragraph extraction
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 50]
        if not paragraphs:
            return [{"key": f"{memory_type}_summary", "value": {"text": text[:500]}}]
        top = sorted(paragraphs, key=len, reverse=True)[:3]
        return [
            {
                "key": f"{memory_type}_fact_{i}",
                "value": {"text": para[:500], "memoryType": memory_type},
            }
            for i, para in enumerate(top)
        ]


async def prepare_memory_updates(
    run: JobRunModel,
    job: ContextJobModel,
    output_text: str,
    db: Session,
) -> tuple[list[dict], list[dict]]:
    """Extract memory facts. Returns (display_changes, persistable_facts)."""
    memory_config = job.memory_config or {}
    changes: list[dict] = []
    facts: list[dict] = []

    for memory_type, enabled_key in (
        ("session", "sessionMemory"),
        ("project", "projectMemory"),
        ("user_profile", "userProfileMemory"),
    ):
        if not memory_config.get(enabled_key):
            continue
        extracted = await _extract_facts(output_text, memory_type, job.goal or "")
        for fact in extracted:
            facts.append({**fact, "memory_type": memory_type})
            changes.append(
                {
                    "type": "memory_write",
                    "destination": memory_type,
                    "reason": f"Extracted from run {run.id}",
                    "key": fact["key"],
                    "preview": str(fact.get("value", ""))[:200],
                }
            )
    return changes, facts


async def persist_memory_updates(
    run: JobRunModel,
    job: ContextJobModel,
    output_text: str,
    db: Session,
) -> list[dict]:
    from context_jobs.hitl import memory_requires_confirmation, set_pending_memory_changes

    changes, facts = await prepare_memory_updates(run, job, output_text, db)
    if not changes:
        return []

    if memory_requires_confirmation(job):
        set_pending_memory_changes(db, run, changes, facts)
        return changes

    memory_config = job.memory_config or {}
    retention_days = int(memory_config.get("retentionDays") or 30)
    expires_at = datetime.now(timezone.utc) + timedelta(days=retention_days)

    for fact in facts:
        entry = RunMemoryEntryModel(
            owner=job.owner,
            job_id=job.id if fact.get("memory_type") != "user_profile" else None,
            memory_type=fact["memory_type"],
            key=fact["key"],
            value=fact["value"],
            source_run_id=run.id,
            expires_at=expires_at,
        )
        db.add(entry)
    db.commit()
    if changes:
        cj_audit.write_audit_event(
            db,
            event_type="memory.written",
            entity_type="run",
            entity_id=str(run.id),
            actor=job.owner,
            metadata={
                "jobId": str(job.id),
                "runId": str(run.id),
                "writeCount": len(changes),
                "memoryTypes": sorted({c["destination"] for c in changes}),
            },
        )
    return changes
