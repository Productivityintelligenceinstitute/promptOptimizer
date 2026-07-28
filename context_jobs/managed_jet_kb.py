"""Per-owner Pinecone namespace assignment for managed Jet KB (same index as platform)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from schemas.managed_jet_kb_namespace_model import ManagedJetKbNamespaceModel

# Pinecone namespace rules (conservative slug)
_NS_SAFE = re.compile(r"^[a-zA-Z0-9_-]{1,512}$")


def _slug_from_owner(owner: str) -> str:
    digest = hashlib.sha256(owner.encode("utf-8")).hexdigest()[:24]
    return f"jkb-{digest}"


def _owner_key(owner: str | None) -> str:
    return (owner or "current_user").strip() or "current_user"


def ensure_managed_namespace(db: Session, owner: str | None) -> str:
    """
    Return the persisted Pinecone namespace for this owner; create mapping on first use.

    Namespaces are logical partitions — no separate Pinecone API call is required to "create"
    them before query; we only persist a stable id per owner.
    """
    owner_key = _owner_key(owner)
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


def is_demo_kb_seeded(db: Session, owner: str | None) -> bool:
    """True when this owner already successfully seeded the procurement demo KB bundle."""
    owner_key = _owner_key(owner)
    row = (
        db.query(ManagedJetKbNamespaceModel.demo_kb_seeded_at)
        .filter(ManagedJetKbNamespaceModel.owner == owner_key)
        .first()
    )
    return bool(row and row[0] is not None)


def get_demo_kb_bundle_version(db: Session, owner: str | None) -> int:
    """Return the last successfully applied demo KB bundle version for this owner."""
    owner_key = _owner_key(owner)
    row = (
        db.query(ManagedJetKbNamespaceModel)
        .filter(ManagedJetKbNamespaceModel.owner == owner_key)
        .first()
    )
    if not row or row.demo_kb_seeded_at is None:
        return 0
    return int(getattr(row, "demo_kb_bundle_version", 0) or 0)


def mark_demo_kb_seeded(
    db: Session,
    owner: str | None,
    *,
    bundle_version: int | None = None,
) -> None:
    """Record a successful demo KB seed for this owner's managed namespace."""
    ensure_managed_namespace(db, owner)
    owner_key = _owner_key(owner)
    row = (
        db.query(ManagedJetKbNamespaceModel)
        .filter(ManagedJetKbNamespaceModel.owner == owner_key)
        .first()
    )
    if not row:
        return
    if row.demo_kb_seeded_at is None:
        row.demo_kb_seeded_at = datetime.now(timezone.utc)
    if bundle_version is not None:
        current = int(getattr(row, "demo_kb_bundle_version", 0) or 0)
        if bundle_version > current:
            row.demo_kb_bundle_version = bundle_version
    db.add(row)
    db.commit()
