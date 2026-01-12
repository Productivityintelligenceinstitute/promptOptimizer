import uuid
from pathlib import Path

from services.ingestion.file_service import read_text
from services.ingestion.chunking_service import chunk_text
from services.ingestion.embedding_service import embed_chunks
from services.ingestion.metadata_service import infer_metadata
from infrastructure.vectorstore.pinecone import upsert_vectors

def ingest_file_pipeline(file_path: Path, filename: str):
    raw_text = read_text(file_path)
    if not raw_text.strip():
        return

    chunks = chunk_text(raw_text)
    embeddings = embed_chunks(chunks)
    metadata = infer_metadata(filename)

    vectors = [
        {
            "id": str(uuid.uuid4()),
            "values": emb,
            "metadata": {
                **metadata,
                "preview": chunk[:300]
            }
        }
        for chunk, emb in zip(chunks, embeddings)
    ]

    upsert_vectors(vectors)
    
    return {
        "file": filename,
        "chunks": len(chunks),
        "vectors": len(vectors),
        "status": "Ingested into Pinecone"
    }