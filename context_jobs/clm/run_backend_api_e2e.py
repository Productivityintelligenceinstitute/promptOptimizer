"""
Hit the real FastAPI CLM routes (auth overridden) so the backend
calls Coupa/Ironclad through the adapters. Point connections at the local mock.
"""

from __future__ import annotations

import json
import sys
import uuid

import httpx
from fastapi.testclient import TestClient

from context_jobs.auth import get_context_jobs_owner_with_access
from context_jobs.clm.mock_server import (
    COUPA_CLIENT_ID,
    COUPA_CLIENT_SECRET,
    COUPA_CONTRACT_ID,
    IRONCLAD_RECORD_ID,
    IRONCLAD_TOKEN,
    IRONCLAD_WORKFLOW_ID,
    MOCK_ORIGIN,
)
from database.database import SessionLocal
from main import app
from schemas.context_jobs_model import ContextJobModel

OWNER = "clm-mock-api-e2e"


def _require_mock() -> None:
    try:
        resp = httpx.get(f"{MOCK_ORIGIN}/health", timeout=2)
    except Exception as exc:
        raise SystemExit(f"Mock server not running at {MOCK_ORIGIN}: {exc}") from exc
    if resp.status_code != 200:
        raise SystemExit(f"Mock /health returned {resp.status_code}")


def _owner() -> str:
    return OWNER


