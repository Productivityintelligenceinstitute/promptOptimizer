import uuid
from pathlib import Path

from utils.reader import read_file
from utils.chunking import chunk_text
from utils.embedding import embed_texts
from utils.metadata import infer_metadata
from core.config import index

from core.ingestion_status import INGESTION_STATUS


def process_ingestion(job_id: str, save_path: Path, filename: str):
    try:
        raw_text = read_file(save_path)
        if not raw_text.strip():
            INGESTION_STATUS[job_id]["status"] = "Failed: No text found"
            return

        chunks = chunk_text(raw_text)
        embeddings = embed_texts(chunks)
        meta_base = infer_metadata(filename)

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

        BATCH_SIZE = 100
        for i in range(0, len(vectors), BATCH_SIZE):
            index.upsert(vectors=vectors[i:i + BATCH_SIZE])

        INGESTION_STATUS[job_id].update({
            "file": filename,
            "chunks": len(chunks),
            "vectors": len(vectors),
            "status": "Ingested into Pinecone"
        })

    except Exception as e:
        INGESTION_STATUS[job_id]["status"] = f"Failed: {str(e)}"
