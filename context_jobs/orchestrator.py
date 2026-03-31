import threading
import time
from queue import Empty, Full, Queue
from datetime import datetime, timezone
from uuid import UUID

from database.database import SessionLocal
from schemas.context_jobs_model import ContextJobModel, JobRunModel
from schemas.context_vector_connection_model import ContextVectorConnectionModel
from core.config import client, GEN_MODEL
from utils.utils import build_jet_system_prompt
from context_jobs.retrieval.factory import get_retrieval_adapter
from context_jobs.retrieval.security import decrypt_config

RUN_QUEUE_MAXSIZE = 50
RUN_WORKER_COUNT = 2
_run_queue: Queue[UUID] = Queue(maxsize=RUN_QUEUE_MAXSIZE)
_workers: list[threading.Thread] = []
_workers_lock = threading.Lock()
_active_runs = 0
_active_runs_lock = threading.Lock()
_stop_event = threading.Event()


def start_mock_run_workers(worker_count: int = RUN_WORKER_COUNT) -> None:
    with _workers_lock:
        if _workers:
            return
        _stop_event.clear()
        for i in range(worker_count):
            worker = threading.Thread(
                target=_run_worker_loop,
                name=f"context-jobs-worker-{i + 1}",
                daemon=True,
            )
            worker.start()
            _workers.append(worker)


def stop_mock_run_workers(timeout_seconds: float = 2.0) -> None:
    with _workers_lock:
        if not _workers:
            return
        _stop_event.set()
        for _ in _workers:
            try:
                _run_queue.put_nowait(UUID(int=0))
            except Full:
                break
        for worker in _workers:
            worker.join(timeout=timeout_seconds)
        _workers.clear()


def enqueue_mock_run(run_id: UUID) -> bool:
    try:
        _run_queue.put_nowait(run_id)
        return True
    except Full:
        return False


def get_mock_queue_status() -> dict:
    with _active_runs_lock:
        active_runs = _active_runs
    return {
        "active_runs": active_runs,
        "queued_runs": _run_queue.qsize(),
        "queue_capacity": RUN_QUEUE_MAXSIZE,
        "workers": len(_workers),
    }


def _run_worker_loop() -> None:
    global _active_runs
    while not _stop_event.is_set():
        try:
            run_id = _run_queue.get(timeout=0.5)
        except Empty:
            continue
        try:
            if run_id.int == 0:
                continue
            with _active_runs_lock:
                _active_runs += 1
            _execute_mock_run(run_id)
        finally:
            with _active_runs_lock:
                _active_runs = max(0, _active_runs - 1)
            _run_queue.task_done()


