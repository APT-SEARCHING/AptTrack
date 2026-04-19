"""create google places raw and google apartments tables

Revision ID: google_places_tables
Revises: google_maps_enhancement
Create Date: 2025-08-19 00:00:00.000000

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = 'google_places_tables'
down_revision = 'google_maps_enhancement'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'google_places_raw',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('place_resource_name', sa.String(), nullable=False),
        sa.Column('place_id', sa.String(), nullable=True),
        sa.Column('display_name', sa.String(), nullable=True),
        sa.Column('formatted_address', sa.String(), nullable=True),
        sa.Column('website_uri', sa.String(), nullable=True),
        sa.Column('national_phone_number', sa.String(), nullable=True),
        sa.Column('rating', sa.Float(), nullable=True),
        sa.Column('user_rating_count', sa.Integer(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('raw_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('source', sa.String(), nullable=False, server_default='google_places_v1'),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_google_places_raw_place_resource_name', 'google_places_raw', ['place_resource_name'], unique=True)
    op.create_index('ix_google_places_raw_place_id', 'google_places_raw', ['place_id'], unique=False)

    op.create_table(
        'google_apartments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('place_resource_name', sa.String(), nullable=False),
        sa.Column('external_id', sa.String(), nullable=False),
        sa.Column('business_name', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('address', sa.String(), nullable=True),
        sa.Column('city', sa.String(), nullable=True),
        sa.Column('state', sa.String(), nullable=True),
        sa.Column('zipcode', sa.String(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('property_type', sa.String(), nullable=False, server_default='apartment'),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('rating', sa.Float(), nullable=True),
        sa.Column('user_rating_count', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(), nullable=False, server_default='google'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_google_apartments_place_resource_name', 'google_apartments', ['place_resource_name'], unique=False)
    op.create_index('ix_google_apartments_external_id', 'google_apartments', ['external_id'], unique=True)


def downgrade():
    op.drop_index('ix_google_apartments_external_id', table_name='google_apartments')
    op.drop_index('ix_google_apartments_place_resource_name', table_name='google_apartments')
    op.drop_table('google_apartments')

    op.drop_index('ix_google_places_raw_place_id', table_name='google_places_raw')
    op.drop_index('ix_google_places_raw_place_resource_name', table_name='google_places_raw')
    op.drop_table('google_places_raw')


