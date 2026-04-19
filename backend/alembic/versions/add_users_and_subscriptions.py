"""add users and price subscriptions

Revision ID: add_users_subscriptions
Revises: merge_google_plan_heads
Create Date: 2026-04-14 00:00:00.000000

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'add_users_subscriptions'
down_revision = 'merge_google_plan_heads'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_id', 'users', ['id'])
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'price_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('apartment_id', sa.Integer(), nullable=True),
        sa.Column('plan_id', sa.Integer(), nullable=True),
        sa.Column('city', sa.String(), nullable=True),
        sa.Column('zipcode', sa.String(10), nullable=True),
        sa.Column('min_bedrooms', sa.Float(), nullable=True),
        sa.Column('max_bedrooms', sa.Float(), nullable=True),
        sa.Column('target_price', sa.Float(), nullable=True),
        sa.Column('price_drop_pct', sa.Float(), nullable=True),
        sa.Column('notify_email', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('notify_telegram', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('telegram_chat_id', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_notified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['apartment_id'], ['apartments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_price_subscriptions_id', 'price_subscriptions', ['id'])
    op.create_index('ix_price_subscriptions_user_id', 'price_subscriptions', ['user_id'])


def downgrade():
    op.drop_index('ix_price_subscriptions_user_id', table_name='price_subscriptions')
    op.drop_index('ix_price_subscriptions_id', table_name='price_subscriptions')
    op.drop_table('price_subscriptions')

    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_id', table_name='users')
    op.drop_table('users')
