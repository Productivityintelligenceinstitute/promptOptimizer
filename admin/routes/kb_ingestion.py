from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from pathlib import Path
import uuid

from core.config import KB_DIR
from constants.file_types import PDF_EXT, TEXT_EXTS, DOC_EXTS
from core.ingestion_status import INGESTION_STATUS
from background.tasks.ingestion_task import process_ingestion

kb_ingestion_router = APIRouter()


@kb_ingestion_router.post("/ingest-file")
async def ingest_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    ext = Path(file.filename).suffix.lower()
    if ext not in (TEXT_EXTS | DOC_EXTS | {PDF_EXT}):
        raise HTTPException(400, f"Unsupported file type {ext}")

    save_path = KB_DIR / file.filename
    with open(save_path, "wb") as f:
        f.write(await file.read())

    job_id = str(uuid.uuid4())

    INGESTION_STATUS[job_id] = {
        "file": file.filename,
        "status": "Processing"
    }

    background_tasks.add_task(
        process_ingestion,
        job_id,
        save_path,
        file.filename
    )

    return {
        "job_id": job_id,
        "status": "Ingestion started"
    }

@kb_ingestion_router.get("/ingest-status/{job_id}")
def get_ingestion_status(job_id: str):
    if job_id not in INGESTION_STATUS:
        raise HTTPException(404, "Invalid job id")

    return INGESTION_STATUS[job_id]
