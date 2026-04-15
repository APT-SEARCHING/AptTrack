"""add is_admin to users and performance indexes

Revision ID: add_indexes_is_admin
Revises: add_users_subscriptions
Create Date: 2026-04-14 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_indexes_is_admin'
down_revision = 'add_users_subscriptions'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_admin flag to users
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), server_default='false', nullable=False))

    # Composite index for price history time-series queries
    op.create_index(
        'ix_price_history_plan_recorded',
        'plan_price_history',
        ['plan_id', 'recorded_at'],
    )

    # Composite index for location-based apartment filtering
    op.create_index(
        'ix_apartments_city_zipcode',
        'apartments',
        ['city', 'zipcode'],
    )

    # Composite index for bedroom-filtered plan queries
    op.create_index(
        'ix_plans_apartment_bedrooms',
        'plans',
        ['apartment_id', 'bedrooms'],
    )


def downgrade():
    op.drop_index('ix_plans_apartment_bedrooms', table_name='plans')
    op.drop_index('ix_apartments_city_zipcode', table_name='apartments')
    op.drop_index('ix_price_history_plan_recorded', table_name='plan_price_history')
    op.drop_column('users', 'is_admin')
