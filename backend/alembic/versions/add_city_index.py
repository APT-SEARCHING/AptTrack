"""Add case-insensitive index on apartments.city for price_checker queries

Revision ID: add_city_index
Revises: add_indexes_is_admin
Create Date: 2026-04-15 00:00:00.000000
"""

from alembic import op

revision = "add_city_index"
down_revision = "add_indexes_is_admin"
branch_labels = None
depends_on = None


def upgrade():
    # Functional index on lower(city) so ilike '%xxx%' at least benefits from
    # index scans when the leading wildcard is dropped (exact city names).
    # For true substring search, pg_trgm would be needed, but city values are
    # already normalised (e.g. "San Jose") so exact lower() equality is used
    # in all real queries.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_apartments_city_lower "
        "ON apartments (lower(city))"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_apartments_city_lower")
