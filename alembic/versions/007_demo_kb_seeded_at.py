"""add demo_kb_seeded_at to managed_jet_kb_namespaces

Revision ID: 007_demo_kb_seeded_at
Revises: 006_procurement_alert_description
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007_demo_kb_seeded_at"
down_revision: Union[str, Sequence[str], None] = "006_procurement_alert_description"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "managed_jet_kb_namespaces",
        sa.Column("demo_kb_seeded_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("managed_jet_kb_namespaces", "demo_kb_seeded_at")
