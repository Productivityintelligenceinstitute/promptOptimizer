"""
Full CLM mock E2E through the live backend, same auth path as the frontend:
Firebase email/password -> ID token -> Authorization Bearer.

Reads CLM_E2E_EMAIL / CLM_E2E_PASSWORD from the environment.
Does not print secrets.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

from context_jobs.clm.mock_server import (
    COUPA_CLIENT_ID,
    COUPA_CLIENT_SECRET,
    COUPA_CONTRACT_ID,
    IRONCLAD_RECORD_ID,
    IRONCLAD_TOKEN,
    IRONCLAD_WORKFLOW_ID,
    MOCK_ORIGIN,
)

API = os.environ.get("CLM_E2E_API", "http://127.0.0.1:8000")
JOB_NAME = "CLM mock live e2e"


def _firebase_api_key() -> str:
    env_path = Path(__file__).resolve().parents[2].parent / "jetpromptoptimizerfrontend" / ".env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("NEXT_PUBLIC_FIREBASE_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("NEXT_PUBLIC_FIREBASE_API_KEY not found in frontend .env")


def _login(email: str, password: str) -> str:
    key = _firebase_api_key()
    resp = httpx.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={key}",
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=20,
    )
    if resp.status_code != 200:
        raise SystemExit(f"Firebase login failed HTTP {resp.status_code}: {resp.text[:240]}")
    token = resp.json().get("idToken")
    if not token:
        raise SystemExit("Firebase login returned no idToken")
    return token


def main() -> int:
    email = os.environ.get("CLM_E2E_EMAIL", "").strip()
    password = os.environ.get("CLM_E2E_PASSWORD", "")
    if not email or not password:
        raise SystemExit("Set CLM_E2E_EMAIL and CLM_E2E_PASSWORD")

    try:
        health = httpx.get(f"{MOCK_ORIGIN}/health", timeout=2)
    except Exception as exc:
        raise SystemExit(f"Mock not running at {MOCK_ORIGIN}: {exc}") from exc
    if health.status_code != 200:
        raise SystemExit(f"Mock /health HTTP {health.status_code}")

    token = _login(email, password)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    results: list[tuple[str, bool, str]] = []

    def rec(name: str, ok: bool, detail: str) -> None:
        results.append((name, ok, detail[:400]))

    with httpx.Client(base_url=API, headers=headers, timeout=120.0) as client:
        me = client.get("/me")
        rec("GET /me (Firebase token accepted)", me.status_code == 200, me.text)

        entitlements = client.get("/context-jobs/entitlements")
        rec(
            "GET /context-jobs/entitlements",
            entitlements.status_code == 200,
            entitlements.text,
        )

        providers = client.get("/context-jobs/clm-connections/providers")
        rec(
            "GET /clm-connections/providers",
            providers.status_code == 200 and "coupa" in providers.text,
            providers.text,
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
        rec("POST /clm-connections Coupa bad secret -> 400", bad.status_code == 400, bad.text)

        coupa = client.post(
            "/context-jobs/clm-connections",
            json={
                "name": "Coupa mock live e2e",
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
        rec("POST /clm-connections Coupa (backend -> mock OAuth)", coupa_ok, coupa.text)

        if coupa_id:
            tested = client.post(f"/context-jobs/clm-connections/{coupa_id}/test")
            body = tested.json() if tested.headers.get("content-type", "").startswith("application/json") else {}
            rec(
                "POST /clm-connections/{id}/test Coupa",
                tested.status_code == 200 and body.get("ok") is True,
                tested.text,
            )

        iron = client.post(
            "/context-jobs/clm-connections",
            json={
                "name": "Ironclad mock live e2e",
                "provider": "ironclad",
                "config": {
                    "api_token": IRONCLAD_TOKEN,
                    "base_url": MOCK_ORIGIN,
                },
            },
        )
        iron_ok = iron.status_code == 201
        iron_id = iron.json().get("id") if iron_ok else None
        rec("POST /clm-connections Ironclad (backend -> mock Bearer)", iron_ok, iron.text)

        if iron_id:
            tested = client.post(f"/context-jobs/clm-connections/{iron_id}/test")
            body = tested.json() if tested.headers.get("content-type", "").startswith("application/json") else {}
            rec(
                "POST /clm-connections/{id}/test Ironclad",
                tested.status_code == 200 and body.get("ok") is True,
                tested.text,
            )

        listed = client.get("/context-jobs/clm-connections")
        names = [row.get("name") for row in (listed.json() if listed.status_code == 200 else [])]
        rec(
            "GET /clm-connections lists saved rows",
            listed.status_code == 200 and "Coupa mock live e2e" in names,
            listed.text,
        )

        jobs = client.get("/context-jobs/jobs")
        job_id = None
        if jobs.status_code == 200:
            for row in jobs.json():
                if row.get("name") == JOB_NAME:
                    job_id = row.get("id")
                    break
        if not job_id:
            created = client.post(
                "/context-jobs/jobs",
                json={
                    "name": JOB_NAME,
                    "status": "published",
                    "retrievalMode": "jet_kb",
                    "workflowType": "standard",
                    "executionProvider": "openai",
                    "executionModel": "gpt-4o-mini",
                },
            )
            rec("POST /jobs create throwaway job", created.status_code == 201, created.text)
            job_id = created.json().get("id") if created.status_code == 201 else None
        else:
            rec("Reuse existing CLM mock live e2e job", True, str(job_id))

        if job_id and coupa_id:
            ingest = client.post(
                f"/context-jobs/jobs/{job_id}/ingest/clm",
                json={
                    "connectionId": coupa_id,
                    "url": f"{MOCK_ORIGIN}/contracts/show/{COUPA_CONTRACT_ID}",
                },
            )
            rec(
                "POST /jobs/{id}/ingest/clm Coupa",
                ingest.status_code == 201,
                f"HTTP {ingest.status_code} {ingest.text}",
            )

        if job_id and iron_id:
            ingest = client.post(
                f"/context-jobs/jobs/{job_id}/ingest/clm",
                json={
                    "connectionId": iron_id,
                    "url": f"{MOCK_ORIGIN}/workflow/{IRONCLAD_WORKFLOW_ID}",
                },
            )
            rec(
                "POST /jobs/{id}/ingest/clm Ironclad workflow",
                ingest.status_code == 201,
                f"HTTP {ingest.status_code} {ingest.text}",
            )
            ingest_rec = client.post(
                f"/context-jobs/jobs/{job_id}/ingest/clm",
                json={
                    "connectionId": iron_id,
                    "url": f"{MOCK_ORIGIN}/record/{IRONCLAD_RECORD_ID}",
                },
            )
            rec(
                "POST /jobs/{id}/ingest/clm Ironclad record",
                ingest_rec.status_code == 201,
                f"HTTP {ingest_rec.status_code} {ingest_rec.text}",
            )

        for conn_id in (coupa_id, iron_id):
            if conn_id:
                client.delete(f"/context-jobs/clm-connections/{conn_id}")

    report_path = Path(__file__).with_name("_last_live_user_e2e.txt")
    failed = 0
    lines = ["=== Live user CLM mock E2E ===", ""]
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        lines.append(f"[{mark}] {name}")
        lines.append(f"       {detail}")
        lines.append("")
    lines.append(f"Summary: {len(results) - failed}/{len(results)} passed")
    report = "\n".join(lines)
    report_path.write_text(report, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(report)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
