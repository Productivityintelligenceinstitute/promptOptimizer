"""
Embedding processor for ingestion chunks.

Uses embed_query for multi-provider configs; batches OpenAI platform embeddings
via utils.embedding.embed_texts (same path as admin KB ingestion).
"""

from __future__ import annotations

from typing import Any

from context_jobs.embeddings import embed_query
from context_jobs.embeddings.registry import infer_provider


def embed_chunks(
    chunks: list[dict[str, Any]],
    config: dict[str, Any],
    batch_size: int = 50,
) -> list[dict[str, Any]]:
    """
    Embed text chunks using the connection embedding profile.

    Returns list of {text, metadata, embedding, chunk_index, source_doc_id}.
    """
    texts: list[str] = []
    meta_rows: list[dict[str, Any]] = []
    for chunk in chunks:
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        texts.append(text)
        meta_rows.append(
            {
                "metadata": chunk.get("metadata") or {},
                "chunk_index": chunk.get("chunk_index"),
                "source_doc_id": chunk.get("source_doc_id"),
            }
        )

    if not texts:
        return []

    provider = (config.get("embedding_provider") or "").strip().lower()
    if not provider:
        model = (config.get("embedding_model") or "").strip()
        provider = infer_provider(model) or "openai"

    vectors: list[list[float]] = []

    # OpenAI platform path: batch API (faster, matches admin ingestion_job).
    if provider == "openai" and not (config.get("embedding_api_key") or "").strip():
        from utils.embedding import embed_texts

        model = (config.get("embedding_model") or "").strip() or None
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            vectors.extend(embed_texts(batch, batch_size=len(batch), model=model))
    else:
        for text in texts:
            vectors.append(embed_query(text, config))

    embedded: list[dict[str, Any]] = []
    for text, vec, meta in zip(texts, vectors, meta_rows):
        embedded.append(
            {
                "text": text,
                "metadata": meta["metadata"],
                "embedding": vec,
                "chunk_index": meta["chunk_index"],
                "source_doc_id": meta["source_doc_id"],
            }
        )
    return embedded
