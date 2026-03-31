from typing import Any

from context_jobs.retrieval.base import NormalizedMatch
from utils.utils import retrieve


class JetKbAdapter:
    provider = "jet_kb"

    def search(
        self,
        query_text: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[NormalizedMatch]:
        matches = retrieve(query_text, top_k=top_k) or []
        normalized: list[NormalizedMatch] = []
        for m in matches:
            meta = getattr(m, "metadata", None) or {}
            preview = (meta.get("preview") or "")[:600]
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
            _ = self.search("test retrieval", top_k=1)
            return True, "JET KB adapter is healthy."
        except Exception as exc:
            return False, f"JET KB retrieval failed: {exc}"

