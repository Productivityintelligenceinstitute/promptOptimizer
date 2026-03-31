from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class NormalizedMatch:
    id: str
    score: float
    text_preview: str
    metadata: dict[str, Any]


class RetrievalAdapter(Protocol):
    def search(
        self,
        query_text: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[NormalizedMatch]:
        ...

    def test_connection(self) -> tuple[bool, str]:
        ...

