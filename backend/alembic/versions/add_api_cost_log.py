"""Add api_cost_log table — persistent cost tracking replacing ephemeral JSONL file.

Revision ID: add_api_cost_log
Revises: add_apartment_current_special
Create Date: 2026-04-19 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "add_api_cost_log"
down_revision = "add_apartment_current_special"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "api_cost_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("input_tok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("api_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
    )
    op.create_index("idx_api_cost_log_ts", "api_cost_log", ["ts"])
    op.create_index("idx_api_cost_log_source_ts", "api_cost_log", ["source", "ts"])


def downgrade():
    op.drop_index("idx_api_cost_log_source_ts", table_name="api_cost_log")
    op.drop_index("idx_api_cost_log_ts", table_name="api_cost_log")
    op.drop_table("api_cost_log")
