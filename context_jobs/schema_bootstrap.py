"""Lightweight dev schema alignment for ORM-first deployments."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from database.database import engine

logger = logging.getLogger(__name__)


def _add_column_if_missing(table: str, column: str, ddl: str) -> None:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns(table)}
    if column not in columns:
        with engine.begin() as conn:
            conn.execute(text(ddl))
        logger.info("Added %s.%s column", table, column)


def ensure_context_jobs_columns() -> None:
    """Add new context_jobs columns when tables predate model updates."""
    try:
        _add_column_if_missing(
            "context_jobs",
            "execution_mode",
            "ALTER TABLE context_jobs ADD COLUMN execution_mode VARCHAR NOT NULL DEFAULT 'single_agent'",
        )
        _add_column_if_missing(
            "context_jobs",
            "output_template",
            "ALTER TABLE context_jobs ADD COLUMN output_template TEXT NULL",
        )
        _add_column_if_missing(
            "context_jobs",
            "workspace_id",
            "ALTER TABLE context_jobs ADD COLUMN workspace_id VARCHAR NULL",
        )
        _add_column_if_missing(
            "context_job_versions",
            "is_current",
            "ALTER TABLE context_job_versions ADD COLUMN is_current BOOLEAN NOT NULL DEFAULT FALSE",
        )
        _add_column_if_missing(
            "job_runs",
            "job_version",
            "ALTER TABLE job_runs ADD COLUMN job_version INTEGER NULL",
        )
        for col, ddl in (
            ("pending_approvals", "ALTER TABLE job_runs ADD COLUMN pending_approvals JSONB NULL"),
            ("pending_memory_changes", "ALTER TABLE job_runs ADD COLUMN pending_memory_changes JSONB NULL"),
            ("repair_cycles", "ALTER TABLE job_runs ADD COLUMN repair_cycles INTEGER NOT NULL DEFAULT 0"),
            ("parent_run_id", "ALTER TABLE job_runs ADD COLUMN parent_run_id UUID NULL"),
            ("replay_snapshot", "ALTER TABLE job_runs ADD COLUMN replay_snapshot JSONB NULL"),
            ("workspace_id", "ALTER TABLE job_runs ADD COLUMN workspace_id VARCHAR NULL"),
        ):
            _add_column_if_missing("job_runs", col, ddl)
        for col, ddl in (
            ("owner", "ALTER TABLE context_assets ADD COLUMN owner VARCHAR NULL"),
            ("workspace_id", "ALTER TABLE context_assets ADD COLUMN workspace_id VARCHAR NULL"),
            ("approval_status", "ALTER TABLE context_assets ADD COLUMN approval_status VARCHAR NOT NULL DEFAULT 'approved'"),
        ):
            _add_column_if_missing("context_assets", col, ddl)
        inspector = inspect(engine)
        if "workspaces" not in inspector.get_table_names():
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS workspaces (
                            id VARCHAR PRIMARY KEY,
                            name TEXT NOT NULL,
                            owner VARCHAR NOT NULL,
                            tool_allowlist JSONB NULL,
                            source_allowlist JSONB NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS workspace_members (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            workspace_id VARCHAR NOT NULL REFERENCES workspaces(id),
                            user_id VARCHAR NOT NULL,
                            role VARCHAR NOT NULL DEFAULT 'editor',
                            UNIQUE (workspace_id, user_id)
                        )
                        """
                    )
                )
            logger.info("Created workspaces and workspace_members tables")
    except Exception:
        logger.exception("Failed to ensure context_jobs schema columns")
