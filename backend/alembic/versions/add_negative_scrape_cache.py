"""add negative_scrape_cache table

Revision ID: add_negative_scrape_cache
Revises: add_corporate_parent_columns
Create Date: 2026-04-22 00:00:00.000000

Suppression table for URLs that consistently return no data.
Exponential backoff: 7d → 14d → 30d (capped).
"""
import sqlalchemy as sa

from alembic import op

revision = "add_negative_scrape_cache"
down_revision = "add_corporate_parent_columns"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "negative_scrape_cache",
        sa.Column("url", sa.String(), nullable=False,
                  comment="Apartment's registered URL (original_url)"),
        sa.Column("first_failed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("last_failed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("last_reason", sa.String(32), nullable=False,
                  comment="validated_fail | hard_fail"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("url"),
    )
    op.create_index(
        "ix_negative_scrape_cache_retry_after",
        "negative_scrape_cache",
        ["retry_after", "attempt_count"],
    )


def downgrade():
    op.drop_index("ix_negative_scrape_cache_retry_after",
                  table_name="negative_scrape_cache")
    op.drop_table("negative_scrape_cache")
