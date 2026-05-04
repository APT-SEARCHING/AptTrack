"""Add telegram linking fields to users table.

Revision ID: add_telegram_link
Revises: add_units_table
Create Date: 2026-05-04
"""

revision = "add_telegram_link"
down_revision = "add_units_table"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("users", sa.Column("telegram_chat_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("telegram_link_token", sa.String(), nullable=True))
    op.add_column("users", sa.Column("telegram_link_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_telegram_link_token", "users", ["telegram_link_token"], unique=True)


def downgrade():
    op.drop_index("ix_users_telegram_link_token", table_name="users")
    op.drop_column("users", "telegram_link_expires_at")
    op.drop_column("users", "telegram_link_token")
    op.drop_column("users", "telegram_chat_id")
