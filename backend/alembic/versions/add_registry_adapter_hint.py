"""Add last_successful_adapter hint columns to scrape_site_registry.

Revision ID: add_registry_adapter_hint
Revises: add_scrape_run_adapter_name
Create Date: 2026-04-23

Records which platform adapter last succeeded for a domain so the scrape
loop can try that adapter first on the next run, skipping the full 10-adapter
registry walk on warm sites.
"""
from alembic import op
import sqlalchemy as sa

revision = "add_registry_adapter_hint"
down_revision = "add_scrape_run_adapter_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scrape_site_registry",
        sa.Column("last_successful_adapter", sa.String(32), nullable=True,
                  comment="Name of the platform adapter that last successfully extracted units for this domain"),
    )
    op.add_column(
        "scrape_site_registry",
        sa.Column("last_adapter_success_at", sa.DateTime(timezone=True), nullable=True,
                  comment="Timestamp of the last successful adapter extraction"),
    )


def downgrade() -> None:
    op.drop_column("scrape_site_registry", "last_adapter_success_at")
    op.drop_column("scrape_site_registry", "last_successful_adapter")
