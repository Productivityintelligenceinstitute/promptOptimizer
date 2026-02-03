"""add message_type column to messages table

Revision ID: 002_add_message_type
Revises: bb4a426f0f21
Create Date: 2025-02-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_add_message_type'
down_revision: Union[str, Sequence[str], None] = 'bb4a426f0f21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add message_type column to messages table."""
    op.add_column('messages', sa.Column('message_type', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove message_type column from messages table."""
    op.drop_column('messages', 'message_type')
