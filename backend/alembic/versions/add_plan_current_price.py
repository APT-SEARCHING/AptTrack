"""add current_price column to plans

Revision ID: add_plan_current_price
Revises: add_demo_subscription
Create Date: 2026-04-18
"""

import sqlalchemy as sa

from alembic import op

revision = 'add_plan_current_price'
down_revision = 'add_demo_subscription'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'plans',
        sa.Column(
            'current_price',
            sa.Float(),
            nullable=True,
            comment=(
                'Latest scraped price — updated on every successful scrape. '
                'NULL until first scrape. Use this instead of Plan.price for live queries.'
            ),
        ),
    )
    # Backfill: set current_price from the most recent PlanPriceHistory row.
    # Plans with no history rows remain NULL — _get_latest_price returns None for those.
    op.execute(
        """
        UPDATE plans
        SET current_price = (
            SELECT price
            FROM plan_price_history
            WHERE plan_id = plans.id
            ORDER BY recorded_at DESC
            LIMIT 1
        )
        """
    )


def downgrade() -> None:
    op.drop_column('plans', 'current_price')
