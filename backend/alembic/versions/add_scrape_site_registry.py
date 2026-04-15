"""Add scrape_site_registry table for compliance tracking

Revision ID: add_scrape_site_registry
Revises: add_city_index
Create Date: 2026-04-15 00:00:01.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "add_scrape_site_registry"
down_revision = "add_city_index"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scrape_site_registry",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("domain", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("robots_txt_allows", sa.Boolean(), nullable=True),
        sa.Column("robots_txt_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("robots_txt_raw", sa.Text(), nullable=True),
        sa.Column("tos_url", sa.String(), nullable=True),
        sa.Column("tos_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tos_allows_scraping", sa.Boolean(), nullable=True),
        sa.Column("tos_notes", sa.Text(), nullable=True),
        sa.Column("platform", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("ceased_reason", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_table("scrape_site_registry")
