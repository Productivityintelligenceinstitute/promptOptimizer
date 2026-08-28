"""Approve recommendations → generate a revised contract as a downloadable artifact."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from context_jobs.artifacts.blob_store import REVISED_CONTRACT_FILENAME
from context_jobs.gateway.execution_limits import merge_amendment_budget
from context_jobs.orchestrator import enqueue_run
from context_jobs.plan_entitlements import assert_can_create_run, ensure_context_jobs_access, record_run_created
from context_jobs.provider_key_services import resolve_llm_api_key
from context_jobs.workspace import default_workspace_id, ensure_default_workspace
from schemas.context_jobs_model import ContextJobModel, JobRunModel

AMENDMENT_WORKFLOW_TYPE = "contract_amendment"
AMENDMENT_SOURCE_KEY = "sourceJobId"
MAX_PARENT_CONTEXT_CHARS = 24000

AMENDMENT_TOOL_PERMISSIONS = [
    {"toolId": "doc-reader", "enabled": True, "readOnly": True, "requireApproval": False},
    {"toolId": "contract-patch", "enabled": True, "readOnly": False, "requireApproval": False},
    {"toolId": "docx-generate", "enabled": True, "readOnly": False, "requireApproval": False},
    {"toolId": "file-write", "enabled": True, "readOnly": False, "requireApproval": False},
]

AMENDMENT_ROLE = (
    "You are a contracts specialist producing a clean conformed copy of an existing agreement. "
    "This is a surgical redline, not a rewrite. You provide ONLY the changed clause bodies as patches — "
    "the server automatically preserves every other section verbatim from the original. "
    "Keep defined terms, parties, cross-references, and unusual clauses exactly as-is in your patches. "
    "You produce a Word document for legal's final review; you do not write back to any CLM."
)

AMENDMENT_INSTRUCTIONS = (
    "Apply the approved recommendations to the original contract using contract-patch.\n"
    "\n"
    "Rules:\n"
    "1. The canonical source contract is already loaded on the server — "
    "you do NOT need to pass source_text.\n"
    "2. Call contract-patch EXACTLY ONCE with:\n"
    '   - path="revised-contract.docx"\n'
    "   - title=<original document title from the contract>\n"
    '   - cover_patches=[{"field": ..., "new_value": ...}] for cover-page fields that change\n'
    "   - section_patches: one entry per change\n"
    "3. Prefer find/replace for number or phrase swaps. Example:\n"
    '   {"id": "4.4", "find": "five (5) days", "replace": "thirty (30) days"}\n'
    '   {"id": "5.5.b", "find": "within 60 days", "replace": "within thirty (30) days"}\n'
    "4. For a full-clause rewrite (e.g. adding opt-out language), new_text MUST be the "
    "COMPLETE original clause including every sub-paragraph (a/b/c/d) with only the "
    "requested words changed. Do not shorten. Do not drop invoices, late-fee, return, "
    "carve-out, or signature language. Exclude only the clause number and title "
    "(the tool keeps '1.6. Machine Learning.').\n"
    '5. If a recommendation targets a lettered item such as 5.5(b), use id "5.5.b".\n'
    "6. A stub that replaces a long clause with one sentence WILL BE REJECTED. "
    "Re-submit the full clause.\n"
    "7. Do not invent counterparties, dates, fees, or governing law.\n"
    '8. Optionally write a short change log via file-write at path="revision-notes.md".\n'
)

AMENDMENT_OUTPUT_TEMPLATE = (
    "State that the revised contract file is ready, name the file "
    f"{REVISED_CONTRACT_FILENAME}, and list the clause changes applied."
)


def is_contract_review_job(job: ContextJobModel | None) -> bool:
    return (getattr(job, "workflow_type", None) or "").lower() == "contract_review"


def is_amendment_job(job: ContextJobModel | None) -> bool:
    return (getattr(job, "workflow_type", None) or "").lower() == AMENDMENT_WORKFLOW_TYPE


def _chain_source_job_id(job: ContextJobModel) -> str | None:
    config = job.chain_config if isinstance(job.chain_config, dict) else {}
    raw = config.get(AMENDMENT_SOURCE_KEY) or config.get("source_job_id")
    return str(raw) if raw else None


def _ensure_amendment_job(db: Session, owner: str, parent_job: ContextJobModel) -> ContextJobModel:
    existing = (
        db.query(ContextJobModel)
        .filter(
            ContextJobModel.owner == owner,
            ContextJobModel.workflow_type == AMENDMENT_WORKFLOW_TYPE,
        )
        .all()
    )
    for candidate in existing:
        if _chain_source_job_id(candidate) == str(parent_job.id):
            candidate.status = "published"
            candidate.role_configuration = AMENDMENT_ROLE
            candidate.stable_instructions = AMENDMENT_INSTRUCTIONS
            candidate.output_template = AMENDMENT_OUTPUT_TEMPLATE
            candidate.tool_permissions = list(AMENDMENT_TOOL_PERMISSIONS)
            candidate.budget_settings = merge_amendment_budget(parent_job.budget_settings)
            if (candidate.max_agent_turns or 0) < 10:
                candidate.max_agent_turns = 10
            db.add(candidate)
            db.commit()
            db.refresh(candidate)
            return candidate

    ws = ensure_default_workspace(db, owner)
    job = ContextJobModel(
        name=f"{parent_job.name} (revised contract)",
        description=(
            "Internal follow-up job that generates a revised contract after a human "
            "approves Contract Review recommendations. Hidden from the jobs library."
        ),
        status="published",
        goal="Produce a complete revised legal agreement that applies the approved recommendations.",
        role_configuration=AMENDMENT_ROLE,
        stable_instructions=AMENDMENT_INSTRUCTIONS,
        output_template=AMENDMENT_OUTPUT_TEMPLATE,
        workflow_type=AMENDMENT_WORKFLOW_TYPE,
        retrieval_config=parent_job.retrieval_config,
        retrieval_mode=parent_job.retrieval_mode or "jet_kb",
        vector_connection_id=parent_job.vector_connection_id,
        memory_config=parent_job.memory_config,
        tool_permissions=list(AMENDMENT_TOOL_PERMISSIONS),
        validation_rules=[],
        budget_settings=merge_amendment_budget(parent_job.budget_settings),
        glossary_terms=parent_job.glossary_terms,
        trusted_sources=parent_job.trusted_sources,
        chain_config={AMENDMENT_SOURCE_KEY: str(parent_job.id), "purpose": AMENDMENT_WORKFLOW_TYPE},
        execution_provider=parent_job.execution_provider or "openai",
        execution_model=parent_job.execution_model,
        llm_key_id=parent_job.llm_key_id,
        max_agent_turns=10,
        execution_mode=parent_job.execution_mode or "single_agent",
        version=1,
        owner=owner,
        approval_required=False,
        policy_profile=parent_job.policy_profile,
        workspace_id=parent_job.workspace_id or ws.id,
        linked_asset_ids=list(parent_job.linked_asset_ids or [])
        if isinstance(parent_job.linked_asset_ids, list)
        else [],
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _parent_result_text(run: JobRunModel) -> str:
    rop = run.run_output_package if isinstance(run.run_output_package, dict) else {}
    primary = rop.get("primaryResult") if isinstance(rop, dict) else None
    content = ""
    if isinstance(primary, dict):
        content = str(primary.get("content") or "").strip()
    if not content:
        content = str(run.output_text or "").strip()
    return content


def _analyzer_excerpt(run: JobRunModel) -> str:
    events = run.tool_events if isinstance(run.tool_events, list) else []
    chunks: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        tool_id = str(event.get("toolId") or event.get("tool_id") or "").lower()
        if tool_id != "contract-analyzer":
            continue
        result = event.get("result") or event.get("content") or event.get("output")
        if isinstance(result, (dict, list)):
            chunks.append(json.dumps(result, ensure_ascii=False)[:8000])
        elif result:
            chunks.append(str(result)[:8000])
        if len(chunks) >= 2:
            break
    return "\n\n".join(chunks)


def build_amendment_request(
    parent_run: JobRunModel,
    notes: str | None,
    *,
    canonical_source: str | None = None,
) -> str:
    recommendations = _parent_result_text(parent_run)
    if len(recommendations) > MAX_PARENT_CONTEXT_CHARS:
        recommendations = recommendations[:MAX_PARENT_CONTEXT_CHARS] + "\n\n[truncated]"
    analyzer = _analyzer_excerpt(parent_run)
    note_block = (notes or "").strip()

    parts = [
        "A human approved the Contract Review recommendations below.",
        "Call contract-patch once with only the changed clauses as patches — "
        "the original contract source is pre-loaded on the server.",
        "",
        "## Approved recommendations",
        recommendations
        or "(No structured recommendations were captured. Use retrieved contract context.)",
    ]
    if note_block:
        parts.extend(["", "## Approver notes", note_block])
    if analyzer:
        parts.extend(["", "## Contract analyzer output (key clause facts)", analyzer])

    if canonical_source:
        from context_jobs.services.revision_validator import (
            extract_clause_ids,
            format_clause_id_checklist,
        )
        clause_ids = extract_clause_ids(canonical_source)
        word_count = len(canonical_source.split())
        # Show a compact reference header (title + cover page only) so the LLM
        # knows the document structure without having to echo it all back.
        header_end = canonical_source.find("\n1.")
        header_preview = (
            canonical_source[:header_end].strip()
            if header_end > 0
            else canonical_source[:800].strip()
        )
        parts.extend([
            "",
            "## Original contract reference (cover page)",
            header_preview,
            "",
            f"Original document: {word_count} words, {len(clause_ids)} numbered clauses.",
            "The FULL original text is pre-loaded on the server under this run.",
            "You MUST call contract-patch (not docx-generate) to produce the DOCX.",
            "Do NOT pass source_text — the tool loads it automatically.",
        ])
        checklist = format_clause_id_checklist(canonical_source)
        if checklist:
            parts.extend([
                "",
                "## Clause IDs in the original (reference for your patches)",
                checklist,
            ])
    else:
        parts.extend([
            "",
            "No canonical source was found for this contract. "
            "Use contract-patch or docx-generate with the retrieved contract context.",
        ])

    return "\n".join(parts)


def start_amendment_run(
    db: Session,
    owner: str,
    parent_run: JobRunModel,
    parent_job: ContextJobModel,
    *,
    notes: str | None = None,
) -> JobRunModel | None:
    if parent_run.amendment_run_id:
        existing = db.query(JobRunModel).filter(JobRunModel.id == parent_run.amendment_run_id).first()
        if existing:
            return existing

    from context_jobs.services.canonical_resolver import resolve_canonical_source

    source_text, resolution_method = resolve_canonical_source(db, owner, parent_run, parent_job)

    if source_text is None:
        rop = dict(parent_run.run_output_package or {})
        rop["amendment"] = {
            "status": "source_not_found",
            "message": (
                "Could not locate the full original contract text. "
                "Re-ingest the source document or attach it manually, then retry."
            ),
        }
        parent_run.run_output_package = rop
        flag_modified(parent_run, "run_output_package")
        db.add(parent_run)
        db.commit()
        return None

    package_name = ensure_context_jobs_access(db, owner)
    assert_can_create_run(db, owner, package_name)
    amendment_job = _ensure_amendment_job(db, owner, parent_job)
    resolve_llm_api_key(
        db,
        owner,
        amendment_job.llm_key_id,
        amendment_job.execution_provider,
        package_name=package_name,
    )

    child = JobRunModel(
        job_id=amendment_job.id,
        user_request=build_amendment_request(parent_run, notes, canonical_source=source_text),
        job_version=amendment_job.version,
        workspace_id=getattr(amendment_job, "workspace_id", None) or default_workspace_id(owner),
        parent_run_id=parent_run.id,
    )
    db.add(child)
    db.commit()
    db.refresh(child)

    # Seed the canonical source to disk so contract-patch can load it
    # without the LLM having to echo back the full text.
    from context_jobs.tools.artifact_paths import run_artifact_dir
    from context_jobs.tools.contract_patch import CANONICAL_SEED_FILENAME

    try:
        seed_dir = run_artifact_dir(owner, str(child.id))
        seed_dir.mkdir(parents=True, exist_ok=True)
        (seed_dir / CANONICAL_SEED_FILENAME).write_text(source_text, encoding="utf-8")
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Could not seed canonical source for amendment run %s", child.id, exc_info=True
        )

    queued = enqueue_run(child.id)
    if not queued:
        child.state = "failed"
        child.outcome = "error"
        child.run_output_package = {
            "status": "failed",
            "primaryResult": {
                "resultType": "text_output",
                "title": "Amendment queue is full",
                "content": "Could not start the revised-contract run because the queue is full. Retry Approve shortly.",
            },
        }
        db.add(child)
        db.commit()
        raise ValueError("Context jobs queue is full. Please retry shortly.")

    record_run_created(db, owner)

    parent_run.amendment_run_id = child.id
    rop = dict(parent_run.run_output_package or {})
    rop["nextAction"] = {
        "type": "generating_revised_contract",
        "label": "Generating revised contract…",
    }
    rop["amendment"] = {
        "runId": str(child.id),
        "jobId": str(amendment_job.id),
        "status": "queued",
        "sourceResolution": resolution_method,
    }
    parent_run.run_output_package = rop
    flag_modified(parent_run, "run_output_package")
    db.add(parent_run)
    db.commit()
    db.refresh(parent_run)
    db.refresh(child)
    return child
