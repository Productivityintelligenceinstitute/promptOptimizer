"""add procurement_alerts table

Revision ID: 004_procurement_alerts
Revises: 003_add_chat_title
Create Date: 2026-06-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "004_procurement_alerts"
down_revision: Union[str, Sequence[str], None] = "003_add_chat_title"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "procurement_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=True),
        sa.Column("vendor", sa.String(), nullable=True),
        sa.Column("contract_document_id", sa.String(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("complexity_tier", sa.String(), nullable=False),
        sa.Column("lead_months_threshold", sa.Integer(), nullable=False),
        sa.Column(
            "complexity_tier_defaulted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "alerted_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "dismissed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("suggested_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_procurement_alerts_owner",
        "procurement_alerts",
        ["owner"],
        unique=False,
    )
    op.create_index(
        "ix_procurement_alerts_contract_document_id",
        "procurement_alerts",
        ["contract_document_id"],
        unique=False,
    )
    op.create_index(
        "ix_procurement_alerts_dismissed",
        "procurement_alerts",
        ["dismissed"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_procurement_alerts_dismissed", table_name="procurement_alerts")
    op.drop_index(
        "ix_procurement_alerts_contract_document_id",
        table_name="procurement_alerts",
    )
    op.drop_index("ix_procurement_alerts_owner", table_name="procurement_alerts")
    op.drop_table("procurement_alerts")
