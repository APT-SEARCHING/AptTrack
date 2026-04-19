"""patch apartments table: add missing columns

Revision ID: patch_apartments_missing_cols
Revises: add_indexes_is_admin
Create Date: 2026-04-14 00:00:03.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "patch_apartments_missing_cols"
down_revision = "add_indexes_is_admin"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("apartments")}

    if "bedrooms" not in existing:
        op.add_column("apartments", sa.Column("bedrooms", sa.Float(), nullable=False, server_default="0"))
    if "bathrooms" not in existing:
        op.add_column("apartments", sa.Column("bathrooms", sa.Float(), nullable=False, server_default="0"))
    if "area_sqft" not in existing:
        op.add_column("apartments", sa.Column("area_sqft", sa.Float(), nullable=True))
    if "current_price" not in existing:
        op.add_column("apartments", sa.Column("current_price", sa.Float(), nullable=True))
    if "available_from" not in existing:
        op.add_column("apartments", sa.Column("available_from", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("apartments", "available_from")
    op.drop_column("apartments", "current_price")
    op.drop_column("apartments", "area_sqft")
    op.drop_column("apartments", "bathrooms")
    op.drop_column("apartments", "bedrooms")
