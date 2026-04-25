"""Add units table, Plan.max_price, PriceSubscription.unit_id

Revision ID: add_units_table
Revises: plan_schema_update
Create Date: 2026-04-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "add_units_table"
down_revision = "add_registry_adapter_hint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_number", sa.String(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("area_sqft", sa.Float(), nullable=True),
        sa.Column("floor_level", sa.Integer(), nullable=True),
        sa.Column("facing", sa.String(), nullable=True),
        sa.Column("available_from", sa.DateTime(), nullable=True),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_units_plan_id", "units", ["plan_id"])

    op.add_column("plans", sa.Column("max_price", sa.Float(), nullable=True))

    op.add_column(
        "price_subscriptions",
        sa.Column(
            "unit_id",
            sa.Integer(),
            sa.ForeignKey("units.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("price_subscriptions", "unit_id")
    op.drop_column("plans", "max_price")
    op.drop_index("ix_units_plan_id", table_name="units")
    op.drop_table("units")
