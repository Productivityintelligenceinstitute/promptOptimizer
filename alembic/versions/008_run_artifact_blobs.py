"""run artifact blobs + amendment_run_id

Revision ID: 008_run_artifact_blobs
Revises: 007_demo_kb_seeded_at
Create Date: 2026-08-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "008_run_artifact_blobs"
down_revision: Union[str, Sequence[str], None] = "007_demo_kb_seeded_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_runs",
        sa.Column("amendment_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_job_runs_amendment_run_id", "job_runs", ["amendment_run_id"], unique=False)
    op.create_table(
        "run_artifact_blobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visible_on_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("tool_id", sa.String(), nullable=True),
        sa.Column("purpose", sa.String(), nullable=False, server_default="artifact"),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "path", name="uq_run_artifact_blobs_run_id_path"),
    )
    op.create_index("ix_run_artifact_blobs_owner", "run_artifact_blobs", ["owner"], unique=False)
    op.create_index("ix_run_artifact_blobs_run_id", "run_artifact_blobs", ["run_id"], unique=False)
    op.create_index(
        "ix_run_artifact_blobs_visible_on_run_id",
        "run_artifact_blobs",
        ["visible_on_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_run_artifact_blobs_visible_on_run_id", table_name="run_artifact_blobs")
    op.drop_index("ix_run_artifact_blobs_run_id", table_name="run_artifact_blobs")
    op.drop_index("ix_run_artifact_blobs_owner", table_name="run_artifact_blobs")
    op.drop_table("run_artifact_blobs")
    op.drop_index("ix_job_runs_amendment_run_id", table_name="job_runs")
    op.drop_column("job_runs", "amendment_run_id")
