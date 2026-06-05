"""Lightweight dev schema alignment for ORM-first deployments."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from database.database import engine

logger = logging.getLogger(__name__)


def ensure_context_jobs_columns() -> None:
    """Add new context_jobs columns when tables predate model updates."""
    try:
        inspector = inspect(engine)
        if "context_jobs" not in inspector.get_table_names():
            return
        columns = {col["name"] for col in inspector.get_columns("context_jobs")}
        if "execution_mode" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE context_jobs "
                        "ADD COLUMN execution_mode VARCHAR NOT NULL DEFAULT 'single_agent'"
                    )
                )
            logger.info("Added context_jobs.execution_mode column")
    except Exception:
        logger.exception("Failed to ensure context_jobs schema columns")
