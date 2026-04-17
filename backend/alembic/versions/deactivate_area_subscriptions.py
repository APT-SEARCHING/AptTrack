"""Deactivate area-level subscriptions (city/zipcode/bedrooms-only rows).

Area-level subscriptions are disabled at the API layer (bug #5 fix).
Existing rows are set to is_active=False rather than deleted so that user
intent is preserved if area-level support is re-enabled later.

Revision ID: deactivate_area_subscriptions
Revises: add_subscription_trigger_count
Create Date: 2026-04-17
"""

from alembic import op

revision = "deactivate_area_subscriptions"
down_revision = "add_subscription_trigger_count"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE price_subscriptions
        SET is_active = FALSE
        WHERE plan_id IS NULL
          AND apartment_id IS NULL
    """)


def downgrade() -> None:
    # Cannot safely re-activate without knowing which rows were active before —
    # leave as-is on downgrade (no data loss, just potentially inactive rows).
    pass
