"""Context Jobs run execution engine."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs.agents.catalog import build_delegate_tool_definition, compile_agent_catalog, is_multi_agent_mode
from context_jobs.agents.delegate_runner import AgentDelegateRunner
import context_jobs.audit as cj_audit
from context_jobs.assembly.memory_loader import load_memory_context
from context_jobs.assembly.prompt_builder import assemble_user_message, build_system_prompt
from context_jobs.assembly.retrieval_pipeline import execute_retrieval
from context_jobs.assembly.tool_resolver import resolve_tools
from context_jobs.gateway.budget_tracker import BudgetTracker
from context_jobs.gateway.guardrail_gateway import GatewayToolExecutor
from context_jobs.memory.memory_service import persist_memory_updates
from context_jobs.provider_key_services import resolve_llm_api_key
from context_jobs.providers.base import ExecutionEnvelope
from context_jobs.providers.registry import get_default_model, get_provider_adapter
from context_jobs.rop.builder import build_run_output_package, determine_terminal_state
from context_jobs.run_workflows import (
    build_repair_user_message,
    build_replay_snapshot,
    should_attempt_repair,
)
from context_jobs.structured_output import extract_structured_output
from context_jobs.validation.engine import run_validation
from context_jobs.workspace import default_workspace_id, ensure_default_workspace
from database.database import SessionLocal
from schemas.context_jobs_model import ContextJobModel, ContextJobVersionModel, JobRunModel


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

        budget_tracker = BudgetTracker(job.budget_settings or {})

        try:
            await _run_stage(db, run, "planning", "Assembling context from job definition")
            system_prompt = build_system_prompt(job, run.user_request or "")
            memory_context = load_memory_context(job.owner, job.id, job.memory_config, db)
            tools = resolve_tools(job.tool_permissions, db)
            agent_catalog = compile_agent_catalog(job)
            delegate_tool = build_delegate_tool_definition(agent_catalog)
            if delegate_tool:
                tools = tools + [delegate_tool]
            _complete_stage(db, run)

            await _run_stage(db, run, "retrieving", "Executing retrieval pipeline")
            retrieval = execute_retrieval(job, run.user_request or "", db)
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
                    base_tool_definitions=resolve_tools(job.tool_permissions, db),
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
            )

            validation_summary, events = await _validate_output(
                db, run, job, response.content or "", retrieval.source_trace_events
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
                repair_message = build_repair_user_message(
                    run.user_request or job.goal or "",
                    validation_summary.repair_reason,
                )
                user_message = assemble_user_message(
                    repair_message,
                    retrieval.rag_context,
                    memory_context,
                )
                response, tool_executor = await _execute_with_provider(
                    db, run, job, provider, model, api_key, system_prompt, user_message,
                    tools, agent_catalog, delegate_runner, budget_tracker,
                )
                validation_summary, events = await _validate_output(
                    db, run, job, response.content or "", retrieval.source_trace_events
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

        except Exception as exc:
            _fail_run(db, run, str(exc))

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
) -> tuple[Any, GatewayToolExecutor]:
    envelope = ExecutionEnvelope(
        system_prompt=system_prompt,
        user_message=user_message,
        tools=tools,
        max_tokens=int((job.budget_settings or {}).get("maxTokens") or 4096),
        max_turns=int(job.max_agent_turns or 10),
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
    )
    adapter = get_provider_adapter(provider)
    response = await adapter.execute(envelope, api_key, tool_executor)
    budget_tracker.record_tokens(response.input_tokens, response.output_tokens, response.model)

    run.output_text = response.content
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
) -> tuple[Any, list]:
    await _run_stage(db, run, "validating", "Running validation rules")
    events, validation_summary = await run_validation(
        output_text=output_text,
        job=job,
        source_traces=source_traces,
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
    logs = list(run.step_logs or [])
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
    db.add(run)
    db.commit()


def _complete_stage(db: Session, run: JobRunModel) -> None:
    run = db.query(JobRunModel).filter(JobRunModel.id == run.id).first()
    if not run:
        return
    logs = list(run.step_logs or [])
    if logs:
        logs[-1]["status"] = "completed"
        logs[-1]["endedAt"] = datetime.now(timezone.utc).isoformat()
    run.step_logs = logs
    db.add(run)
    db.commit()


def _fail_run(db: Session, run: JobRunModel, message: str) -> None:
    run.state = "failed"
    run.outcome = "error"
    run.ended_at = datetime.now(timezone.utc)
    run.run_output_package = {
        "status": "failed",
        "primaryResult": {
            "resultType": "text_output",
            "title": "Run failed",
            "content": message,
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
                "message": message,
                "relatedStep": "executing",
                "suggestedAction": "Retry when issue is resolved",
            }
        ],
        "nextAction": {"type": "retry_later", "label": "Retry when issue is resolved"},
        "traceSummary": {
            "stages": [log.get("step") for log in (run.step_logs or []) if isinstance(log, dict)],
            "toolEvents": len(run.tool_events or []),
            "retrievalEvents": len(run.retrieval_events or []),
            "repairCycles": 0,
            "replayAvailable": True,
        },
        "memoryStateChanges": {"updated": False, "changes": []},
        "costTimeSummary": {
            "startedAt": (run.started_at or datetime.now(timezone.utc)).isoformat(),
            "endedAt": datetime.now(timezone.utc).isoformat(),
            "runtimeSeconds": 0,
            "estimatedCost": "$0.0000",
            "toolUsageCount": len(run.tool_events or []),
            "retrievalUsageCount": len(run.retrieval_events or []),
        },
        "auditMetadata": {
            "runId": str(run.id),
            "jobId": str(run.job_id),
            "jobVersion": run.job_version or 1,
            "workspaceId": "default",
            "actor": "unknown",
            "environment": "development",
            "approvalState": "not_required",
            "policyProfile": "default",
        },
    }
    db.add(run)
    db.commit()
