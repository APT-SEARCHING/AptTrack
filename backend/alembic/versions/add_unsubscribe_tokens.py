"""Add unsubscribe_token to price_subscriptions and unsubscribe_all_token to users.

Each token is a URL-safe random string (secrets.token_urlsafe(16) → 22 chars,
128 bits of entropy). They are stable forever — independent of JWT secret rotation.

Revision ID: add_unsubscribe_tokens
Revises: deactivate_area_subscriptions
Create Date: 2026-04-17
"""

import secrets

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "add_unsubscribe_tokens"
down_revision = "deactivate_area_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # --- price_subscriptions.unsubscribe_token ---
    op.add_column(
        "price_subscriptions",
        sa.Column("unsubscribe_token", sa.String(), nullable=True),
    )
    # Backfill existing rows — each gets its own unique token
    rows = conn.execute(text("SELECT id FROM price_subscriptions")).fetchall()
    for (row_id,) in rows:
        conn.execute(
            text("UPDATE price_subscriptions SET unsubscribe_token = :t WHERE id = :id"),
            {"t": secrets.token_urlsafe(16), "id": row_id},
        )
    op.create_unique_constraint(
        "uq_price_subscriptions_unsubscribe_token",
        "price_subscriptions",
        ["unsubscribe_token"],
    )
    op.create_index(
        "ix_price_subscriptions_unsubscribe_token",
        "price_subscriptions",
        ["unsubscribe_token"],
    )

    # --- users.unsubscribe_all_token ---
    op.add_column(
        "users",
        sa.Column("unsubscribe_all_token", sa.String(), nullable=True),
    )
    rows = conn.execute(text("SELECT id FROM users")).fetchall()
    for (row_id,) in rows:
        conn.execute(
            text("UPDATE users SET unsubscribe_all_token = :t WHERE id = :id"),
            {"t": secrets.token_urlsafe(16), "id": row_id},
        )
    op.create_unique_constraint(
        "uq_users_unsubscribe_all_token",
        "users",
        ["unsubscribe_all_token"],
    )
    op.create_index(
        "ix_users_unsubscribe_all_token",
        "users",
        ["unsubscribe_all_token"],
    )


def downgrade() -> None:
    op.drop_index("ix_users_unsubscribe_all_token", table_name="users")
    op.drop_constraint("uq_users_unsubscribe_all_token", "users", type_="unique")
    op.drop_column("users", "unsubscribe_all_token")

    op.drop_index(
        "ix_price_subscriptions_unsubscribe_token",
        table_name="price_subscriptions",
    )
    op.drop_constraint(
        "uq_price_subscriptions_unsubscribe_token",
        "price_subscriptions",
        type_="unique",
    )
    op.drop_column("price_subscriptions", "unsubscribe_token")
