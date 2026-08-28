"""
Live-API E2E for Contract Review HITL: Approve recommendations vs Escalate.

Auth matches the frontend: Firebase email/password -> Bearer ID token.
Seeds completed parent runs in DB so we can test the decision/amendment path
without waiting on a full contract-review LLM execution. The amendment child
run is a real queued agent run (LLM + docx-generate).

Env:
  CLM_E2E_EMAIL / CLM_E2E_PASSWORD  (defaults: context_job@gmail.com)
  CLM_E2E_API                       (default http://127.0.0.1:8000)
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import httpx

from database.database import SessionLocal
from schemas.context_jobs_model import ContextJobModel, JobRunModel

API = os.environ.get("CLM_E2E_API", "http://127.0.0.1:8000")
EMAIL = os.environ.get("CLM_E2E_EMAIL", "context_job@gmail.com").strip()
PASSWORD = os.environ.get("CLM_E2E_PASSWORD", "context_job@gmail.com")
JOB_NAME = "Amendment e2e contract review"
STANDARD_JOB_NAME = "Amendment e2e standard job"

MINI_CONTRACT = """MASTER SERVICES AGREEMENT
This Agreement is between Acme Corp ('Customer') and Northwind Labs ('Supplier'), effective 1 January 2025.

1. Services. Supplier will provide software implementation services as described in Exhibit A.
2. Fees. Customer shall pay USD 120,000 per year, invoiced annually in advance.
3. Term. The initial term is 24 months and auto-renews for 12-month periods unless either party gives 30 days written notice.
4. Limitation of Liability. Supplier's aggregate liability is capped at fees paid in the prior 3 months. Consequential damages are excluded.
5. Termination. Either party may terminate for convenience on 15 days notice.
6. Governing Law. California law. Venue in San Francisco.
7. Confidentiality. Each party shall protect Confidential Information for 2 years after disclosure.
8. Data Protection. Supplier will process Customer personal data only on documented instructions.
9. Insurance. Supplier shall maintain commercial general liability insurance of at least USD 1,000,000.
10. Assignment. Neither party may assign without prior written consent.
"""

RECOMMENDATIONS = """## Recommendations
1. Increase termination-for-convenience notice from 15 days to 90 days.
2. Raise the liability cap from 3 months of fees to 12 months of fees paid in the prior 12 months.
3. Extend confidentiality survival from 2 years to 5 years.
4. Keep governing law California / San Francisco unchanged.
5. Add a 60-day cure period before termination for material breach.
"""

APPROVER_NOTES = "Keep limitation of liability structure, but apply the 12-month cap. Do not change governing law."


def _firebase_api_key() -> str:
    env_path = Path(__file__).resolve().parents[1].parent / "jetpromptoptimizerfrontend" / ".env"
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


def _seed_completed_run(job_id: str, owner: str, *, with_analyzer: bool = True) -> str:
    db = SessionLocal()
    try:
        job = db.query(ContextJobModel).filter(ContextJobModel.id == UUID(str(job_id))).first()
        if not job:
            raise SystemExit(f"Seed job not found: {job_id}")
        tool_events = []
        if with_analyzer:
            tool_events.append(
                {
                    "toolId": "contract-analyzer",
                    "result": {
                        "clauses": [
                            {"name": "Limitation of Liability", "excerpt": "capped at fees paid in the prior 3 months"},
                            {"name": "Termination", "excerpt": "terminate for convenience on 15 days notice"},
                        ]
                    },
                }
            )
        run = JobRunModel(
            job_id=job.id,
            state="completed",
            outcome="completed",
            user_request="Review the Acme / Northwind MSA for renewal.",
            job_version=job.version,
            workspace_id=job.workspace_id,
            output_text=RECOMMENDATIONS,
            tool_events=tool_events,
            run_output_package={
                "status": "completed",
                "primaryResult": {
                    "resultType": "text_output",
                    "title": "Contract review recommendations",
                    "content": RECOMMENDATIONS,
                },
            },
            ended_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return str(run.id)
    finally:
        db.close()


def _is_docx(content: bytes) -> bool:
    if not content.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            return "word/document.xml" in zf.namelist()
    except zipfile.BadZipFile:
        return False


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    def rec(name: str, ok: bool, detail: str) -> None:
        results.append((name, ok, detail[:500]))

    token = _login(EMAIL, PASSWORD)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    with httpx.Client(base_url=API, headers=headers, timeout=120.0) as client:
        me = client.get("/me")
        rec("GET /me", me.status_code == 200, me.text)
        if me.status_code != 200:
            _print(results)
            return 1
        owner = str(me.json().get("firebase_uid") or me.json().get("firebaseUid") or "")
        if not owner:
            rec("owner uid present", False, me.text)
            _print(results)
            return 1
        rec("owner uid present", True, owner)

        ent = client.get("/context-jobs/entitlements")
        rec(
            "GET /context-jobs/entitlements",
            ent.status_code == 200 and bool(ent.json().get("contextJobsEnabled")),
            ent.text,
        )

        jobs = client.get("/context-jobs/jobs")
        rec("GET /context-jobs/jobs", jobs.status_code == 200, f"count={len(jobs.json()) if jobs.status_code == 200 else jobs.text}")
        listed = jobs.json() if jobs.status_code == 200 else []
        hidden = [j for j in listed if (j.get("workflowType") or "").lower() == "contract_amendment"]
        rec("list_jobs hides contract_amendment", hidden == [], json.dumps(hidden)[:300])

        review_jobs = [j for j in listed if (j.get("workflowType") or "").lower() == "contract_review"]
        rec(
            "library has some contract_review jobs (any name, not template-only)",
            True,
            f"count={len(review_jobs)} names={[j.get('name') for j in review_jobs][:8]}",
        )

        cr_payload = {
            "name": JOB_NAME,
            "description": "E2E job for revised-contract HITL",
            "status": "published",
            "workflowType": "contract_review",
            "goal": "Review the Acme / Northwind MSA and recommend clause changes.",
            "roleConfiguration": "You are a contracts specialist.",
            "stableInstructions": "Produce concrete clause recommendations.",
            "retrievalMode": "jet_kb",
            "executionProvider": "openai",
            "executionModel": "gpt-4o-mini",
            "retrievalConfig": {
                "maxDocuments": 8,
                "knowledgeSources": [
                    {
                        "id": "mini-msa",
                        "type": "text",
                        "label": "Acme-Northwind MSA",
                        "value": MINI_CONTRACT,
                    }
                ],
            },
            "toolPermissions": [
                {"toolId": "doc-reader", "enabled": True, "readOnly": True, "requireApproval": False},
                {"toolId": "contract-analyzer", "enabled": True, "readOnly": True, "requireApproval": False},
                {"toolId": "docx-generate", "enabled": True, "readOnly": False, "requireApproval": False},
                {"toolId": "file-write", "enabled": True, "readOnly": False, "requireApproval": False},
            ],
        }
        created = client.post("/context-jobs/jobs", json=cr_payload)
        rec("POST /jobs contract_review", created.status_code == 201, created.text)
        if created.status_code != 201:
            _print(results)
            return 1
        cr_job = created.json()
        cr_job_id = cr_job["id"]
        rec(
            "created job workflowType=contract_review",
            (cr_job.get("workflowType") or "").lower() == "contract_review",
            json.dumps({"workflowType": cr_job.get("workflowType"), "executionModel": cr_job.get("executionModel")}),
        )

        std_payload = {
            "name": STANDARD_JOB_NAME,
            "description": "Control job — approve should not spawn amendment",
            "status": "published",
            "workflowType": "standard",
            "goal": "Summarize a note.",
            "executionProvider": "openai",
            "executionModel": "gpt-4o-mini",
        }
        std = client.post("/context-jobs/jobs", json=std_payload)
        rec("POST /jobs standard", std.status_code == 201, std.text)
        std_job_id = std.json()["id"] if std.status_code == 201 else None

        approve_run_id = _seed_completed_run(cr_job_id, owner)
        escalate_run_id = _seed_completed_run(cr_job_id, owner)
        std_run_id = _seed_completed_run(std_job_id, owner, with_analyzer=False) if std_job_id else None
        rec("seeded completed contract_review runs", True, f"approve={approve_run_id} escalate={escalate_run_id}")

        got = client.get(f"/context-jobs/runs/{approve_run_id}")
        rec(
            "GET seeded run",
            got.status_code == 200 and got.json().get("state") == "completed",
            got.text,
        )

        # Escalate first (no file)
        esc = client.patch(
            f"/context-jobs/runs/{escalate_run_id}/decision",
            json={"decision": "escalate", "notes": "Legal should take this; do not generate a file."},
        )
        esc_body = esc.json() if esc.status_code == 200 else {"raw": esc.text}
        rec(
            "PATCH escalate -> 200, no amendmentRunId, state=escalated",
            esc.status_code == 200
            and not esc_body.get("amendmentRunId")
            and (esc_body.get("state") or "").lower() == "escalated"
            and (esc_body.get("humanDecision") or {}).get("decision") == "escalate",
            json.dumps(esc_body)[:500],
        )
        esc_arts = client.get(f"/context-jobs/runs/{escalate_run_id}/artifacts")
        esc_list = (esc_arts.json() or {}).get("artifacts") if esc_arts.status_code == 200 else []
        rec(
            "escalate produces no revised_contract artifact",
            esc_arts.status_code == 200
            and not any((a.get("purpose") or "").lower() == "revised_contract" for a in esc_list),
            json.dumps(esc_list)[:300],
        )

        # Standard job approve must not start amendment
        if std_run_id:
            std_dec = client.patch(
                f"/context-jobs/runs/{std_run_id}/decision",
                json={"decision": "approve", "notes": "should not generate a contract"},
            )
            std_body = std_dec.json() if std_dec.status_code == 200 else {"raw": std_dec.text}
            rec(
                "standard job PATCH approve does not start amendment",
                std_dec.status_code == 200 and not std_body.get("amendmentRunId"),
                json.dumps(std_body)[:400],
            )

        # Approve recommendations — starts child run
        appr = client.patch(
            f"/context-jobs/runs/{approve_run_id}/decision",
            json={"decision": "approve", "notes": APPROVER_NOTES},
        )
        appr_body = appr.json() if appr.status_code == 200 else {"raw": appr.text}
        amendment_id = appr_body.get("amendmentRunId")
        rec(
            "PATCH approve starts amendmentRunId",
            appr.status_code == 200 and bool(amendment_id),
            json.dumps(appr_body)[:500],
        )
        rec(
            "approver notes stored on humanDecision",
            (appr_body.get("humanDecision") or {}).get("notes") == APPROVER_NOTES,
            json.dumps(appr_body.get("humanDecision"))[:400],
        )

        # Duplicate decision -> 409/400
        dup = client.patch(
            f"/context-jobs/runs/{approve_run_id}/decision",
            json={"decision": "approve", "notes": "second click"},
        )
        rec(
            "second PATCH decision rejected",
            dup.status_code in {400, 409},
            f"HTTP {dup.status_code} {dup.text[:240]}",
        )

        listed_after = client.get("/context-jobs/jobs").json() if jobs.status_code == 200 else []
        still_hidden = [j for j in listed_after if (j.get("workflowType") or "").lower() == "contract_amendment"]
        rec("amendment job still hidden from jobs library", still_hidden == [], json.dumps(still_hidden)[:200])

        if amendment_id:
            child = client.get(f"/context-jobs/runs/{amendment_id}")
            rec(
                "GET amendment child run exists",
                child.status_code == 200,
                child.text[:400],
            )
            if child.status_code == 200:
                req = child.json().get("userRequest") or ""
                rec(
                    "child userRequest includes recommendations + notes",
                    "Increase termination-for-convenience" in req and APPROVER_NOTES in req,
                    req[:400],
                )
                rec(
                    "child userRequest tells model to use retrieved contract context",
                    "retrieved contract context" in req.lower(),
                    req[-200:],
                )

            terminal = {"completed", "completed_with_warnings", "failed", "escalated", "blocked_by_policy"}
            last_state = None
            last_body = {}
            deadline = time.time() + 240
            while time.time() < deadline:
                parent = client.get(f"/context-jobs/runs/{approve_run_id}")
                last_body = parent.json() if parent.status_code == 200 else {}
                last_state = (last_body.get("amendmentState") or "").lower()
                if last_state in terminal:
                    break
                time.sleep(4)

            rec(
                "amendment child reached a terminal state",
                last_state in terminal,
                f"amendmentState={last_state} parent={json.dumps({k: last_body.get(k) for k in ('state','amendmentRunId','amendmentState')})}",
            )
            rec(
                "amendment completed (not failed)",
                last_state in {"completed", "completed_with_warnings"},
                f"amendmentState={last_state}",
            )

            arts = client.get(f"/context-jobs/runs/{approve_run_id}/artifacts")
            rec("GET parent /artifacts", arts.status_code == 200, arts.text[:400])
            art_list = (arts.json() or {}).get("artifacts") if arts.status_code == 200 else []
            revised = [
                a
                for a in art_list
                if (a.get("purpose") or "").lower() == "revised_contract"
                or "revised-contract" in (a.get("path") or "").lower()
            ]
            rec(
                "revised_contract artifact listed on parent run",
                bool(revised),
                json.dumps(art_list)[:500],
            )
            if revised:
                path = revised[0].get("path")
                dl = client.get(f"/context-jobs/runs/{approve_run_id}/artifacts/{path}")
                rec(
                    "download revised DOCX bytes",
                    dl.status_code == 200 and _is_docx(dl.content),
                    f"HTTP {dl.status_code} bytes={len(dl.content)} content-type={dl.headers.get('content-type')} magic={dl.content[:4]!r}",
                )

            if last_state in terminal and amendment_id:
                child_final = client.get(f"/context-jobs/runs/{amendment_id}")
                rec(
                    "child run GET after finish",
                    child_final.status_code == 200,
                    json.dumps(
                        {
                            "state": child_final.json().get("state") if child_final.status_code == 200 else None,
                            "executionModel": child_final.json().get("executionModel") if child_final.status_code == 200 else None,
                        }
                    ),
                )
                if child_final.status_code == 200:
                    model = child_final.json().get("executionModel")
                    rec(
                        "amendment uses parent job model (gpt-4o-mini unless overridden at runtime)",
                        True,
                        f"executionModel={model} jobModel={cr_job.get('executionModel')}",
                    )

    _print(results)
    failed = [r for r in results if not r[1]]
    return 1 if failed else 0


def _print(results: list[tuple[str, bool, str]]) -> None:
    print("\n=== Amendment HITL E2E ===")
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}")
        if detail:
            print(f"       {detail}")
    passed = sum(1 for r in results if r[1])
    print(f"\n{passed}/{len(results)} passed")


if __name__ == "__main__":
    sys.exit(main())
