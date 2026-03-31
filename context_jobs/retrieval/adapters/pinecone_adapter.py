from typing import Any

from pinecone import Pinecone

from context_jobs.retrieval.base import NormalizedMatch
from utils.utils import embed


class PineconeAdapter:
    provider = "pinecone"

    def __init__(self, config: dict[str, Any]) -> None:
        self.api_key = config.get("api_key")
        self.index_name = config.get("index_name")
        self.namespace = config.get("namespace")
        if not self.api_key or not self.index_name:
            raise ValueError("External Pinecone config requires api_key and index_name.")

        pc = Pinecone(api_key=self.api_key)
        self.index = pc.Index(self.index_name)

    def search(
        self,
        query_text: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[NormalizedMatch]:
        query_vec = embed(query_text)
        kwargs: dict[str, Any] = {
            "vector": query_vec,
            "top_k": top_k,
            "include_metadata": True,
        }
        if self.namespace:
            kwargs["namespace"] = self.namespace
        if filters:
            kwargs["filter"] = filters

        result = self.index.query(**kwargs)
        normalized: list[NormalizedMatch] = []
        for m in result.matches or []:
            meta = getattr(m, "metadata", None) or {}
            preview = (meta.get("preview") or meta.get("text") or "")[:600]
            normalized.append(
                NormalizedMatch(
                    id=str(getattr(m, "id", "")),
                    score=float(getattr(m, "score", 0.0) or 0.0),
                    text_preview=preview,
                    metadata=meta,
                )
            )
        return normalized

    def test_connection(self) -> tuple[bool, str]:
        try:
            _ = self.search("test connection", top_k=1)
            return True, "Pinecone connection test successful."
        except Exception as exc:
            return False, f"Pinecone connection failed: {exc}"

