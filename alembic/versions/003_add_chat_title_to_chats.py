"""add chat_title to chats

Revision ID: 003_add_chat_title
Revises: add_soft_delete_to_users
Create Date: 2026-02-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003_add_chat_title"
down_revision: Union[str, Sequence[str], None] = "add_soft_delete_to_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _chat_title_column_exists(connection) -> bool:
    """Return True if chats.chat_title already exists (e.g. production already has it)."""
    result = connection.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'chats' AND column_name = 'chat_title'"
        )
    )
    return result.scalar() is not None


def upgrade() -> None:
    conn = op.get_bind()
    if not _chat_title_column_exists(conn):
        op.add_column(
            "chats",
            sa.Column("chat_title", sa.String(), server_default=sa.text("'Chat'"), nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _chat_title_column_exists(conn):
        op.drop_column("chats", "chat_title")