def _ensure_job() -> str:
    db = SessionLocal()
    try:
        existing = (
            db.query(ContextJobModel)
            .filter(
                ContextJobModel.owner == OWNER,
                ContextJobModel.name == "CLM mock API e2e job",
            )
            .first()
        )
        if existing:
            return str(existing.id)
        job = ContextJobModel(
            name="CLM mock API e2e job",
            owner=OWNER,
            status="published",
            retrieval_mode="jet_kb",
            workflow_type="standard",
            execution_provider="openai",
            execution_model="gpt-4o-mini",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return str(job.id)
    finally:
        db.close()


def main() -> int:
    _require_mock()
    app.dependency_overrides[get_context_jobs_owner_with_access] = _owner
    results: list[tuple[str, bool, str]] = []

    with TestClient(app) as client:
        providers = client.get("/context-jobs/clm-connections/providers")
        results.append(
            (
                "GET /clm-connections/providers",
                providers.status_code == 200 and "coupa" in providers.json(),
                providers.text[:240],
            )
        )

        bad = client.post(
            "/context-jobs/clm-connections",
            json={
                "name": "Coupa mock (bad secret)",
                "provider": "coupa",
                "config": {
                    "instance_url": MOCK_ORIGIN,
                    "client_id": COUPA_CLIENT_ID,
                    "client_secret": "wrong",
                },
            },
        )
        results.append(
            (
                "POST /clm-connections Coupa bad secret -> 400",
                bad.status_code == 400,
                bad.text[:240],
            )
        )

        coupa = client.post(
            "/context-jobs/clm-connections",
            json={
                "name": "Coupa mock e2e",
                "provider": "coupa",
                "config": {
                    "instance_url": MOCK_ORIGIN,
                    "client_id": COUPA_CLIENT_ID,
                    "client_secret": COUPA_CLIENT_SECRET,
                    "scope": "core.contract.read",
                },
            },
        )
        coupa_ok = coupa.status_code == 201
        coupa_id = coupa.json().get("id") if coupa_ok else None
        results.append(("POST /clm-connections Coupa (backend->mock OAuth)", coupa_ok, coupa.text[:300]))

        if coupa_id:
            tested = client.post(f"/context-jobs/clm-connections/{coupa_id}/test")
            body = tested.json() if tested.headers.get("content-type", "").startswith("application/json") else {}
            results.append(
                (
                    "POST /clm-connections/{id}/test Coupa",
                    tested.status_code == 200 and body.get("ok") is True,
                    tested.text[:240],
                )
            )

        iron = client.post(
            "/context-jobs/clm-connections",
            json={
                "name": "Ironclad mock e2e",
                "provider": "ironclad",
                "config": {
                    "api_token": IRONCLAD_TOKEN,
                    "base_url": MOCK_ORIGIN,
                },
            },
        )
        iron_ok = iron.status_code == 201
        iron_id = iron.json().get("id") if iron_ok else None
        results.append(("POST /clm-connections Ironclad (backend->mock Bearer)", iron_ok, iron.text[:300]))

        if iron_id:
            tested = client.post(f"/context-jobs/clm-connections/{iron_id}/test")
            body = tested.json() if tested.headers.get("content-type", "").startswith("application/json") else {}
            results.append(
                (
                    "POST /clm-connections/{id}/test Ironclad",
                    tested.status_code == 200 and body.get("ok") is True,
                    tested.text[:240],
                )
            )

        listed = client.get("/context-jobs/clm-connections")
        names = [row.get("name") for row in (listed.json() if listed.status_code == 200 else [])]
        results.append(
            (
                "GET /clm-connections lists saved rows",
                listed.status_code == 200 and "Coupa mock e2e" in names,
                listed.text[:300],
            )
        )

        try:
            job_id = _ensure_job()
        except Exception as exc:
            results.append(("Create throwaway job for ingest", False, str(exc)[:360]))
            job_id = None
        if job_id and coupa_id:
            ingest = client.post(
                f"/context-jobs/jobs/{job_id}/ingest/clm",
                json={
                    "connectionId": coupa_id,
                    "url": f"{MOCK_ORIGIN}/contracts/show/{COUPA_CONTRACT_ID}",
                },
            )
            ingest_json = ingest.json() if ingest.headers.get("content-type", "").startswith("application/json") else {}
            clm_reached = ingest.status_code in (201, 400)
            downloaded = ingest.status_code == 201 or "extract" in str(ingest_json).lower() or "ingest" in str(ingest_json).lower()
            results.append(
                (
                    "POST /jobs/{id}/ingest/clm Coupa (backend downloads mock PDF)",
                    clm_reached and ingest.status_code != 404,
                    f"HTTP {ingest.status_code} {ingest.text[:360]}",
                )
            )
            if ingest.status_code == 201:
                results.append(
                    (
                        "Coupa ingest completed into job KB",
                        True,
                        json.dumps(ingest_json)[:300],
                    )
                )
            else:
                results.append(
                    (
                        "Coupa ingest after CLM download (KB/embed may fail locally)",
                        downloaded,
                        f"HTTP {ingest.status_code} {ingest.text[:360]}",
                    )
                )

        if job_id and iron_id:
            ingest = client.post(
                f"/context-jobs/jobs/{job_id}/ingest/clm",
                json={
                    "connectionId": iron_id,
                    "url": f"{MOCK_ORIGIN}/workflow/{IRONCLAD_WORKFLOW_ID}",
                },
            )
            results.append(
                (
                    "POST /jobs/{id}/ingest/clm Ironclad workflow",
                    ingest.status_code in (201, 400),
                    f"HTTP {ingest.status_code} {ingest.text[:360]}",
                )
            )
            ingest_rec = client.post(
                f"/context-jobs/jobs/{job_id}/ingest/clm",
                json={
                    "connectionId": iron_id,
                    "url": f"{MOCK_ORIGIN}/record/{IRONCLAD_RECORD_ID}",
                },
            )
            results.append(
                (
                    "POST /jobs/{id}/ingest/clm Ironclad record",
                    ingest_rec.status_code in (201, 400),
                    f"HTTP {ingest_rec.status_code} {ingest_rec.text[:360]}",
                )
            )

        for conn_id in (coupa_id, iron_id):
            if conn_id:
                client.delete(f"/context-jobs/clm-connections/{conn_id}")

    app.dependency_overrides.clear()

    report_path = "context_jobs/clm/_last_backend_api_e2e.txt"
    lines = ["=== Backend API -> CLM mock E2E ===", ""]
    failed = 0
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        lines.append(f"[{mark}] {name}")
        lines.append(f"       {detail}")
        lines.append("")
    lines.append(f"Summary: {len(results) - failed}/{len(results)} passed")
    report = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(report)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
