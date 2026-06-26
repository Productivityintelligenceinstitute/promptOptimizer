"""Run all idempotent database seeds on application startup."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from context_jobs.permissions_seed import seed_context_jobs_permissions
from context_jobs.procurement_templates_seed import seed_procurement_templates
from context_jobs.tools.seed_registry import seed_tool_registry
from database.bootstrap_seed import seed_bootstrap

logger = logging.getLogger(__name__)


def run_startup_seeds(db: Session) -> None:
    """Seed packages, permissions, tools, and Context Jobs data (skips existing rows)."""
    seed_bootstrap(db)
    seed_tool_registry(db)
    seed_context_jobs_permissions(db)
    seed_procurement_templates(db)
    logger.info("Startup database seeding complete")
