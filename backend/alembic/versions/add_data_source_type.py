"""add data_source_type to scrape_site_registry and apartments

Revision ID: add_data_source_type
Revises: add_negative_scrape_cache
Create Date: 2026-04-23 00:00:00.000000

Classifies each site/apartment as brand_site | corporate_parent |
unscrapeable | aggregator_readonly.  Worker skips scraping for
unscrapeable entries; frontend shows amber banner.
"""
import sqlalchemy as sa

from alembic import op

revision = "add_data_source_type"
down_revision = "add_negative_scrape_cache"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "scrape_site_registry",
        sa.Column(
            "data_source_type",
            sa.String(32),
            nullable=False,
            server_default="brand_site",
            comment=(
                "brand_site: scrape normally | "
                "corporate_parent: redirect via corporate_parent_url | "
                "unscrapeable: site doesn't publish pricing, skip all scraping | "
                "aggregator_readonly: reserved"
            ),
        ),
    )
    op.add_column(
        "apartments",
        sa.Column(
            "data_source_type",
            sa.String(32),
            nullable=False,
            server_default="brand_site",
            comment=(
                "brand_site: scrape normally | "
                "corporate_parent: redirect via corporate_parent_url | "
                "unscrapeable: site doesn't publish pricing, skip all scraping | "
                "aggregator_readonly: reserved"
            ),
        ),
    )


def downgrade():
    op.drop_column("apartments", "data_source_type")
    op.drop_column("scrape_site_registry", "data_source_type")
