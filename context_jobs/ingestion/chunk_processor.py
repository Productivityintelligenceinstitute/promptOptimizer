"""
Document chunking for ingestion.

Reuses platform chunking logic from utils.chunking with configurable parameters.
"""

from __future__ import annotations

from typing import Any

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
        text = doc.get("text", "").strip()
        base_metadata = doc.get("metadata") or {}

        if not text:
            continue

        chunks = platform_chunk_text(text, max_chars=chunk_size, overlap=chunk_overlap)

        for chunk_idx, chunk in enumerate(chunks):
            chunked.append(
                {
                    "text": chunk,
                    "metadata": {
                        **base_metadata,
                        "chunk_index": chunk_idx,
                        "total_chunks": len(chunks),
                        "source_doc_id": doc.get("id") or f"doc_{doc_idx}",
                    },
                    "chunk_index": chunk_idx,
                    "source_doc_id": doc.get("id") or f"doc_{doc_idx}",
                }
            )

    return chunked
