"""
Local Coupa + Ironclad stand-in for CLM integration tests.

Mirrors the official paths/headers/JSON keys our adapters call.
Does not talk to real Coupa or Ironclad.

Run:
    python -m context_jobs.clm.mock_server
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

MOCK_HOST = "127.0.0.1"
MOCK_PORT = 8765
MOCK_ORIGIN = f"http://{MOCK_HOST}:{MOCK_PORT}"

COUPA_CLIENT_ID = "test"
COUPA_CLIENT_SECRET = "test"
COUPA_TOKEN = "mock-coupa-token"
COUPA_CONTRACT_ID = "12345"

IRONCLAD_TOKEN = "test-token"
IRONCLAD_WORKFLOW_ID = "wf_demo"
IRONCLAD_RECORD_ID = "rec_demo"
IRONCLAD_DOC_KEY = "mockKey"

CONTRACT_TEXT = (
    "ACME MASTER SERVICES AGREEMENT (mock)\n"
    "This mock legal agreement is for Jet Prompt Optimizer CLM import testing.\n"
    "Vendor: Acme Corp. Contract number: MSA-2026-001. Term: 2026-01-01 to 2027-12-31.\n"
    "Limitation of liability, confidentiality, and termination clauses are included for retrieval."
)


def _minimal_pdf(text: str) -> bytes:
    """Tiny text-extractable PDF (Type1 Helvetica)."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 11 Tf 50 740 Td ({escaped}) Tj ET\n".encode("latin-1", "replace")
    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        (
            b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj\n"
        ),
        b"4 0 obj<< /Length %d >>stream\n" % len(stream) + stream + b"endstream\nendobj\n",
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
    ]
    header = b"%PDF-1.1\n"
    body = b"".join(objects)
    offsets = []
    cursor = len(header)
    for obj in objects:
        offsets.append(cursor)
        cursor += len(obj)
    xref = [b"xref\n0 6\n0000000000 65535 f \n"]
    for off in offsets:
        xref.append(f"{off:010d} 00000 n \n".encode("ascii"))
    trailer = (
        b"trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(cursor).encode("ascii")
        + b"\n%%EOF\n"
    )
    return header + body + b"".join(xref) + trailer


SAMPLE_PDF = _minimal_pdf(CONTRACT_TEXT)
SAMPLE_FILENAME = "acme-msa-2026.pdf"

app = FastAPI(title="Jet CLM mock (Coupa + Ironclad)", docs_url="/docs")


def _coupa_contract() -> dict:
    return {
        "id": int(COUPA_CONTRACT_ID),
        "name": "Acme MSA 2026",
        "number": "MSA-2026-001",
        "status": "published",
        "start-date": "2026-01-01T00:00:00-08:00",
        "end-date": "2027-12-31T00:00:00-08:00",
        "supplier": {"id": 1023, "name": "Acme Corp"},
    }


def _require_coupa_bearer(authorization: Optional[str]) -> None:
    if not authorization or authorization.strip() != f"Bearer {COUPA_TOKEN}":
        raise HTTPException(status_code=401, detail="Coupa auth failed")


def _require_ironclad_bearer(authorization: Optional[str]) -> None:
    if not authorization or authorization.strip() != f"Bearer {IRONCLAD_TOKEN}":
        raise HTTPException(status_code=401, detail="Ironclad auth failed")


def _pdf_response(filename: str = SAMPLE_FILENAME) -> Response:
    return Response(
        content=SAMPLE_PDF,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- Coupa


@app.post("/oauth2/token")
async def coupa_token(request: Request):
    form = await request.form()
    client_id = str(form.get("client_id") or "")
    client_secret = str(form.get("client_secret") or "")
    grant_type = str(form.get("grant_type") or "")
    if grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="grant_type must be client_credentials")
    if client_id != COUPA_CLIENT_ID or client_secret != COUPA_CLIENT_SECRET:
        raise HTTPException(status_code=401, detail="invalid_client")
    return {
        "access_token": COUPA_TOKEN,
        "token_type": "Bearer",
        "expires_in": 86399,
        "scope": str(form.get("scope") or "core.contract.read"),
    }


@app.get("/api/contracts")
def coupa_list_contracts(
    authorization: Optional[str] = Header(default=None),
    limit: int = 1,
):
    _require_coupa_bearer(authorization)
    return [_coupa_contract()][: max(1, limit)]


@app.get("/api/contracts/{contract_id}")
def coupa_show_contract(
    contract_id: str,
    authorization: Optional[str] = Header(default=None),
):
    _require_coupa_bearer(authorization)
    if contract_id != COUPA_CONTRACT_ID:
        raise HTTPException(status_code=404, detail="Contract not found")
    return _coupa_contract()


@app.get("/api/contracts/{contract_id}/retrieve_legal_agreement")
def coupa_legal_agreement(
    contract_id: str,
    authorization: Optional[str] = Header(default=None),
):
    _require_coupa_bearer(authorization)
    if contract_id != COUPA_CONTRACT_ID:
        raise HTTPException(status_code=404, detail="No legal agreement")
    return _pdf_response()


@app.get("/api/contracts/{contract_id}/attachments")
def coupa_attachments(
    contract_id: str,
    authorization: Optional[str] = Header(default=None),
):
    _require_coupa_bearer(authorization)
    if contract_id != COUPA_CONTRACT_ID:
        raise HTTPException(status_code=404, detail="Not found")
    return [{"id": 1, "file-url": f"/api/contracts/{contract_id}/attachments/1"}]


