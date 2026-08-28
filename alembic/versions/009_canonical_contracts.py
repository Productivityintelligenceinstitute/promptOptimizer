"""canonical contracts full-text store

Revision ID: 009_canonical_contracts
Revises: 008_run_artifact_blobs
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "009_canonical_contracts"
down_revision: Union[str, Sequence[str], None] = "008_run_artifact_blobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canonical_contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_doc_id", sa.String(), nullable=True),
        sa.Column("contract_id", sa.String(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
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
        sa.UniqueConstraint("owner", "source_doc_id", name="uq_canonical_contracts_owner_source_doc_id"),
    )
    op.create_index("ix_canonical_contracts_owner", "canonical_contracts", ["owner"], unique=False)
    op.create_index("ix_canonical_contracts_job_id", "canonical_contracts", ["job_id"], unique=False)
    op.create_index("ix_canonical_contracts_source_doc_id", "canonical_contracts", ["source_doc_id"], unique=False)
    op.create_index("ix_canonical_contracts_contract_id", "canonical_contracts", ["contract_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_canonical_contracts_contract_id", table_name="canonical_contracts")
    op.drop_index("ix_canonical_contracts_source_doc_id", table_name="canonical_contracts")
    op.drop_index("ix_canonical_contracts_job_id", table_name="canonical_contracts")
    op.drop_index("ix_canonical_contracts_owner", table_name="canonical_contracts")
    op.drop_table("canonical_contracts")
