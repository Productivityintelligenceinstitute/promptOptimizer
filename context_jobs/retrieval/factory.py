from typing import Any

from context_jobs.retrieval.adapters.jet_kb_adapter import JetKbAdapter
from context_jobs.retrieval.adapters.pinecone_adapter import PineconeAdapter
from context_jobs.retrieval.adapters.qdrant_adapter import QdrantAdapter


def get_retrieval_adapter(
    provider: str,
    config: dict[str, Any] | None = None,
):
    provider_key = (provider or "").lower().strip()
    config = config or {}
    if provider_key in {"jet_kb", "jetkb", "internal"}:
        return JetKbAdapter()
    if provider_key == "pinecone":
        return PineconeAdapter(config=config)
    if provider_key == "qdrant":
        return QdrantAdapter(config=config)
    raise ValueError(f"Unsupported vector provider: {provider}")

