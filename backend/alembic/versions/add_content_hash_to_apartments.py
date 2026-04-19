"""Add last_content_hash and last_scraped_at to apartments

Merges the two open heads (add_scrape_site_registry, patch_apartments_missing_cols)
and adds content-hash short-circuit columns.

Revision ID: add_content_hash_apartments
Revises: add_scrape_site_registry, patch_apartments_missing_cols
Create Date: 2026-04-16 00:00:01.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "add_content_hash_apartments"
down_revision = ("add_scrape_site_registry", "patch_apartments_missing_cols")
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("apartments")}

    if "last_content_hash" not in existing:
        op.add_column(
            "apartments",
            sa.Column(
                "last_content_hash",
                sa.String(64),
                nullable=True,
                comment="SHA256 of stripped HTML from last fetch — skip scrape when unchanged",
            ),
        )
    if "last_scraped_at" not in existing:
        op.add_column(
            "apartments",
            sa.Column(
                "last_scraped_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="When last_content_hash was last computed",
            ),
        )


def downgrade():
    op.drop_column("apartments", "last_scraped_at")
    op.drop_column("apartments", "last_content_hash")
