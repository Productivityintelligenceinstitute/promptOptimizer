"""Context Jobs run execution engine."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs.agents.catalog import build_delegate_tool_definition, compile_agent_catalog, is_multi_agent_mode
from context_jobs.agents.delegate_runner import AgentDelegateRunner
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
from context_jobs.validation.engine import run_validation
from database.database import SessionLocal
from schemas.context_jobs_model import ContextJobModel, JobRunModel


def execute_run_sync(run_id: UUID) -> None:
    asyncio.run(_execute_run_async(run_id))


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

        run.started_at = started_at
        run.step_logs = []
        db.add(run)
        db.commit()

        budget_tracker = BudgetTracker(job.budget_settings or {})

        try:
            await _run_stage(db, run, "planning", "Assembling context from job definition")
            system_prompt = build_system_prompt(job)
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
            _, api_key = resolve_llm_api_key(db, job.owner, job.llm_key_id)

            await _run_stage(db, run, "executing", f"Executing with provider {provider}")
            user_message = assemble_user_message(
                run.user_request or job.goal or "",
                retrieval.rag_context,
                memory_context,
            )
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

            await _run_stage(db, run, "validating", "Running validation rules")
            events, validation_summary = await run_validation(
                output_text=response.content or "",
                job=job,
                source_traces=retrieval.source_trace_events,
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

            ended_at = datetime.now(timezone.utc)
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
            )
            state, outcome = determine_terminal_state(rop["status"])
            run.state = state
            run.outcome = outcome
            run.run_output_package = rop
            run.ended_at = ended_at
            run.latency_ms = int((ended_at - started_at).total_seconds() * 1000)
            db.add(run)
            db.commit()

            if job.memory_config:
                changes = await persist_memory_updates(run, job, response.content or "", db)
                rop["memoryStateChanges"]["changes"] = changes
                run.run_output_package = rop
                db.add(run)
                db.commit()

        except Exception as exc:
            _fail_run(db, run, str(exc))

    finally:
        db.close()


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
            "jobVersion": 1,
            "workspaceId": "default",
            "actor": "unknown",
            "environment": "development",
            "approvalState": "not_required",
            "policyProfile": "default",
        },
    }
    db.add(run)
    db.commit()
