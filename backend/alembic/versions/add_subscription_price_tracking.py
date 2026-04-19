"""Add baseline_price and baseline_recorded_at to price_subscriptions.

Revision ID: add_subscription_price_tracking
Revises: alter_plan_price_nullable
Create Date: 2026-04-17
"""

import sqlalchemy as sa

from alembic import op

revision = "add_subscription_price_tracking"
down_revision = "alter_plan_price_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add columns ────────────────────────────────────────────────────────
    op.add_column(
        "price_subscriptions",
        sa.Column("baseline_price", sa.Float(), nullable=True,
                  comment="Price at subscription-creation time"),
    )
    op.add_column(
        "price_subscriptions",
        sa.Column("baseline_recorded_at", sa.DateTime(timezone=True), nullable=True,
                  comment="When baseline_price was captured"),
    )

    # ── 2. Backfill: plan-level subscriptions ─────────────────────────────────
    # Use latest PlanPriceHistory price; fall back to Plan.price if no history.
    op.execute("""
        UPDATE price_subscriptions ps
        SET
            baseline_price = COALESCE(
                (
                    SELECT pph.price
                    FROM plan_price_history pph
                    WHERE pph.plan_id = ps.plan_id
                    ORDER BY pph.recorded_at DESC
                    LIMIT 1
                ),
                (SELECT p.price FROM plans p WHERE p.id = ps.plan_id)
            ),
            baseline_recorded_at = ps.created_at
        WHERE ps.plan_id IS NOT NULL
    """)

    # ── 3. Backfill: apartment-level subscriptions ────────────────────────────
    # Use the minimum available plan price for the target apartment.
    op.execute("""
        UPDATE price_subscriptions ps
        SET
            baseline_price = (
                SELECT MIN(p.price)
                FROM plans p
                WHERE p.apartment_id = ps.apartment_id
                  AND p.is_available = TRUE
                  AND p.price IS NOT NULL
            ),
            baseline_recorded_at = ps.created_at
        WHERE ps.plan_id IS NULL
          AND ps.apartment_id IS NOT NULL
    """)

    # ── 4. Backfill: area-level subscriptions ─────────────────────────────────
    # Use average price across all matching available plans.
    op.execute("""
        UPDATE price_subscriptions ps
        SET
            baseline_price = (
                SELECT AVG(p.price)
                FROM plans p
                JOIN apartments a ON p.apartment_id = a.id
                WHERE p.is_available = TRUE
                  AND p.price IS NOT NULL
                  AND (ps.city IS NULL OR LOWER(a.city) = LOWER(ps.city))
                  AND (ps.zipcode IS NULL OR a.zipcode = ps.zipcode)
                  AND (ps.min_bedrooms IS NULL OR p.bedrooms >= ps.min_bedrooms)
                  AND (ps.max_bedrooms IS NULL OR p.bedrooms <= ps.max_bedrooms)
            ),
            baseline_recorded_at = ps.created_at
        WHERE ps.plan_id IS NULL
          AND ps.apartment_id IS NULL
    """)


def downgrade() -> None:
    op.drop_column("price_subscriptions", "baseline_recorded_at")
    op.drop_column("price_subscriptions", "baseline_price")
