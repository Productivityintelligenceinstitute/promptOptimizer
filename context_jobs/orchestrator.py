import random
import threading
import time
from queue import Empty, Full, Queue
from datetime import datetime, timezone
from uuid import UUID

from database.database import SessionLocal
from schemas.context_jobs_model import ContextJobModel, JobRunModel

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

        steps = [
            ("planning", "Analyzing job goal and request context", 0.4),
            ("retrieving", "Collecting configured trusted sources", 0.7),
            ("executing", "Building structured mock output", 1.0),
            ("validating", "Applying validation rules and escalation policy", 0.5),
        ]

        for state, details, delay in steps:
            run = db.query(JobRunModel).filter(JobRunModel.id == run_id).first()
            if not run:
                return
            logs = list(run.step_logs or [])
            logs.append(
                {
                    "step": state,
                    "status": "running",
                    "startedAt": datetime.now(timezone.utc).isoformat(),
                    "details": details,
                }
            )
            run.state = state
            run.step_logs = logs
            db.add(run)
            db.commit()
            time.sleep(delay)

            run = db.query(JobRunModel).filter(JobRunModel.id == run_id).first()
            if not run:
                return
            logs = list(run.step_logs or [])
            if logs:
                logs[-1]["status"] = "completed"
                logs[-1]["endedAt"] = datetime.now(timezone.utc).isoformat()
            run.step_logs = logs
            db.add(run)
            db.commit()

        run = db.query(JobRunModel).filter(JobRunModel.id == run_id).first()
        if not run:
            return

        trusted_sources = list(job.trusted_sources or [])
        source_count = max(1, len(trusted_sources))
        source_names = [s.get("name", "Workspace Source") for s in trusted_sources] or ["Workspace Source"]

        retrieval_events = []
        for name in source_names:
            retrieval_events.append(
                {
                    "query": run.user_request or job.goal or "general request",
                    "source": name,
                    "resultCount": random.randint(2, 8),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        validation_rules = [r for r in list(job.validation_rules or []) if r.get("enabled", False)]
        validation_events = []
        any_warning = False
        any_error = False
        any_blocking = False
        for rule in validation_rules:
            severity = str(rule.get("severity", "warning"))
            passed = random.random() > 0.15
            if not passed and severity == "warning":
                any_warning = True
            if not passed and severity == "error":
                any_error = True
            if not passed and severity == "blocking":
                any_blocking = True
            validation_events.append(
                {
                    "rule": rule.get("name", "Validation rule"),
                    "passed": passed,
                    "message": "Check passed" if passed else "Needs attention",
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

        ended_at = datetime.now(timezone.utc)
        runtime_seconds = max(0.1, (ended_at - started_at).total_seconds())

        output_text = (
            f"# {job.name}\n\n"
            f"Request: {run.user_request or job.goal or 'N/A'}\n\n"
            f"Mock context execution complete using {source_count} source(s): "
            f"{', '.join(source_names)}.\n\n"
            "This is a scaffold output from the Python context-gatherer runner."
        )

        run.state = terminal_state
        run.outcome = outcome
        run.ended_at = ended_at
        run.retrieval_events = retrieval_events
        run.validation_events = validation_events
        run.output_text = output_text
        run.token_usage = random.randint(900, 3000)
        run.latency_ms = int(runtime_seconds * 1000)
        run.run_output_package = {
            "status": status,
            "primaryResult": {
                "resultType": "text_output",
                "title": f"{job.name} - Mock Result",
                "content": output_text,
            },
            "validationSummary": {
                "overallDecision": "passed_with_warnings"
                if any_warning
                else ("failed" if any_error or any_blocking else "passed"),
                "confidenceLevel": "medium" if any_warning else ("low" if any_error or any_blocking else "high"),
                "checks": [
                    {
                        "name": ev["rule"],
                        "result": "passed" if ev["passed"] else ("warning" if ev["severity"] == "warning" else "failed"),
                        "message": ev["message"],
                    }
                    for ev in validation_events
                ],
            },
            "sourceSummary": {
                "groundedMode": bool(job.retrieval_config or trusted_sources),
                "sourcesUsed": [
                    {
                        "sourceId": str(i + 1),
                        "title": ev["source"],
                        "sourceType": "document",
                        "freshness": "current",
                        "evidenceStrength": "sufficient",
                        "trustLevel": "preferred",
                    }
                    for i, ev in enumerate(retrieval_events)
                ],
                "overallEvidenceStrength": "sufficient",
            },
            "warnings": [],
            "exceptions": [],
            "nextAction": next_action,
            "traceSummary": {
                "stages": ["planning", "retrieving", "executing", "validating"],
                "toolEvents": 0,
                "retrievalEvents": len(retrieval_events),
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
                "estimatedCost": f"{(run.token_usage or 0) * 0.00004:.4f}",
                "toolUsageCount": 0,
                "retrievalUsageCount": len(retrieval_events),
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

