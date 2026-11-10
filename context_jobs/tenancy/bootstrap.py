"""Idempotent, additive schema + data alignment for workspace tenancy.

Runs on every startup after ``create_all``. It only adds columns/indexes, inserts
missing personal workspaces and memberships, and fills NULL attribution columns.
It never drops, renames or rewrites existing values (except mapping legacy role
labels such as ``owner`` to ``tenant_admin``), so redeploying the previous build
remains a valid rollback.

Unlike the best-effort column patcher in ``schema_bootstrap``, failures here are
raised: running with a half-applied tenancy schema is a security risk.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("workspaces", "kind", "VARCHAR NOT NULL DEFAULT 'personal'"),
    ("workspaces", "status", "VARCHAR NOT NULL DEFAULT 'active'"),
    ("workspaces", "slug", "VARCHAR NULL"),
    ("workspaces", "package_name", "VARCHAR NULL"),
    ("workspaces", "access_expires_at", "TIMESTAMPTZ NULL"),
    ("workspaces", "created_by", "VARCHAR NULL"),
    ("workspaces", "notes", "TEXT NULL"),
    ("workspaces", "updated_at", "TIMESTAMPTZ NULL DEFAULT NOW()"),
    ("workspace_members", "status", "VARCHAR NOT NULL DEFAULT 'active'"),
    ("workspace_members", "invited_by", "VARCHAR NULL"),
    ("workspace_members", "created_at", "TIMESTAMPTZ NULL DEFAULT NOW()"),
    ("workspace_members", "updated_at", "TIMESTAMPTZ NULL DEFAULT NOW()"),
    ("context_jobs", "created_by", "VARCHAR NULL"),
    ("job_runs", "triggered_by", "VARCHAR NULL"),
    ("audit_events", "workspace_id", "VARCHAR NULL"),
    ("users", "last_login_at", "TIMESTAMPTZ NULL"),
)

_INDEXES: tuple[str, ...] = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_workspaces_slug ON workspaces (slug) WHERE slug IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_workspaces_kind ON workspaces (kind)",
    "CREATE INDEX IF NOT EXISTS ix_audit_events_workspace_id ON audit_events (workspace_id)",
    "CREATE INDEX IF NOT EXISTS ix_context_jobs_owner ON context_jobs (owner)",
    "CREATE INDEX IF NOT EXISTS ix_job_runs_job_id ON job_runs (job_id)",
)


def _is_user_owner(column: str) -> str:
    """SQL predicate: ``column`` holds a Firebase UID, not a company key or system owner."""
    return (
        f"({column} IS NOT NULL AND {column} NOT LIKE 'org\\_%' "
        f"AND {column} NOT LIKE '\\_\\_%' AND {column} <> 'current_user')"
    )


_BACKFILL: tuple[tuple[str, str], ...] = (
    (
        "personal workspaces",
        """
        INSERT INTO workspaces (id, name, owner, kind, status, created_at, updated_at)
        SELECT 'ws_' || u.firebase_uid || '_default', 'Personal workspace', u.firebase_uid,
               'personal', 'active', NOW(), NOW()
        FROM users u
        WHERE u.firebase_uid IS NOT NULL AND u.firebase_uid <> ''
        ON CONFLICT (id) DO NOTHING
        """,
    ),
    (
        "personal memberships",
        """
        INSERT INTO workspace_members (id, workspace_id, user_id, role, status, created_at, updated_at)
        SELECT gen_random_uuid(), w.id, w.owner, 'tenant_admin', 'active', NOW(), NOW()
        FROM workspaces w
        WHERE w.kind = 'personal'
        ON CONFLICT (workspace_id, user_id) DO NOTHING
        """,
    ),
    (
        "shared personal memberships",
        # The pre-tenancy members API could add users to someone else's personal
        # workspace. Personal workspaces are single-user now: disable (never delete).
        """
        UPDATE workspace_members m SET status = 'disabled'
        FROM workspaces w
        WHERE m.workspace_id = w.id AND w.kind = 'personal'
          AND m.user_id <> w.owner AND m.status <> 'disabled'
        """,
    ),
    (
        "legacy role labels",
        """
        UPDATE workspace_members
        SET role = CASE role WHEN 'editor' THEN 'analyst' ELSE 'tenant_admin' END
        WHERE role IN ('owner', 'admin', 'editor')
        """,
    ),
    (
        "job creator",
        f"""
        UPDATE context_jobs SET created_by = owner
        WHERE created_by IS NULL AND {_is_user_owner("owner")}
        """,
    ),
    (
        "job workspace",
        f"""
        UPDATE context_jobs SET workspace_id = 'ws_' || owner || '_default'
        WHERE workspace_id IS NULL AND {_is_user_owner("owner")}
        """,
    ),
    (
        "run initiator",
        f"""
        UPDATE job_runs r SET triggered_by = j.owner
        FROM context_jobs j
        WHERE r.job_id = j.id AND r.triggered_by IS NULL AND {_is_user_owner("j.owner")}
        """,
    ),
    (
        "run workspace",
        """
        UPDATE job_runs r SET workspace_id = j.workspace_id
        FROM context_jobs j
        WHERE r.job_id = j.id AND r.workspace_id IS NULL AND j.workspace_id IS NOT NULL
        """,
    ),
)


def _add_missing_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table, column, ddl in _COLUMNS:
        if table not in tables:
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        if column in existing:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        logger.info("Tenancy: added %s.%s", table, column)


def ensure_tenancy_schema(engine: Engine) -> None:
    """Align schema and backfill tenancy data. Safe to run on every startup."""
    try:
        _add_missing_columns(engine)
        with engine.begin() as conn:
            for statement in _INDEXES:
                conn.execute(text(statement))
            for label, statement in _BACKFILL:
                result = conn.execute(text(statement))
                if result.rowcount:
                    logger.info("Tenancy backfill (%s): %s rows", label, result.rowcount)
    except Exception:
        logger.exception("Tenancy schema alignment failed")
        raise
