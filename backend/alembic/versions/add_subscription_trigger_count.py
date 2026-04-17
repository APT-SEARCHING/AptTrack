"""Add trigger_count to price_subscriptions.

Revision ID: add_subscription_trigger_count
Revises: add_subscription_price_tracking
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa

revision = "add_subscription_trigger_count"
down_revision = "add_subscription_price_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "price_subscriptions",
        sa.Column(
            "trigger_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of times a notification has fired for this subscription",
        ),
    )


def downgrade() -> None:
    op.drop_column("price_subscriptions", "trigger_count")
