"""add adapter_name column to scrape_runs

Revision ID: add_scrape_run_adapter_name
Revises: add_data_source_type
Create Date: 2026-04-23 00:00:00.000000

Records which platform adapter short-circuited a scrape when
outcome = 'platform_direct'.  NULL for all other outcomes.
Powers dev/coverage_report.py per-adapter observability.
"""
import sqlalchemy as sa

from alembic import op

revision = "add_scrape_run_adapter_name"
down_revision = "add_data_source_type"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "scrape_runs",
        sa.Column(
            "adapter_name",
            sa.String(32),
            nullable=True,
            comment="Platform adapter that handled this scrape, e.g. 'sightmap'. NULL unless outcome='platform_direct'.",
        ),
    )


def downgrade():
    op.drop_column("scrape_runs", "adapter_name")
