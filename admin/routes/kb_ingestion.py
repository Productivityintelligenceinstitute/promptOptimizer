from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from pathlib import Path

from background.tasks.ingestion_task import process_ingestion
from core.config import KB_DIR
from constants.file_types import PDF_EXT, TEXT_EXTS, DOC_EXTS

kb_ingestion_router = APIRouter()

@kb_ingestion_router.post("/ingest-file")
async def ingest_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in (TEXT_EXTS | DOC_EXTS | {PDF_EXT}):
        raise HTTPException(400, "Unsupported file type")

    save_path = KB_DIR / file.filename
    with open(save_path, "wb") as f:
        f.write(await file.read())

    background_tasks.add_task(
        process_ingestion,
        save_path,
        file.filename
    )

    # return {
    #     "file": file.filename,
    #     "chunks": len(chunks),
    #     "vectors": len(vectors),
    #     "status": "Ingested into Pinecone"
    # }
