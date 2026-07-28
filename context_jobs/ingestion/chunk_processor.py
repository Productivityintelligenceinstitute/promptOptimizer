"""
Document chunking for ingestion.

Reuses platform chunking logic from utils.chunking with configurable parameters.
"""

from __future__ import annotations

import uuid
from typing import Any

from context_jobs.ingestion.metadata import normalize_document_metadata
from context_jobs.text_sanitize import sanitize_db_text
from utils.chunking import chunk_text as platform_chunk_text


def chunk_documents(
    documents: list[dict[str, Any]],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[dict[str, Any]]:
    """
    Chunk a list of documents into smaller text segments.

    Args:
        documents: List of {text: str, metadata: dict} dicts
        chunk_size: Max characters per chunk
        chunk_overlap: Overlap between chunks

    Returns:
        List of {text: str, metadata: dict, chunk_index: int, source_doc_id: str}
    """
    chunked = []

    for doc_idx, doc in enumerate(documents):
        text = sanitize_db_text(doc.get("text", "")).strip()
        # Prefer caller id; never fall back to a reused doc_0 style id across
        # separate paste ingestions (that overwrites prior vectors in Pinecone/Qdrant).
        raw_id = doc.get("id")
        doc_id = str(raw_id).strip() if raw_id is not None else ""
        if not doc_id:
            doc_id = f"doc_{doc_idx}_{uuid.uuid4().hex[:12]}"
        base_metadata = normalize_document_metadata(
            doc.get("metadata"),
            doc_id=doc_id,
            text=text,
        )

        if not text:
            continue

        chunks = platform_chunk_text(text, max_chars=chunk_size, overlap=chunk_overlap)

        for chunk_idx, chunk in enumerate(chunks):
            clean_chunk = sanitize_db_text(chunk)
            chunked.append(
                {
                    "text": clean_chunk,
                    "metadata": {
                        **base_metadata,
                        "chunk_index": chunk_idx,
                        "total_chunks": len(chunks),
                        "source_doc_id": doc_id,
                    },
                    "chunk_index": chunk_idx,
                    "source_doc_id": doc_id,
                }
            )

    return chunked
