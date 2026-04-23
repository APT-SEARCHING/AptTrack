"""add corporate parent columns to site registry and scrape runs

Revision ID: add_corporate_parent_columns
Revises: add_password_reset_tokens
Create Date: 2026-04-22 00:00:00.000000

Adds three nullable columns to scrape_site_registry:
  - corporate_parent_url: override scrape target for brand-front subdomains
  - corporate_platform:   human-readable platform tag (e.g. 'greystar')
  - corporate_parent_set_at: when the override was last set

Adds one nullable column to scrape_runs:
  - effective_url: actual URL scraped when a corporate redirect fired

No data migration — all columns are nullable.
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_corporate_parent_columns"
down_revision = "add_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "scrape_site_registry",
        sa.Column(
            "corporate_parent_url",
            sa.String(),
            nullable=True,
            comment=(
                "Corporate platform URL to scrape instead of the brand-front domain. "
                "e.g. https://www.greystar.com/properties/san-jose-ca/121-tasman/floorplans"
            ),
        ),
    )
    op.add_column(
        "scrape_site_registry",
        sa.Column(
            "corporate_platform",
            sa.String(32),
            nullable=True,
            comment="e.g. 'greystar', 'avalonbay', 'equity'",
        ),
    )
    op.add_column(
        "scrape_site_registry",
        sa.Column(
            "corporate_parent_set_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When corporate_parent_url was last set (for audit trail)",
        ),
    )
    op.add_column(
        "scrape_runs",
        sa.Column(
            "effective_url",
            sa.String(),
            nullable=True,
            comment=(
                "Actual URL scraped when a corporate_parent_url redirect fired. "
                "NULL when no redirect occurred (effective_url == url)."
            ),
        ),
    )


def downgrade():
    op.drop_column("scrape_runs", "effective_url")
    op.drop_column("scrape_site_registry", "corporate_parent_set_at")
    op.drop_column("scrape_site_registry", "corporate_platform")
    op.drop_column("scrape_site_registry", "corporate_parent_url")
