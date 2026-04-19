"""add external_url to plans table

Revision ID: add_plan_external_url
Revises: add_filter_indexes
Create Date: 2026-04-18

"""
import sqlalchemy as sa

from alembic import op

revision = 'add_plan_external_url'
down_revision = 'add_filter_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'plans',
        sa.Column(
            'external_url',
            sa.String(),
            nullable=True,
            comment="Deep link to this specific plan on the source site (e.g. ?floorplanId=S1)",
        ),
    )


def downgrade() -> None:
    op.drop_column('plans', 'external_url')
