"""Per-owner Pinecone namespace assignment for managed Jet KB (same index as platform)."""

from __future__ import annotations

import hashlib
import re

from sqlalchemy.orm import Session

from schemas.managed_jet_kb_namespace_model import ManagedJetKbNamespaceModel

# Pinecone namespace rules (conservative slug)
_NS_SAFE = re.compile(r"^[a-zA-Z0-9_-]{1,512}$")


def _slug_from_owner(owner: str) -> str:
    digest = hashlib.sha256(owner.encode("utf-8")).hexdigest()[:24]
    return f"jkb-{digest}"


def ensure_managed_namespace(db: Session, owner: str | None) -> str:
    """
    Return the persisted Pinecone namespace for this owner; create mapping on first use.

    Namespaces are logical partitions — no separate Pinecone API call is required to "create"
    them before query; we only persist a stable id per owner.
    """
    owner_key = (owner or "current_user").strip() or "current_user"
    row = (
        db.query(ManagedJetKbNamespaceModel)
        .filter(ManagedJetKbNamespaceModel.owner == owner_key)
        .first()
    )
    if row:
        return row.namespace

    slug = _slug_from_owner(owner_key)
    if not _NS_SAFE.match(slug):
        raise ValueError(f"Invalid derived namespace slug: {slug!r}")

    row = ManagedJetKbNamespaceModel(owner=owner_key, namespace=slug)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.namespace