def _execute_mock_run(run_id: UUID) -> None:
    db = SessionLocal()
    try:
        run = db.query(JobRunModel).filter(JobRunModel.id == run_id).first()
        if not run:
            return
        job = db.query(ContextJobModel).filter(ContextJobModel.id == run.job_id).first()
        if not job:
            run.state = "failed"
            run.outcome = "error"
            run.ended_at = datetime.now(timezone.utc)
            run.run_output_package = {
                "status": "failed",
                "primaryResult": {
                    "resultType": "text_output",
                    "title": "Run failed",
                    "content": "Context job not found.",
                },
            }
            db.add(run)
            db.commit()
            return

        started_at = datetime.now(timezone.utc)
        run.started_at = started_at
        run.step_logs = []
        db.add(run)
        db.commit()

        def _commit_step(step_name: str, details: str, fn):
            nonlocal run
            # Reload for latest state in case of race
            run = db.query(JobRunModel).filter(JobRunModel.id == run_id).first()
            if not run:
                return False

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

            try:
                result = fn()
            except Exception:
                raise

            run = db.query(JobRunModel).filter(JobRunModel.id == run_id).first()
            if not run:
                return False
            logs = list(run.step_logs or [])
            if logs:
                logs[-1]["status"] = "completed"
                logs[-1]["endedAt"] = datetime.now(timezone.utc).isoformat()
            run.step_logs = logs
            db.add(run)
            db.commit()
            return result

        context_job_request_text = (run.user_request or "").strip() or (job.goal or "").strip()

        # 1) Planning: assemble context window (we do actual retrieval in the next stage).
        planning_result = _commit_step(
            "planning",
            "Building planning context window",
            lambda: {
                "workflow_type": (job.workflow_type or "standard"),
                "role_configuration": (job.role_configuration or ""),
                "stable_instructions": (job.stable_instructions or ""),
                "semantic_blueprint": (job.semantic_blueprint or ""),
                "glossary_terms": job.glossary_terms or [],
                "relationships": job.relationships or [],
                "goal": job.goal or "",
            },
        )
        if planning_result is False:
            return

        # 2) Retrieving: real Pinecone RAG.
        retrieved = {"matches": [], "rag_context": "", "retrieval_events": [], "source_trace_events": []}

        def _retrieve_fn():
            nonlocal retrieved

            retrieval_config = job.retrieval_config or {}
            top_k = 8
            if isinstance(retrieval_config, dict):
                try:
                    top_k = int(retrieval_config.get("maxDocuments") or top_k)
                except Exception:
                    top_k = 8

            # B) Combined query: goal + user request
            combined_query = f"{job.goal or ''}\n\n{run.user_request or ''}".strip()
            if not combined_query:
                combined_query = context_job_request_text or "general request"

            retrieval_mode = (getattr(job, "retrieval_mode", None) or "jet_kb").lower()
            vector_connection_id = getattr(job, "vector_connection_id", None)
            adapter = None
            if retrieval_mode == "external":
                if not vector_connection_id:
                    raise ValueError("Job retrieval_mode is external but vector_connection_id is not set.")
                vector_conn = (
                    db.query(ContextVectorConnectionModel)
                    .filter(ContextVectorConnectionModel.id == vector_connection_id)
                    .first()
                )
                if not vector_conn:
                    raise ValueError("Configured vector connection not found.")
                if vector_conn.status != "active":
                    raise ValueError(f"Configured vector connection is not active (status={vector_conn.status}).")
                conn_config = decrypt_config(vector_conn.encrypted_config or {})
                adapter = get_retrieval_adapter(vector_conn.provider, conn_config)
            else:
                adapter = get_retrieval_adapter("jet_kb", {})

            matches = adapter.search(combined_query, top_k=top_k) or []

            context_blocks = []
            retrieval_events = []
            source_trace_events = []

            now_iso = datetime.now(timezone.utc).isoformat()
            for m in matches:
                meta = getattr(m, "metadata", None) or {}
                file_name = meta.get("file") or meta.get("source") or "Workspace Knowledge"
                jet_layer = meta.get("jet_layer") or "misc"
                preview = (getattr(m, "text_preview", None) or meta.get("preview") or "")[:600]
                score = getattr(m, "score", None)

                context_blocks.append(f"[source:{file_name} layer:{jet_layer}]\n{preview}")
                retrieval_events.append(
                    {
                        "query": combined_query,
                        "source": file_name,
                        "resultCount": 1,
                        "timestamp": now_iso,
                    }
                )

                # Map Pinecone score to evidenceStrength used by the UI (strong/moderate/weak)
                try:
                    score_val = float(score) if score is not None else 0.0
                except Exception:
                    score_val = 0.0
                if score_val >= 0.7:
                    evidence_strength = "strong"
                elif score_val >= 0.45:
                    evidence_strength = "moderate"
                else:
                    evidence_strength = "weak"

                source_trace_events.append(
                    {
                        "sourceId": str(getattr(m, "id", file_name)),
                        "sourceName": file_name,
                        "sourceType": meta.get("source") or "document",
                        "factsCited": 1,
                        "trustLevel": "preferred",
                        "lastUpdated": None,
                        "freshnessStatus": "current",
                        "warnings": [],
                        "evidenceStrength": evidence_strength,
                    }
                )

            rag_context = "\n\n---\n\n".join(context_blocks) if context_blocks else "No context retrieved."
            retrieved = {
                "matches": matches,
                "rag_context": rag_context,
                "retrieval_events": retrieval_events,
                "source_trace_events": source_trace_events,
            }
            return True

        retrieved_ok = _commit_step(
            "retrieving",
            "Retrieving relevant Jet KB context (Pinecone)",
            _retrieve_fn,
        )
        if retrieved_ok is False:
            return

        # 3) Executing: real generation from retrieved context + job configuration.
        def _execute_fn():
            workflow_type = planning_result.get("workflow_type") or "standard"

            # Choose Jet system style by workflow type (Quick vs Mastery)
            mode = "Mastery" if workflow_type in {"analysis", "research", "generation", "decision", "review"} else "Quick"
            system_prompt = build_jet_system_prompt(mode)
            system_prompt += "\n\nCitation format requirement: use exactly [source:{file} layer:{jet_layer}] as seen in the context blocks.\n"

            role_configuration = planning_result.get("role_configuration") or ""
            stable_instructions = planning_result.get("stable_instructions") or ""
            semantic_blueprint = planning_result.get("semantic_blueprint") or ""

            # Budget
            budget = job.budget_settings or {}
            max_tokens = 1200
            if isinstance(budget, dict):
                try:
                    max_tokens = int(budget.get("maxTokens") or max_tokens)
                except Exception:
                    pass
            max_tokens = max(256, min(2048, max_tokens))

            glossary_terms = job.glossary_terms or []
            relationships = job.relationships or []

            glossary_str = ", ".join([t.get("term") or t.get("id") for t in glossary_terms if isinstance(t, dict)])[:1200]
            relationships_str = ", ".join([r.get("relation") or r.get("id") for r in relationships if isinstance(r, dict)])[:1200]

            user_request = context_job_request_text

            user_prompt = (
                f"Context Job Name: {job.name}\n"
                f"Goal: {job.goal}\n"
                f"Workflow Type: {workflow_type}\n"
                f"Role Configuration: {role_configuration}\n"
                f"Semantic Blueprint: {semantic_blueprint}\n"
                f"Stable Instructions:\n{stable_instructions}\n"
                f"Glossary Terms: {glossary_str}\n"
                f"Relationships: {relationships_str}\n\n"
                f"User Request:\n{user_request}\n\n"
                f"Retrieved Jet KB Context:\n{retrieved['rag_context']}\n\n"
                "Execution requirements:\n"
                "- Use the retrieved context to answer.\n"
                "- When you mention facts from the context, include citations using the required citation format.\n"
                "- If the context does not support an answer, say so explicitly.\n"
                f"- Output style: {workflow_type}.\n"
            )

            chat = client.chat.completions.create(
                model=GEN_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
            )

            output_text = chat.choices[0].message.content or ""
            token_usage = None
            try:
                if getattr(chat, "usage", None) is not None:
                    token_usage = int(chat.usage.total_tokens)
            except Exception:
                token_usage = None

            return {"output_text": output_text, "token_usage": token_usage}

        exec_result = _commit_step(
            "executing",
            "Generating output with retrieved context + OpenAI",
            _execute_fn,
        )
        if exec_result is False:
            return

        output_text = exec_result.get("output_text") or ""
        token_usage = exec_result.get("token_usage")

        # 4) Validating: rule-based minimal validation (groundedness/citations heuristic).
        validation_rules = [
            r
            for r in (list(job.validation_rules or []) if isinstance(job.validation_rules, list) else [])
            if isinstance(r, dict) and r.get("enabled", False)
        ]

        def _validate_fn():
            any_warning = False
            any_error = False
            any_blocking = False
            validation_events = []

            def _citation_present() -> bool:
                return "[source:" in (output_text or "")

            for rule in validation_rules:
                severity = str(rule.get("severity", "warning"))
                rule_type = str(rule.get("type", "custom"))
                rule_name = str(rule.get("name", "Validation rule"))

                if rule_type in {"groundedness", "citation", "format"}:
                    passed = _citation_present()
                    message = "Required citations present." if passed else "Missing citations from retrieved context."
                else:
                    passed = bool(output_text.strip())
                    message = "Check passed" if passed else "Needs attention"

                if not passed and severity == "warning":
                    any_warning = True
                if not passed and severity == "error":
                    any_error = True
                if not passed and severity == "blocking":
                    any_blocking = True

                validation_events.append(
                    {
                        "rule": rule_name,
                        "passed": passed,
                        "message": message,
                        "severity": severity,
                    }
                )

            if any_blocking:
                terminal_state = "escalated"
                status = "blocked_by_policy"
                outcome = "escalated"
                next_action = {"type": "escalate", "label": "Escalate for policy review"}
            elif any_error:
                terminal_state = "repair"
                status = "needs_repair"
                outcome = "needs_review"
                next_action = {"type": "repair_and_rerun", "label": "Fix failed checks and re-run"}
            elif any_warning:
                terminal_state = "completed"
                status = "completed_with_warnings"
                outcome = "accepted_with_warnings"
                next_action = {"type": "review_result", "label": "Review warnings before using"}
            else:
                terminal_state = "completed"
                status = "completed"
                outcome = "accepted"
                next_action = {"type": "use_result", "label": "Result ready to use"}

            return {
                "validation_events": validation_events,
                "terminal_state": terminal_state,
                "status": status,
                "outcome": outcome,
                "next_action": next_action,
            }

        validate_result = _commit_step(
            "validating",
            "Validating output against enabled rules",
            _validate_fn,
        )
        if validate_result is False:
            return

        ended_at = datetime.now(timezone.utc)
        runtime_seconds = max(0.1, (ended_at - started_at).total_seconds())

        validation_events = validate_result.get("validation_events") or []
        terminal_state = validate_result.get("terminal_state") or "completed"
        status = validate_result.get("status") or "completed"
        outcome = validate_result.get("outcome") or "accepted"
        next_action = validate_result.get("next_action") or {"type": "use_result", "label": "Result ready to use"}

        def _result_type_map(wf: str) -> str:
            mapping = {
                "standard": "text_output",
                "analysis": "structured_summary",
                "research": "citation_backed_answer",
                "generation": "formatted_prompt",
                "decision": "decision_memo",
                "review": "recommendation",
                "monitoring": "checklist",
            }
            return mapping.get(wf, "text_output")

        # Build compact source summary from retrieval/source trace events
        grounded_mode = bool(retrieved["source_trace_events"])

        run = db.query(JobRunModel).filter(JobRunModel.id == run_id).first()
        if not run:
            return

        run.state = terminal_state
        run.outcome = outcome
        run.ended_at = ended_at
        run.retrieval_events = retrieved["retrieval_events"]
        run.source_trace_events = retrieved["source_trace_events"]
        run.validation_events = validation_events
        run.output_text = output_text
        run.token_usage = token_usage
        run.latency_ms = int(runtime_seconds * 1000)

        run_output_package = {
            "status": status,
            "primaryResult": {
                "resultType": _result_type_map(planning_result.get("workflow_type") or "standard"),
                "title": f"{job.name} - Context Result",
                "content": output_text,
            },
            "validationSummary": {
                "overallDecision": "passed_with_warnings"
                if status == "completed_with_warnings"
                else ("failed" if status in {"needs_repair", "blocked_by_policy"} else "passed"),
                "confidenceLevel": "medium" if status == "completed_with_warnings" else ("low" if status != "completed" else "high"),
                "checks": [
                    {
                        "name": ev["rule"],
                        "result": "passed"
                        if ev["passed"]
                        else ("warning" if ev["severity"] == "warning" else "failed"),
                        "message": ev["message"],
                    }
                    for ev in validation_events
                ],
            },
            "sourceSummary": {
                "groundedMode": grounded_mode,
                "sourcesUsed": [
                    {
                        "sourceId": st.get("sourceId"),
                        "title": st.get("sourceName"),
                        "sourceType": st.get("sourceType"),
                        "freshness": st.get("freshnessStatus"),
                        "evidenceStrength": st.get("evidenceStrength"),
                        "trustLevel": st.get("trustLevel"),
                    }
                    for st in retrieved["source_trace_events"]
                ],
                "overallEvidenceStrength": "sufficient" if grounded_mode else "unavailable",
            },
            "warnings": [],
            "exceptions": [],
            "nextAction": next_action,
            "traceSummary": {
                "stages": ["planning", "retrieving", "executing", "validating"],
                "toolEvents": 0,
                "retrievalEvents": len(retrieved["retrieval_events"]),
                "repairCycles": 0,
                "replayAvailable": True,
            },
            "memoryStateChanges": {
                "updated": bool((job.memory_config or {}).get("sessionMemory", False)),
                "changes": [],
            },
            "costTimeSummary": {
                "startedAt": started_at.isoformat(),
                "endedAt": ended_at.isoformat(),
                "runtimeSeconds": round(runtime_seconds, 2),
                "estimatedCost": f"{((token_usage or 0) * 0.00004):.4f}",
                "toolUsageCount": 0,
                "retrievalUsageCount": len(retrieved["retrieval_events"]),
            },
            "auditMetadata": {
                "runId": str(run.id),
                "jobId": str(job.id),
                "jobVersion": f"v{job.version or 1}",
                "workspaceId": "ws_default",
                "actor": "current_user",
                "environment": "development",
                "approvalState": "not_required",
                "policyProfile": job.policy_profile or "default",
            },
        }

        run.run_output_package = run_output_package

        db.add(run)
        db.commit()
    except Exception:
        run = db.query(JobRunModel).filter(JobRunModel.id == run_id).first()
        if run:
            run.state = "failed"
            run.outcome = "error"
            run.ended_at = datetime.now(timezone.utc)
            run.run_output_package = {
                "status": "failed",
                "primaryResult": {
                    "resultType": "text_output",
                    "title": "Run failed",
                    "content": "Unexpected error while generating mock output.",
                },
            }
            db.add(run)
            db.commit()
    finally:
        db.close()

