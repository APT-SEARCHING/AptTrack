"""add is_demo column to price_subscriptions

Revision ID: add_demo_subscription
Revises: add_plan_floor_facing
Create Date: 2026-04-18
"""

import sqlalchemy as sa

from alembic import op

revision = 'add_demo_subscription'
down_revision = 'add_plan_floor_facing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'price_subscriptions',
        sa.Column(
            'is_demo',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='Auto-created demo subscription shown to new users',
        ),
    )


def downgrade() -> None:
    op.drop_column('price_subscriptions', 'is_demo')
