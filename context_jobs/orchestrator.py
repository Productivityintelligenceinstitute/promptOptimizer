"""Context Jobs run queue and worker pool."""

from __future__ import annotations

import threading
from queue import Empty, Full, Queue
from uuid import UUID

from context_jobs.run_engine import execute_run_sync

RUN_QUEUE_MAXSIZE = 50
RUN_WORKER_COUNT = 2
_run_queue: Queue[UUID] = Queue(maxsize=RUN_QUEUE_MAXSIZE)
_workers: list[threading.Thread] = []
_workers_lock = threading.Lock()
_active_runs = 0
_active_runs_lock = threading.Lock()
_stop_event = threading.Event()


def start_run_workers(worker_count: int = RUN_WORKER_COUNT) -> None:
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


def stop_run_workers(timeout_seconds: float = 2.0) -> None:
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


def enqueue_run(run_id: UUID) -> bool:
    try:
        _run_queue.put_nowait(run_id)
        return True
    except Full:
        return False


def get_run_queue_status() -> dict:
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
            execute_run_sync(run_id)
        finally:
            with _active_runs_lock:
                _active_runs = max(0, _active_runs - 1)
            _run_queue.task_done()
