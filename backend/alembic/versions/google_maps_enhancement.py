"""google maps enhancement

Revision ID: google_maps_enhancement
Revises: apartment_schema_update
Create Date: 2024-08-18 18:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'google_maps_enhancement'
down_revision = 'apartment_schema_update'
branch_labels = None
depends_on = None

def upgrade():
    # Add new columns to apartments table for Google Maps API data (idempotent)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c['name'] for c in inspector.get_columns('apartments')}

    if 'phone' not in existing_cols:
        op.add_column('apartments', sa.Column('phone', sa.String(), nullable=True, comment='Phone number for the property'))
    if 'rating' not in existing_cols:
        op.add_column('apartments', sa.Column('rating', sa.Float(), nullable=True, comment='Google rating (0-5)'))
    if 'user_rating_count' not in existing_cols:
        op.add_column('apartments', sa.Column('user_rating_count', sa.Integer(), nullable=True, comment='Number of user ratings'))
    if 'business_name' not in existing_cols:
        op.add_column('apartments', sa.Column('business_name', sa.String(), nullable=True, comment='Official business name of the property'))

def downgrade():
    # Remove the added columns
    op.drop_column('apartments', 'phone')
    op.drop_column('apartments', 'rating')
    op.drop_column('apartments', 'user_rating_count')
    op.drop_column('apartments', 'business_name')
