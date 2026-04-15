"""plan schema update

Revision ID: plan_schema_update
Revises: apartment_schema_update
Create Date: 2024-03-10 14:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'plan_schema_update'
down_revision = 'apartment_schema_update'
branch_labels = None
depends_on = None

def upgrade():
    # Create plans table
    op.create_table(
        'plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('apartment_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('bedrooms', sa.Float(), nullable=False, index=True),
        sa.Column('bathrooms', sa.Float(), nullable=False),
        sa.Column('area_sqft', sa.Float(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('available_from', sa.DateTime(), nullable=True),
        sa.Column('is_available', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['apartment_id'], ['apartments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create plan_price_history table
    op.create_table(
        'plan_price_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Migrate data from apartments to plans
    # First, check if the bedrooms, bathrooms, area_sqft, and current_price columns exist in the apartments table
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('apartments')]

    if all(col in columns for col in ['bedrooms', 'bathrooms', 'area_sqft', 'current_price']):
        # Migrate data from apartments to plans
        op.execute("""
        INSERT INTO plans (
            apartment_id, name, bedrooms, bathrooms, area_sqft, price, is_available
        )
        SELECT
            id,
            'Default Plan',
            bedrooms,
            bathrooms,
            area_sqft,
            current_price,
            is_available
        FROM apartments
        WHERE bedrooms IS NOT NULL AND bathrooms IS NOT NULL AND area_sqft IS NOT NULL AND current_price IS NOT NULL;
        """)

        # Migrate price history data
        if 'apartment_price_history' in inspector.get_table_names():
            op.execute("""
            INSERT INTO plan_price_history (plan_id, price, recorded_at)
            SELECT
                p.id as plan_id,
                aph.price,
                aph.recorded_at
            FROM apartment_price_history aph
            JOIN apartments a ON aph.apartment_id = a.id
            JOIN plans p ON p.apartment_id = a.id;
            """)

            # Drop old price_history table
            op.drop_table('apartment_price_history')

    # Remove columns from apartments table that are now in plans
    for column in ['bedrooms', 'bathrooms', 'area_sqft', 'current_price', 'available_from']:
        if column in columns:
            op.drop_column('apartments', column)

def downgrade():
    # Add back columns to apartments table
    op.add_column('apartments', sa.Column('bedrooms', sa.Float(), nullable=True))
    op.add_column('apartments', sa.Column('bathrooms', sa.Float(), nullable=True))
    op.add_column('apartments', sa.Column('area_sqft', sa.Float(), nullable=True))
    op.add_column('apartments', sa.Column('current_price', sa.Float(), nullable=True))
    op.add_column('apartments', sa.Column('available_from', sa.DateTime(), nullable=True))

    # Create apartment_price_history table
    op.create_table(
        'apartment_price_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('apartment_id', sa.Integer(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['apartment_id'], ['apartments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Migrate data back from plans to apartments
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'plans' in inspector.get_table_names():
        # For each apartment, find the first plan and use its data
        op.execute("""
        UPDATE apartments a
        SET
            bedrooms = p.bedrooms,
            bathrooms = p.bathrooms,
            area_sqft = p.area_sqft,
            current_price = p.price,
            available_from = p.available_from
        FROM plans p
        WHERE a.id = p.apartment_id
        AND p.id IN (
            SELECT MIN(id) FROM plans GROUP BY apartment_id
        );
        """)

        # Migrate price history data back
        op.execute("""
        INSERT INTO apartment_price_history (apartment_id, price, recorded_at)
        SELECT
            p.apartment_id,
            pph.price,
            pph.recorded_at
        FROM plan_price_history pph
        JOIN plans p ON pph.plan_id = p.id;
        """)

    # Drop new tables
    op.drop_table('plan_price_history')
    op.drop_table('plans')
