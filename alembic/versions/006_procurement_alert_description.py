"""add description to procurement_alerts

Revision ID: 006_procurement_alert_description
Revises: 005_run_chains
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_procurement_alert_description"
down_revision: Union[str, Sequence[str], None] = "005_run_chains"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("procurement_alerts", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("procurement_alerts", "description")