@app.get("/api/contracts/{contract_id}/attachments/{attachment_id}")
def coupa_attachment_file(
    contract_id: str,
    attachment_id: str,
    authorization: Optional[str] = Header(default=None),
):
    _require_coupa_bearer(authorization)
    if contract_id != COUPA_CONTRACT_ID:
        raise HTTPException(status_code=404, detail="Not found")
    return _pdf_response(f"coupa-attachment-{attachment_id}.pdf")


@app.get("/contracts/show/{contract_id}", response_class=HTMLResponse)
def coupa_browser_page(contract_id: str):
    return f"<html><body>Coupa contract {contract_id}</body></html>"


# --------------------------------------------------------------------------- Ironclad


@app.get("/public/api/v1/records")
def ironclad_list_records(
    authorization: Optional[str] = Header(default=None),
    pageSize: int = 1,
):
    _require_ironclad_bearer(authorization)
    return {
        "page": 0,
        "pageSize": pageSize,
        "count": 1,
        "list": [
            {
                "id": IRONCLAD_RECORD_ID,
                "ironcladId": "IC-100",
                "name": "Acme MSA 2026",
            }
        ],
    }


@app.get("/public/api/v1/workflows")
def ironclad_list_workflows(
    authorization: Optional[str] = Header(default=None),
    pageSize: int = 1,
):
    _require_ironclad_bearer(authorization)
    return {
        "page": 0,
        "pageSize": pageSize,
        "count": 1,
        "list": [{"id": IRONCLAD_WORKFLOW_ID, "title": "Acme MSA 2026"}],
    }


@app.get("/public/api/v1/workflows/{workflow_id}")
def ironclad_get_workflow(
    workflow_id: str,
    authorization: Optional[str] = Header(default=None),
):
    _require_ironclad_bearer(authorization)
    if workflow_id != IRONCLAD_WORKFLOW_ID:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "id": IRONCLAD_WORKFLOW_ID,
        "ironcladId": "IC-99",
        "title": "Acme MSA 2026",
        "step": "Complete",
        "attributes": {
            "signed": {
                "filename": SAMPLE_FILENAME,
                "key": IRONCLAD_DOC_KEY,
                "download": (
                    f"/public/api/v1/workflows/{IRONCLAD_WORKFLOW_ID}"
                    f"/document/{IRONCLAD_DOC_KEY}/download"
                ),
            }
        },
    }


@app.get("/public/api/v1/workflows/{workflow_id}/document/{key}/download")
def ironclad_workflow_download(
    workflow_id: str,
    key: str,
    authorization: Optional[str] = Header(default=None),
):
    _require_ironclad_bearer(authorization)
    if workflow_id != IRONCLAD_WORKFLOW_ID or key != IRONCLAD_DOC_KEY:
        raise HTTPException(status_code=404, detail="Document not found")
    return _pdf_response()


@app.get("/public/api/v1/records/{record_id}")
def ironclad_get_record(
    record_id: str,
    authorization: Optional[str] = Header(default=None),
):
    _require_ironclad_bearer(authorization)
    if record_id != IRONCLAD_RECORD_ID:
        raise HTTPException(status_code=404, detail="Record not found")
    return {
        "id": IRONCLAD_RECORD_ID,
        "ironcladId": "IC-100",
        "name": "Acme MSA 2026",
        "attachments": {
            "signedCopy": {
                "filename": SAMPLE_FILENAME,
                "contentType": "application/pdf",
                "href": (
                    f"{MOCK_ORIGIN}/public/api/v1/records/"
                    f"{IRONCLAD_RECORD_ID}/attachments/signedCopy"
                ),
            }
        },
    }


@app.get("/public/api/v1/records/{record_id}/attachments/{key}")
def ironclad_record_attachment(
    record_id: str,
    key: str,
    authorization: Optional[str] = Header(default=None),
):
    _require_ironclad_bearer(authorization)
    if record_id != IRONCLAD_RECORD_ID:
        raise HTTPException(status_code=404, detail="Record not found")
    if key != "signedCopy":
        raise HTTPException(status_code=404, detail="Attachment not found")
    return _pdf_response()


@app.get("/workflow/{workflow_id}", response_class=HTMLResponse)
def ironclad_browser_workflow(workflow_id: str):
    return f"<html><body>Ironclad workflow {workflow_id}</body></html>"


@app.get("/record/{record_id}", response_class=HTMLResponse)
def ironclad_browser_record(record_id: str):
    return f"<html><body>Ironclad record {record_id}</body></html>"


@app.get("/health")
def health():
    return JSONResponse(
        {
            "ok": True,
            "origin": MOCK_ORIGIN,
            "coupa": {
                "instance_url": MOCK_ORIGIN,
                "client_id": COUPA_CLIENT_ID,
                "client_secret": COUPA_CLIENT_SECRET,
                "import_url": f"{MOCK_ORIGIN}/contracts/show/{COUPA_CONTRACT_ID}",
            },
            "ironclad": {
                "base_url": MOCK_ORIGIN,
                "api_token": IRONCLAD_TOKEN,
                "workflow_url": f"{MOCK_ORIGIN}/workflow/{IRONCLAD_WORKFLOW_ID}",
                "record_url": f"{MOCK_ORIGIN}/record/{IRONCLAD_RECORD_ID}",
            },
        }
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        "context_jobs.clm.mock_server:app",
        host=MOCK_HOST,
        port=MOCK_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
