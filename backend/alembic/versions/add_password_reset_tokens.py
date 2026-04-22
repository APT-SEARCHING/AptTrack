"""add password_reset_tokens table

Revision ID: add_password_reset_tokens
Revises: add_api_cost_log
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa

revision = "add_password_reset_tokens"
down_revision = "add_api_cost_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_password_reset_tokens_token", "password_reset_tokens", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_token", "password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_user_id", "password_reset_tokens")
    op.drop_table("password_reset_tokens")
