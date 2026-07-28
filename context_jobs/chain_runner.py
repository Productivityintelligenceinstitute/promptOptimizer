"""Lifecycle chain handoff — disabled.

Procurement lifecycle guidance now lives in the template gallery.
Users copy useful result sections into the next job's User request manually.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session


def prepare_chain_handoff(run_id: UUID, rop: dict[str, Any] | None, db: Session) -> None:
    """No-op: automatic chain handoff is disabled."""
    _ = (run_id, rop, db)


# Keep old name as alias so any other callers (tests, scripts) don't break
evaluate_chain = prepare_chain_handoff
