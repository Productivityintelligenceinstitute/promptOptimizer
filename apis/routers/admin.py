import os
import uuid
from pathlib import Path
from typing import List, Dict

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from admin.core.reader import read_file
from admin.core.chunking import chunk_text
from admin.core.embedding import embed_texts
from admin.core.metadata import infer_metadata
from config import KB_DIR, index
from constants.file_types import PDF_EXT, TEXT_EXTS, DOC_EXTS

kb_ingestion_router = APIRouter()

@kb_ingestion_router.post("/ingest-file")
async def ingest_file(file: UploadFile = File(...)):
    """
    Upload any document → Read → Chunk → Embed → Upsert to Pinecone.
    """
    ext = Path(file.filename).suffix.lower()

    if ext not in (TEXT_EXTS | DOC_EXTS | {PDF_EXT}):
        raise HTTPException(400, f"Unsupported file type {ext}")

    # Save file locally
    save_path = KB_DIR / file.filename
    with open(save_path, "wb") as f:
        f.write(await file.read())

    # Process file
    raw_text = read_file(save_path)
    if not raw_text.strip():
        raise HTTPException(400, "No text found in the file.")

    chunks = chunk_text(raw_text)
    embeddings = embed_texts(chunks)
    meta_base = infer_metadata(file.filename)

    vectors = []
    for chunk, emb in zip(chunks, embeddings):
        vectors.append({
            "id": str(uuid.uuid4()),
            "values": emb,
            "metadata": {
                **meta_base,
                "preview": chunk[:300]
            }
        })

    # Upsert in batches
    BATCH_SIZE = 100
    for i in range(0, len(vectors), BATCH_SIZE):
        batch = vectors[i:i + BATCH_SIZE]
        index.upsert(vectors=batch)

    return {
        "file": file.filename,
        "chunks": len(chunks),
        "vectors": len(vectors),
        "status": "Ingested into Pinecone"
    }
