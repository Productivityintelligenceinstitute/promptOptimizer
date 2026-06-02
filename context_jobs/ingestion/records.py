"""Vector record helpers (no retrieval/ingestion service imports)."""

from __future__ import annotations

import uuid
from typing import Any


def ensure_record_ids(records: list[dict[str, Any]]) -> None:
    for rec in records:
        if not rec.get("id"):
            rec["id"] = str(uuid.uuid4())


_QDRANT_ID_NAMESPACE = uuid.UUID("a3b8c2e1-4f5d-6e7a-8b9c-0d1e2f3a4b5c")


def qdrant_point_id(raw: Any) -> str | int:
    """Qdrant accepts UUID strings or unsigned integers only."""
    s = str(raw)
    try:
        return str(uuid.UUID(s))
    except ValueError:
        pass
    if s.isdigit():
        return int(s)
    return str(uuid.uuid5(_QDRANT_ID_NAMESPACE, s))
