from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from pathlib import Path
import os
import uuid
import logging

from core.config import KB_DIR, index
from constants.file_types import PDF_EXT, TEXT_EXTS, DOC_EXTS
from core.ingestion_status import INGESTION_STATUS


kb_ingestion_router = APIRouter()


@kb_ingestion_router.post("/ingest-file")
async def ingest_file(request: Request, file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in (TEXT_EXTS | DOC_EXTS | {PDF_EXT}):
        raise HTTPException(400, detail=f"Unsupported file type {ext}")

    max_size = 20 * 1024 * 1024  # 20 MB — keep in sync with admin KB UI
    save_path = KB_DIR / file.filename

    try:
        contents = await file.read()
        if len(contents) > max_size:
            raise HTTPException(
                413, detail="File too large. Maximum allowed size is 20MB."
            )

        with open(save_path, "wb") as out_file:
            out_file.write(contents)
        del contents
    except HTTPException:
        raise
    except Exception:
        if os.path.exists(save_path):
            os.remove(save_path)
        logging.exception("Failed to save file %s", file.filename)
        raise HTTPException(
            500, detail="Failed to save file. Please try again."
        )

    job_id = str(uuid.uuid4())
    INGESTION_STATUS[job_id] = {
        "file": file.filename,
        "status": "Queued for ingestion",
    }

    job_queue = request.app.state.job_queue
    try:
        job_queue.put_nowait((job_id, file.filename, save_path))
    except Exception:
        if os.path.exists(save_path):
            os.remove(save_path)
        INGESTION_STATUS[job_id]["status"] = "Failed: Queue full"
        raise HTTPException(
            429,
            detail="Server is busy. Max 20 jobs can be queued. Try again later.",
        )

    return {
        "job_id": job_id,
        "status": "Ingestion started",
    }


@kb_ingestion_router.get("/queue-status")
def queue_status(request: Request):
    active_jobs_fn = getattr(request.app.state, "active_jobs", None)
    active_jobs = active_jobs_fn() if callable(active_jobs_fn) else 0
    job_queue = request.app.state.job_queue
    queued = job_queue.qsize()
    return {
        "active_jobs": active_jobs,
        "queued_jobs": queued,
        "slots_available": max(0, 2 - active_jobs),
        "queue_capacity": 20,
    }


@kb_ingestion_router.get("/ingest-status/{job_id}")
def get_ingestion_status(job_id: str):
    if job_id not in INGESTION_STATUS:
        raise HTTPException(404, "Invalid job id")

    return INGESTION_STATUS[job_id]


@kb_ingestion_router.get("/pinecone-status")
async def pinecone_status():
    try:
        stats = index.describe_index_stats()
        return {
            "total_vectors": stats.total_vector_count,
            "namespaces": {
                k: v.vector_count for k, v in stats.namespaces.items()
            },
            "dimension": stats.dimension,
            "index_fullness": stats.index_fullness,
        }
    except Exception as e:
        raise HTTPException(
            500, detail=f"Failed to fetch Pinecone stats: {str(e)}"
        )
