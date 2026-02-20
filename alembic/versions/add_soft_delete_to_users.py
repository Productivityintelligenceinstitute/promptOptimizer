"""add soft delete fields to users

Revision ID: add_soft_delete_to_users
Revises: bb4a426f0f21
Create Date: 2026-02-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_soft_delete_to_users"
down_revision: Union[str, None] = "002_add_message_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_active and deleted_at columns to users for soft delete."""
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove soft delete columns from users."""
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "is_active")

