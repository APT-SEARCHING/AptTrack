"""add floor_level and facing to plans table

Revision ID: add_plan_floor_facing
Revises: add_plan_external_url
Create Date: 2026-04-18

"""
import sqlalchemy as sa

from alembic import op

revision = 'add_plan_floor_facing'
down_revision = 'add_plan_external_url'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'plans',
        sa.Column(
            'floor_level',
            sa.Integer(),
            nullable=True,
            comment="Floor number this unit is on (integer, e.g. 3 for 3rd floor)",
        ),
    )
    op.add_column(
        'plans',
        sa.Column(
            'facing',
            sa.String(),
            nullable=True,
            comment="Compass direction this unit faces: N/S/E/W/NE/NW/SE/SW",
        ),
    )


def downgrade() -> None:
    op.drop_column('plans', 'facing')
    op.drop_column('plans', 'floor_level')
