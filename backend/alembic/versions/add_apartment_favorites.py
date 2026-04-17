"""Add apartment_favorites table.

Revision ID: add_apartment_favorites
Revises: add_notification_events
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa

revision = "add_apartment_favorites"
down_revision = "add_notification_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "apartment_favorites",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "apartment_id",
            sa.Integer(),
            sa.ForeignKey("apartments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "apartment_id", name="uq_favorites_user_apt"),
    )
    op.create_index("ix_apartment_favorites_user_id", "apartment_favorites", ["user_id"])
    op.create_index("ix_apartment_favorites_apartment_id", "apartment_favorites", ["apartment_id"])


def downgrade() -> None:
    op.drop_index("ix_apartment_favorites_apartment_id", table_name="apartment_favorites")
    op.drop_index("ix_apartment_favorites_user_id", table_name="apartment_favorites")
    op.drop_table("apartment_favorites")
