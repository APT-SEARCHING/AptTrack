"""Add indexes for new apartment/plan filter params.

Covers: pets_allowed, has_parking (apartment-level booleans),
area_sqft (plan-level range), available_from (plan-level date range,
partial index to skip NULLs).

Revision ID: add_filter_indexes
Revises: add_apartment_favorites
Create Date: 2026-04-17
"""

from alembic import op

revision = "add_filter_indexes"
down_revision = "add_apartment_favorites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_apartments_pets_allowed", "apartments", ["pets_allowed"])
    op.create_index("ix_apartments_has_parking",  "apartments", ["has_parking"])
    op.create_index("ix_plans_area_sqft",          "plans",      ["area_sqft"])
    op.create_index(
        "ix_plans_available_from_notnull",
        "plans",
        ["available_from"],
        postgresql_where="available_from IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("ix_plans_available_from_notnull", table_name="plans")
    op.drop_index("ix_plans_area_sqft",              table_name="plans")
    op.drop_index("ix_apartments_has_parking",       table_name="apartments")
    op.drop_index("ix_apartments_pets_allowed",      table_name="apartments")
