"""add subscription_change_logs audit table

Revision ID: 006_subscription_change_logs
Revises: 005_run_chains
Create Date: 2026-07-03 16:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "006_subscription_change_logs"
down_revision: Union[str, Sequence[str], None] = "005_run_chains"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_change_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("performed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("old_status", sa.String(), nullable=True),
        sa.Column("new_status", sa.String(), nullable=True),
        sa.Column("old_end_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("new_end_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["performed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_subscription_change_logs_user_id",
        "subscription_change_logs",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_subscription_change_logs_user_id",
        table_name="subscription_change_logs",
    )
    op.drop_table("subscription_change_logs")
