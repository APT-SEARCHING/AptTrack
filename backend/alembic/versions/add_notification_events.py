"""Add notification_events table for delivery observability.

Tracks every outbound notification (email/telegram) with status, external ID
for webhook correlation, and trigger context.

Revision ID: add_notification_events
Revises: add_unsubscribe_tokens
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "add_notification_events"
down_revision = "add_unsubscribe_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("price_subscriptions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="sent"),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("trigger_type", sa.String(32), nullable=True),
        sa.Column("trigger_price", sa.Float(), nullable=True),
        sa.Column("baseline_price", sa.Float(), nullable=True),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
    )

    # Composite indexes for the two main query patterns
    op.create_index(
        "ix_notification_events_sub_sent",
        "notification_events",
        ["subscription_id", "sent_at"],
    )
    op.create_index(
        "ix_notification_events_status_sent",
        "notification_events",
        ["status", "sent_at"],
    )
    op.create_index(
        "ix_notification_events_external_id",
        "notification_events",
        ["external_id"],
    )
    op.create_index(
        "ix_notification_events_user_id",
        "notification_events",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_events_user_id", table_name="notification_events")
    op.drop_index("ix_notification_events_external_id", table_name="notification_events")
    op.drop_index("ix_notification_events_status_sent", table_name="notification_events")
    op.drop_index("ix_notification_events_sub_sent", table_name="notification_events")
    op.drop_table("notification_events")
