"""Allow Plan.price to be NULL for 'Contact for pricing' floor plans.

Revision ID: alter_plan_price_nullable
Revises: add_scrape_run_table
Create Date: 2026-04-16
"""

from alembic import op

revision = "alter_plan_price_nullable"
down_revision = "add_scrape_run_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("plans", "price", nullable=True)


def downgrade() -> None:
    # Set any NULLs to 0 before restoring NOT NULL so downgrade doesn't fail.
    op.execute("UPDATE plans SET price = 0 WHERE price IS NULL")
    op.alter_column("plans", "price", nullable=False)
