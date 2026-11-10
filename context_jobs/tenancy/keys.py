"""Workspace ids and data partition keys (dependency-free so any module can import it)."""

from __future__ import annotations

import uuid

COMPANY_KEY_PREFIX = "org_"
PERSONAL_WORKSPACE_PREFIX = "ws_"
PERSONAL_WORKSPACE_SUFFIX = "_default"


def personal_workspace_id(firebase_uid: str) -> str:
    return f"{PERSONAL_WORKSPACE_PREFIX}{firebase_uid}{PERSONAL_WORKSPACE_SUFFIX}"


def new_company_workspace_id() -> str:
    return f"{COMPANY_KEY_PREFIX}{uuid.uuid4().hex}"


def is_company_owner_key(owner: str | None) -> bool:
    """
    True when ``owner`` is a company partition key. Firebase UIDs are alphanumeric,
    so the ``org_`` prefix cannot collide with a personal partition.
    """
    return bool(owner) and str(owner).startswith(COMPANY_KEY_PREFIX)
