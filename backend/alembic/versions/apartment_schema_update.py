"""apartment schema update

Revision ID: apartment_schema_update
Revises: initial_migration
Create Date: 2024-03-10 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'apartment_schema_update'
down_revision = 'initial_migration'
branch_labels = None
depends_on = None

def upgrade():
    # Create the new tables

    # Create apartments table
    op.create_table(
        'apartments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.String(), nullable=True, unique=True, index=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('address', sa.String(), nullable=True),
        sa.Column('city', sa.String(), nullable=False, index=True),
        sa.Column('state', sa.String(length=2), nullable=False),
        sa.Column('zipcode', sa.String(length=10), nullable=False, index=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('property_type', sa.String(), nullable=False, server_default='apartment'),
        sa.Column('bedrooms', sa.Float(), nullable=False, index=True),
        sa.Column('bathrooms', sa.Float(), nullable=False),
        sa.Column('area_sqft', sa.Float(), nullable=True),
        sa.Column('has_parking', sa.Boolean(), nullable=True),
        sa.Column('has_pool', sa.Boolean(), nullable=True),
        sa.Column('has_gym', sa.Boolean(), nullable=True),
        sa.Column('has_dishwasher', sa.Boolean(), nullable=True),
        sa.Column('has_air_conditioning', sa.Boolean(), nullable=True),
        sa.Column('has_washer_dryer', sa.Boolean(), nullable=True),
        sa.Column('pets_allowed', sa.Boolean(), nullable=True),
        sa.Column('current_price', sa.Float(), nullable=True),
        sa.Column('available_from', sa.DateTime(), nullable=True),
        sa.Column('is_available', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create apartment_images table
    op.create_table(
        'apartment_images',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('apartment_id', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('caption', sa.String(), nullable=True),
        sa.Column('is_primary', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['apartment_id'], ['apartments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create neighborhoods table
    op.create_table(
        'neighborhoods',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False, index=True),
        sa.Column('city', sa.String(), nullable=False),
        sa.Column('state', sa.String(length=2), nullable=False),
        sa.Column('zipcode', sa.String(length=10), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('walkability_score', sa.Integer(), nullable=True),
        sa.Column('safety_score', sa.Integer(), nullable=True),
        sa.Column('avg_price_per_sqft', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create a new price_history table that references apartments
    op.create_table(
        'apartment_price_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('apartment_id', sa.Integer(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['apartment_id'], ['apartments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Check if listings table exists
    conn = op.get_bind()
    res = conn.execute("SELECT 1 FROM information_schema.tables WHERE table_name='listings'").scalar()

    if res:
        # Migrate data from old listings table to new apartments table
        # This is a basic migration - you may need to adjust based on your data
        op.execute("""
        INSERT INTO apartments (
            external_id, title, description, city, state, zipcode,
            bedrooms, bathrooms, area_sqft, created_at, updated_at
        )
        SELECT
            external_id, title, description,
            SPLIT_PART(location, ',', 1) as city,
            'CA' as state,
            '00000' as zipcode,
            bedrooms, bathrooms, area_sqft, created_at, updated_at
        FROM listings;
        """)

        # Migrate price history data
        op.execute("""
        INSERT INTO apartment_price_history (apartment_id, price, recorded_at)
        SELECT
            a.id as apartment_id, ph.price, ph.recorded_at
        FROM price_history ph
        JOIN listings l ON ph.listing_id = l.id
        JOIN apartments a ON a.external_id = l.external_id;
        """)

        # Drop old tables
        op.drop_table('price_history')
        op.drop_table('listings')


def downgrade():
    # Create the original tables
    op.create_table(
        'listings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('location', sa.String(), nullable=False),
        sa.Column('bedrooms', sa.Integer(), nullable=False),
        sa.Column('bathrooms', sa.Float(), nullable=False),
        sa.Column('area_sqft', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_id')
    )

    op.create_table(
        'price_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('listing_id', sa.Integer(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Migrate data back (simplified)
    op.execute("""
    INSERT INTO listings (
        external_id, title, description, location,
        bedrooms, bathrooms, area_sqft, created_at, updated_at
    )
    SELECT
        external_id, title, description,
        city || ', ' || state as location,
        bedrooms, bathrooms, area_sqft, created_at, updated_at
    FROM apartments;
    """)

    # Migrate price history data back
    op.execute("""
    INSERT INTO price_history (listing_id, price, recorded_at)
    SELECT
        l.id as listing_id, ph.price, ph.recorded_at
    FROM apartment_price_history ph
    JOIN apartments a ON ph.apartment_id = a.id
    JOIN listings l ON a.external_id = l.external_id;
    """)

    # Drop new tables
    op.drop_table('apartment_price_history')
    op.drop_table('neighborhoods')
    op.drop_table('apartment_images')
    op.drop_table('apartments')
