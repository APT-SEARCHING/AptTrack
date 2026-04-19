"""add current_special column to apartments

Revision ID: add_apartment_current_special
Revises: add_plan_current_price
Create Date: 2026-04-18
"""

import sqlalchemy as sa

from alembic import op

revision = 'add_apartment_current_special'
down_revision = 'add_plan_current_price'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'apartments',
        sa.Column(
            'current_special',
            sa.Text(),
            nullable=True,
            comment=(
                'Current move-in offer or discount as plain text, e.g. "$250 deposit", '
                '"1 month free on 12-month leases". Overwritten on each scrape. NULL if none found.'
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column('apartments', 'current_special')
