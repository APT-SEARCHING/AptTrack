"""Add scrape_runs table for cost/quality observability

Revision ID: add_scrape_run_table
Revises: add_content_hash_apartments
Create Date: 2026-04-16 00:00:02.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "add_scrape_run_table"
down_revision = "add_content_hash_apartments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "apartment_id",
            sa.Integer(),
            sa.ForeignKey("apartments.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("path_cache_hit", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("content_hash_short_circuit", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("iterations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("elapsed_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_scrape_runs_apt_run_at", "scrape_runs", ["apartment_id", "run_at"])
    op.create_index("ix_scrape_runs_outcome_run_at", "scrape_runs", ["outcome", "run_at"])


def downgrade():
    op.drop_index("ix_scrape_runs_outcome_run_at", table_name="scrape_runs")
    op.drop_index("ix_scrape_runs_apt_run_at", table_name="scrape_runs")
    op.drop_table("scrape_runs")
