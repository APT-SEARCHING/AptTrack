"""add data_source_type to scrape_site_registry and apartments

Revision ID: add_data_source_type
Revises: add_negative_scrape_cache
Create Date: 2026-04-23 00:00:00.000000

Allowed values:
  'brand_site'           default — scrape normally from the property's own website
  'corporate_parent'     label only; redirect already handled via corporate_parent_url
  'unscrapeable'         skip all scraping; UI shows "no pricing published"
  'aggregator_readonly'  reserved, not yet implemented
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_data_source_type"
down_revision = "add_negative_scrape_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scrape_site_registry",
        sa.Column(
            "data_source_type",
            sa.String(32),
            nullable=False,
            server_default="brand_site",
        ),
    )
    op.add_column(
        "apartments",
        sa.Column(
            "data_source_type",
            sa.String(32),
            nullable=False,
            server_default="brand_site",
        ),
    )


def downgrade() -> None:
    op.drop_column("apartments", "data_source_type")
    op.drop_column("scrape_site_registry", "data_source_type")
