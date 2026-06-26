"""add run_chains table and chain_config on context_jobs

Revision ID: 005_run_chains
Revises: 004_procurement_alerts
Create Date: 2026-06-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "005_run_chains"
down_revision: Union[str, Sequence[str], None] = "004_procurement_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("context_jobs", sa.Column("chain_config", postgresql.JSONB(), nullable=True))
    op.create_table(
        "run_chains",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("child_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("child_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("input_mapping", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_chains_parent_run_id", "run_chains", ["parent_run_id"], unique=False)
    op.create_index("ix_run_chains_child_job_id", "run_chains", ["child_job_id"], unique=False)
    op.create_index("ix_run_chains_child_run_id", "run_chains", ["child_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_run_chains_child_run_id", table_name="run_chains")
    op.drop_index("ix_run_chains_child_job_id", table_name="run_chains")
    op.drop_index("ix_run_chains_parent_run_id", table_name="run_chains")
    op.drop_table("run_chains")
    op.drop_column("context_jobs", "chain_config")
