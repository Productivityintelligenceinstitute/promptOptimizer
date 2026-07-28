"""Context Jobs run execution engine."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from context_jobs.agents.catalog import build_delegate_tool_definition, compile_agent_catalog, is_multi_agent_mode
from context_jobs.agents.delegate_runner import AgentDelegateRunner
import context_jobs.audit as cj_audit
from context_jobs.assembly.memory_loader import load_memory_context
from context_jobs.assembly.prompt_builder import assemble_user_message, build_system_prompt
from context_jobs.assembly.output_format import clean_model_output
from context_jobs.assembly.prompt_safety import build_trusted_repair_instruction
from context_jobs.assembly.retrieval_pipeline import execute_retrieval
from context_jobs.ingestion.metadata import extract_retrieval_hints
from context_jobs.assembly.tool_resolver import resolve_tools
from context_jobs.gateway.budget_tracker import BudgetTracker
from context_jobs.gateway.execution_limits import (
    resolve_budget_settings,
    resolve_max_agent_turns,
    resolve_per_request_max_tokens,
)
from context_jobs.gateway.guardrail_gateway import GatewayToolExecutor
from context_jobs.memory.memory_service import persist_memory_updates
from context_jobs.provider_key_services import resolve_llm_api_key
from context_jobs.providers.base import ExecutionEnvelope, ToolCall
from context_jobs.providers.registry import get_default_model, get_provider_adapter
from context_jobs.rop.builder import build_run_output_package, determine_terminal_state
from context_jobs.run_workflows import (
    build_replay_snapshot,
    list_tool_executions,
    should_attempt_repair,
)
from context_jobs.validation.tool_output import merge_tool_execution_sources
from context_jobs.structured_output import extract_structured_output
from context_jobs.text_sanitize import sanitize_db_text
from context_jobs.validation.engine import run_validation
from context_jobs.workspace import default_workspace_id, ensure_default_workspace
from database.database import SessionLocal
from schemas.context_jobs_model import ContextJobModel, ContextJobVersionModel, JobRunModel

logger = logging.getLogger(__name__)


def _tool_enabled(job: ContextJobModel, tool_id: str) -> bool:
    for perm in job.tool_permissions or []:
        if not isinstance(perm, dict) or not perm.get("enabled"):
            continue
        candidate = perm.get("toolId") or perm.get("tool_id")
        if candidate == tool_id:
            return True
    return False


async def _prerun_contract_analyzer(
    tool_executor: GatewayToolExecutor,
    job: ContextJobModel,
    retrieved_context: str,
) -> str | None:
    """
    Deterministically run contract-analyzer before the LLM loop for contract_review.

    Models often skip the tool when RAG already has the MSA text; validation still
    requires structured analyzer output for mandatory_clause.
    """
    if (job.workflow_type or "").lower() != "contract_review":
        return None
    if not _tool_enabled(job, "contract-analyzer"):
        return None
    if not (retrieved_context or "").strip():
        return None

    call = ToolCall(
        id=f"prerun-{uuid.uuid4()}",
        tool_id="contract-analyzer",
        tool_name="Contract Analyzer",
        arguments={
            "source": "text",
            # Gateway consolidates full retrieved_context for source=text.
            "value": retrieved_context[:4000],
            "contractType": "msa",
        },
    )
    result = await tool_executor(call)
    if result.is_error:
        logger.warning(
            "Pre-run contract-analyzer failed for job %s: %s",
            job.id,
            (result.content or "")[:300],
        )
        return None
    return result.content


def execute_run_sync(run_id: UUID) -> None:
    asyncio.run(_execute_run_async(run_id))


def _apply_job_snapshot(job: ContextJobModel, snapshot: dict) -> None:
    for field, value in snapshot.items():
        if field in {"vector_connection_id", "llm_key_id"} and value:
            value = UUID(str(value))
        setattr(job, field, value)


async def _execute_run_async(run_id: UUID) -> None:
    db = SessionLocal()
    started_at = datetime.now(timezone.utc)
    try:
        run = db.query(JobRunModel).filter(JobRunModel.id == run_id).first()
        if not run:
            return
        job = db.query(ContextJobModel).filter(ContextJobModel.id == run.job_id).first()
        if not job:
            _fail_run(db, run, "Context job not found.")
            return
        ensure_default_workspace(db, job.owner or "unknown")
        if (job.status or "draft").lower() != "published":
            _fail_run(
                db,
                run,
                "Job must be published before running. Publish the job first.",
            )
            return
        if run.job_version and int(job.version or 1) != int(run.job_version or 1):
            version_row = (
                db.query(ContextJobVersionModel)
                .filter(
                    ContextJobVersionModel.job_id == job.id,
                    ContextJobVersionModel.version == run.job_version,
                )
                .first()
            )
            if version_row:
                _apply_job_snapshot(job, dict(version_row.snapshot or {}))
                job.version = version_row.version

        run.started_at = started_at
        run.step_logs = []
        db.add(run)
        db.commit()

        budget_settings = resolve_budget_settings(job)
        budget_tracker = BudgetTracker(budget_settings)

        try:
            await _run_stage(db, run, "planning", "Assembling context from job definition")
            system_prompt = build_system_prompt(job, run.user_request or "")
            memory_context = load_memory_context(job.owner, job.id, job.memory_config, db)
            tools = resolve_tools(job.tool_permissions, db)
            # Supplier assessment must stay grounded in retrieved vendor evidence.
            # Existing jobs may still list web-search — strip it at runtime.
            if (job.workflow_type or "").lower() == "supplier_assessment":
                tools = [tool for tool in tools if tool.id != "web-search"]
            agent_catalog = compile_agent_catalog(job)
            delegate_tool = build_delegate_tool_definition(agent_catalog)
            if delegate_tool:
                tools = tools + [delegate_tool]
            _complete_stage(db, run)

            await _run_stage(db, run, "retrieving", "Executing retrieval pipeline")
            combined_for_hints = f"{job.goal or ''}\n\n{run.user_request or ''}".strip()
            retrieval_hints = extract_retrieval_hints(combined_for_hints)
            if (job.workflow_type or "").lower() == "contract_review":
                retrieval_hints.setdefault("contractRenewal", True)
            retrieval = execute_retrieval(
                job,
                run.user_request or "",
                db,
                retrieval_hints=retrieval_hints,
            )
            run.retrieval_events = retrieval.retrieval_events
            run.source_trace_events = retrieval.source_trace_events
            db.add(run)
            db.commit()
            _complete_stage(db, run)

            provider = (job.execution_provider or "openai").lower()
            model = job.execution_model or get_default_model(provider)
            _, api_key = resolve_llm_api_key(db, job.owner, job.llm_key_id, job.execution_provider)

            delegate_runner = None
            if is_multi_agent_mode(job) and agent_catalog:
                delegate_runner = AgentDelegateRunner(
                    job=job,
                    run=run,
                    db=db,
                    budget_tracker=budget_tracker,
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    catalog=agent_catalog,
                    base_tool_definitions=tools,
                )

            await _run_stage(db, run, "executing", f"Executing with provider {provider}")
            user_message = assemble_user_message(
                run.user_request or job.goal or "",
                retrieval.rag_context,
                memory_context,
            )
            response, tool_executor = await _execute_with_provider(
                db, run, job, provider, model, api_key, system_prompt, user_message,
                tools, agent_catalog, delegate_runner, budget_tracker,
                retrieved_context=retrieval.rag_context,
            )

            validation_summary, events = await _validate_output(
                db,
                run,
                job,
                response.content or "",
                retrieval.source_trace_events,
                tool_executor=tool_executor,
            )

            # Repair loop: one retry on needs_repair
            while should_attempt_repair(run, validation_summary.status):
                run.repair_cycles = int(getattr(run, "repair_cycles", None) or 0) + 1
                db.add(run)
                db.commit()
                await _run_stage(
                    db,
                    run,
                    "executing",
                    f"Repair attempt {run.repair_cycles}",
                )
                repair_message = build_trusted_repair_instruction(
                    validation_summary.repair_reason,
                )
                user_message = assemble_user_message(
                    run.user_request or job.goal or "",
                    retrieval.rag_context,
                    memory_context,
                    trusted_suffix=repair_message,
                )
                response, tool_executor = await _execute_with_provider(
                    db, run, job, provider, model, api_key, system_prompt, user_message,
                    tools, agent_catalog, delegate_runner, budget_tracker,
                    retrieved_context=retrieval.rag_context,
                )
                validation_summary, events = await _validate_output(
                    db,
                    run,
                    job,
                    response.content or "",
                    retrieval.source_trace_events,
                    tool_executor=tool_executor,
                )
                _complete_stage(db, run)

            ended_at = datetime.now(timezone.utc)
            db.refresh(run)
            structured = extract_structured_output(
                response.content or "",
                job.output_template or job.semantic_blueprint,
            )
            rop = build_run_output_package(
                run=run,
                job=job,
                validation_summary=validation_summary,
                source_traces=retrieval.source_trace_events,
                tool_executor=tool_executor,
                budget_tracker=budget_tracker,
                response=response,
                started_at=started_at,
                ended_at=ended_at,
                repair_cycles=int(getattr(run, "repair_cycles", None) or 0),
                structured_output=structured,
            )
            state, outcome = determine_terminal_state(rop["status"])
            run.state = state
            run.outcome = outcome
            run.run_output_package = rop
            run.replay_snapshot = build_replay_snapshot(
                run,
                job,
                response.content or "",
                run.retrieval_events or [],
                retrieval.source_trace_events,
                run.validation_events or [],
            )
            run.workspace_id = getattr(job, "workspace_id", None) or default_workspace_id(job.owner or "")
            run.ended_at = ended_at
            run.latency_ms = int((ended_at - started_at).total_seconds() * 1000)
            _finalize_running_step_logs(run)
            db.add(run)
            db.commit()

            if state == "escalated":
                cj_audit.write_audit_event(
                    db,
                    event_type="run.escalated",
                    entity_type="run",
                    entity_id=str(run.id),
                    actor=job.owner,
                    metadata={
                        "status": rop.get("status"),
                        "outcome": outcome,
                        "approvalState": rop.get("auditMetadata", {}).get("approvalState"),
                    },
                )

            if job.memory_config:
                changes = await persist_memory_updates(run, job, response.content or "", db)
                rop = dict(run.run_output_package or rop)
                rop["memoryStateChanges"] = {
                    "updated": bool(changes),
                    "approvalRequired": bool(run.pending_memory_changes),
                    "approvalGranted": not bool(run.pending_memory_changes) and bool(changes),
                    "changes": changes,
                }
                if run.pending_memory_changes:
                    run.state = "awaiting_memory_approval"
                run.run_output_package = rop
                db.add(run)
                db.commit()

            db.refresh(run)
            if run.state in ("completed", "completed_with_warnings"):
                try:
                    from context_jobs.chain_runner import prepare_chain_handoff

                    prepare_chain_handoff(run.id, run.run_output_package or rop, db)
                except Exception:
                    logger.exception("Chain handoff preparation failed for run %s", run.id)

            chain_status = None
            if run.state in ("completed", "completed_with_warnings"):
                chain_status = "completed"
            elif run.state in ("escalated", "failed"):
                chain_status = "failed"
            if chain_status is not None:
                try:
                    db.execute(
                        text(
                            "UPDATE run_chains SET status = :status WHERE child_run_id = :run_id"
                        ),
                        {"status": chain_status, "run_id": run.id},
                    )
                    db.commit()
                except Exception:
                    logger.exception("RunChain status update failed for run %s", run.id)

        except Exception as exc:
            _fail_run(db, run.id, str(exc))

    finally:
        db.close()


async def _execute_with_provider(
    db: Session,
    run: JobRunModel,
    job: ContextJobModel,
    provider: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_message: str,
    tools: list,
    agent_catalog,
    delegate_runner,
    budget_tracker: BudgetTracker,
    retrieved_context: str = "",
) -> tuple[Any, GatewayToolExecutor]:
    budget_settings = resolve_budget_settings(job)
    envelope = ExecutionEnvelope(
        system_prompt=system_prompt,
        user_message=user_message,
        tools=tools,
        max_tokens=resolve_per_request_max_tokens(budget_settings),
        max_turns=resolve_max_agent_turns(job),
        temperature=0.2,
        model=model,
        metadata={"job_id": str(job.id), "run_id": str(run.id), "owner": job.owner},
    )
    tool_executor = GatewayToolExecutor(
        job=job,
        run=run,
        budget_tracker=budget_tracker,
        db=db,
        agent_catalog=agent_catalog,
        delegate_runner=delegate_runner,
        allow_delegation=bool(delegate_runner),
        retrieved_context=retrieved_context,
    )
    analyzer_json = await _prerun_contract_analyzer(tool_executor, job, retrieved_context)
    if analyzer_json:
        user_message = (
            f"{user_message}\n\n"
            "## Pre-run contract-analyzer output (trusted structured extraction)\n"
            "Use this JSON as the primary clause inventory. Still cite Retrieved Context.\n"
            f"{analyzer_json}"
        )
        envelope = replace(envelope, user_message=user_message)
    adapter = get_provider_adapter(provider)
    response = await adapter.execute(envelope, api_key, tool_executor)
    budget_tracker.record_tokens(response.input_tokens, response.output_tokens, response.model)

    cleaned_content = clean_model_output(response.content or "", job)
    response = replace(response, content=cleaned_content)
    run.output_text = cleaned_content
    run.execution_provider = provider
    run.execution_model = response.model
    run.total_provider_tokens = response.input_tokens + response.output_tokens
    run.total_tool_calls = tool_executor.total_calls
    run.agent_turns = response.agent_turns
    run.token_usage = run.total_provider_tokens
    run.tool_events = tool_executor.executed_calls
    if delegate_runner and delegate_runner.delegation_events:
        run.tool_events = (run.tool_events or []) + [
            {"type": "delegation", **event} for event in delegate_runner.delegation_events
        ]
    run.estimated_cost_usd = budget_tracker.cost_usd
    db.add(run)
    db.commit()
    _complete_stage(db, run)
    return response, tool_executor


async def _validate_output(
    db: Session,
    run: JobRunModel,
    job: ContextJobModel,
    output_text: str,
    source_traces: list,
    tool_executor: GatewayToolExecutor | None = None,
) -> tuple[Any, list]:
    await _run_stage(db, run, "validating", "Running validation rules")
    memory_outputs = getattr(tool_executor, "tool_outputs", None) if tool_executor else None
    tool_executions = merge_tool_execution_sources(
        list_tool_executions(db, run.id),
        memory_outputs,
    )
    events, validation_summary = await run_validation(
        output_text=output_text,
        job=job,
        source_traces=source_traces,
        tool_executions=tool_executions,
        tool_events=run.tool_events or [],
    )
    run.validation_events = [
        {
            "rule": e.rule,
            "passed": e.passed,
            "message": e.message,
            "severity": e.severity,
        }
        for e in events
    ]
    db.add(run)
    db.commit()
    _complete_stage(db, run)

    if validation_summary.status in {"needs_repair", "blocked_by_policy"}:
        cj_audit.write_audit_event(
            db,
            event_type="validation.failed",
            entity_type="run",
            entity_id=str(run.id),
            actor=job.owner,
            metadata={
                "status": validation_summary.status,
                "repairReason": validation_summary.repair_reason,
                "failedChecks": [e.rule for e in events if not e.passed],
            },
        )
    return validation_summary, events


async def _run_stage(db: Session, run: JobRunModel, step_name: str, details: str) -> None:
    run = db.query(JobRunModel).filter(JobRunModel.id == run.id).first()
    if not run:
        return
    logs = [dict(log) if isinstance(log, dict) else log for log in (run.step_logs or [])]
    logs.append(
        {
            "step": step_name,
            "status": "running",
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "details": details,
        }
    )
    run.state = step_name
    run.step_logs = logs
    flag_modified(run, "step_logs")
    db.add(run)
    db.commit()


def _complete_stage(db: Session, run: JobRunModel) -> None:
    run = db.query(JobRunModel).filter(JobRunModel.id == run.id).first()
    if not run:
        return
    logs = [dict(log) if isinstance(log, dict) else log for log in (run.step_logs or [])]
    if logs:
        ended_at = datetime.now(timezone.utc).isoformat()
        logs[-1] = {**logs[-1], "status": "completed", "endedAt": ended_at}
    run.step_logs = logs
    flag_modified(run, "step_logs")
    db.add(run)
    db.commit()


def _finalize_running_step_logs(run_row: JobRunModel) -> None:
    """Mark any step logs still running as completed when the run reaches a terminal state."""
    logs = [dict(log) if isinstance(log, dict) else log for log in (run_row.step_logs or [])]
    if not logs:
        return
    ended_at = datetime.now(timezone.utc).isoformat()
    changed = False
    for index, log in enumerate(logs):
        if isinstance(log, dict) and log.get("status") == "running":
            logs[index] = {**log, "status": "completed", "endedAt": log.get("endedAt") or ended_at}
            changed = True
    if not changed:
        return
    run_row.step_logs = logs
    flag_modified(run_row, "step_logs")


def _fail_run(db: Session, run: JobRunModel | UUID, message: str) -> None:
    run_id = run.id if isinstance(run, JobRunModel) else run
    try:
        db.rollback()
    except Exception:
        pass

    safe_message = sanitize_db_text(message)
    run_row = db.query(JobRunModel).filter(JobRunModel.id == run_id).first()
    if not run_row:
        return

    step_logs = [dict(log) if isinstance(log, dict) else log for log in (run_row.step_logs or [])]
    run_row.state = "failed"
    run_row.outcome = "error"
    run_row.ended_at = datetime.now(timezone.utc)
    run_row.run_output_package = {
        "status": "failed",
        "primaryResult": {
            "resultType": "text_output",
            "title": "Run failed",
            "content": safe_message,
        },
        "validationSummary": {
            "overallDecision": "failed",
            "confidenceLevel": "low",
            "checks": [],
        },
        "sourceSummary": {"groundedMode": False, "sourcesUsed": [], "overallEvidenceStrength": "unavailable"},
        "warnings": [],
        "exceptions": [
            {
                "code": "RUNTIME_FAILURE",
                "severity": "critical",
                "message": safe_message,
                "relatedStep": "executing",
                "suggestedAction": "Retry when issue is resolved",
            }
        ],
        "nextAction": {"type": "retry_later", "label": "Retry when issue is resolved"},
        "traceSummary": {
            "stages": [log.get("step") for log in step_logs if isinstance(log, dict)],
            "toolEvents": len(run_row.tool_events or []),
            "retrievalEvents": len(run_row.retrieval_events or []),
            "repairCycles": int(getattr(run_row, "repair_cycles", None) or 0),
            "replayAvailable": True,
        },
        "memoryStateChanges": {"updated": False, "changes": []},
        "costTimeSummary": {
            "startedAt": (run_row.started_at or datetime.now(timezone.utc)).isoformat(),
            "endedAt": datetime.now(timezone.utc).isoformat(),
            "runtimeSeconds": 0,
            "estimatedCost": "$0.0000",
            "toolUsageCount": len(run_row.tool_events or []),
            "retrievalUsageCount": len(run_row.retrieval_events or []),
        },
        "auditMetadata": {
            "runId": str(run_row.id),
            "jobId": str(run_row.job_id),
            "jobVersion": run_row.job_version or 1,
            "workspaceId": "default",
            "actor": "unknown",
            "environment": "development",
            "approvalState": "not_required",
            "policyProfile": "default",
        },
    }
    if step_logs:
        ended_at = datetime.now(timezone.utc).isoformat()
        step_logs[-1] = {
            **step_logs[-1],
            "status": "failed",
            "endedAt": ended_at,
            "details": safe_message[:500],
        }
        run_row.step_logs = step_logs
        flag_modified(run_row, "step_logs")
    _finalize_running_step_logs(run_row)
    db.add(run_row)
    try:
        db.commit()
    except Exception:
        db.rollback()
