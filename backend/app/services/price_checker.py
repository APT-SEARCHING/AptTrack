"""Price-drop checker.

``check_all_subscriptions(db)`` is called by the Celery beat task.
It queries every active PriceSubscription, computes the latest
relevant price, and fires notifications when thresholds are crossed.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.models.user import PriceSubscription, User
from app.services.notification import send_email_alert, send_telegram_alert

logger = logging.getLogger(__name__)

_DEBOUNCE_HOURS = 24  # minimum gap between repeated notifications


def check_all_subscriptions(db: Session) -> None:
    """Main entry point — iterate active subscriptions and notify if triggered."""
    subs = db.execute(
        select(PriceSubscription).where(PriceSubscription.is_active.is_(True))
    ).scalars().all()
    logger.info("Price checker: checking %d active subscription(s)", len(subs))

    for sub in subs:
        try:
            _check_subscription(sub, db)
        except Exception as exc:
            logger.error("Error checking subscription %d: %s", sub.id, exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_subscription(sub: PriceSubscription, db: Session) -> None:
    latest_price = _get_latest_price(sub, db)
    if latest_price is None:
        return

    # Fetch the immediately-previous price once; pass it into _is_triggered
    # so we don't double-query if both target_price and price_drop_pct are set.
    prev_price = _get_immediately_previous_price(sub, db)

    triggered, reason = _is_triggered(sub, latest_price, prev_price, db)
    if not triggered:
        return

    # Debounce: skip if we notified within the last 24 h
    if sub.last_notified_at is not None:
        last = sub.last_notified_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - last
        if age < timedelta(hours=_DEBOUNCE_HOURS):
            logger.debug("Subscription %d debounced (last notified %s ago)", sub.id, age)
            return

    # Build notification message
    apt_label = _apt_label(sub, db)
    subject = f"AptTrack: price drop alert for {apt_label}"
    body = (
        f"Hi,\n\n"
        f"A price drop was detected for {apt_label}.\n"
        f"Current price: ${latest_price:,.0f}/mo\n"
        f"Reason: {reason}\n\n"
        f"Log in to AptTrack to review your subscriptions.\n"
    )
    tg_msg = (
        f"*AptTrack price alert*\n"
        f"Property: {apt_label}\n"
        f"Current price: ${latest_price:,.0f}/mo\n"
        f"_{reason}_"
    )

    _send_notifications(sub, subject, body, tg_msg, db)

    # Auto-pause after firing so the same crossing doesn't re-notify every day.
    # User must re-activate manually to re-arm.
    sub.last_notified_at = datetime.now(timezone.utc)
    sub.is_active = False
    sub.trigger_count = (sub.trigger_count or 0) + 1
    db.commit()


def _get_latest_price(sub: PriceSubscription, db: Session) -> Optional[float]:
    """Return the most recent price relevant to this subscription."""
    if sub.plan_id is not None:
        price = db.execute(
            select(PlanPriceHistory.price)
            .where(PlanPriceHistory.plan_id == sub.plan_id)
            .order_by(PlanPriceHistory.recorded_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if price is not None:
            return price
        # Fallback to plan.price
        return db.execute(
            select(Plan.price).where(Plan.id == sub.plan_id)
        ).scalar_one_or_none()

    if sub.apartment_id is not None:
        return db.execute(
            select(func.min(Plan.price))
            .where(Plan.apartment_id == sub.apartment_id, Plan.is_available.is_(True))
        ).scalar_one_or_none()

    # Area-level: average price across matching plans
    stmt = (
        select(func.avg(Plan.price))
        .join(Apartment, Plan.apartment_id == Apartment.id)
        .where(Plan.is_available.is_(True))
    )
    if sub.city:
        stmt = stmt.where(func.lower(Apartment.city) == sub.city.lower())
    if sub.zipcode:
        stmt = stmt.where(Apartment.zipcode == sub.zipcode)
    if sub.min_bedrooms is not None:
        stmt = stmt.where(Plan.bedrooms >= sub.min_bedrooms)
    if sub.max_bedrooms is not None:
        stmt = stmt.where(Plan.bedrooms <= sub.max_bedrooms)
    return db.execute(stmt).scalar_one_or_none()


def _get_immediately_previous_price(sub: PriceSubscription, db: Session) -> Optional[float]:
    """Return the price immediately before the latest scrape for crossing detection.

    For plan-level subscriptions this is the second-most-recent PlanPriceHistory row.
    For apartment/area-level subscriptions we have no per-scrape aggregate history,
    so we fall back to baseline_price (captured at subscription-creation time), which
    is the best available reference for "was the price above the threshold before?"
    """
    if sub.plan_id is not None:
        rows = db.execute(
            select(PlanPriceHistory.price)
            .where(PlanPriceHistory.plan_id == sub.plan_id)
            .order_by(PlanPriceHistory.recorded_at.desc())
            .limit(2)
        ).all()
        return rows[1][0] if len(rows) >= 2 else None

    # apartment-level and area-level
    return sub.baseline_price


def _is_triggered(
    sub: PriceSubscription,
    latest_price: float,
    prev_price: Optional[float],
    db: Session,
) -> tuple:
    """Return (triggered: bool, reason: str).

    Bug #1 fix: target_price fires only on the ≥→< crossing, not on every
    run while price stays below target.
      - prev_price >= target AND latest < target  →  trigger (just crossed)
      - prev_price <  target AND latest < target  →  skip   (already below)
      - prev_price is None (no history)           →  trigger (treat as first crossing)
    """
    if sub.target_price is not None and latest_price < sub.target_price:
        if prev_price is None or prev_price >= sub.target_price:
            return (
                True,
                f"price ${latest_price:,.0f} dropped below target ${sub.target_price:,.0f}",
            )

    if sub.price_drop_pct is not None:
        prev = _get_previous_price(sub, db)  # Bug #2 will replace this with baseline
        if prev is not None and prev > 0:
            drop = (prev - latest_price) / prev * 100
            if drop >= sub.price_drop_pct:
                return (
                    True,
                    f"price dropped {drop:.1f}% (was ${prev:,.0f}, now ${latest_price:,.0f})",
                )

    return False, ""


def _get_previous_price(sub: PriceSubscription, db: Session) -> Optional[float]:
    """Return the second-most-recent price for percentage-drop calculation.

    NOTE: This is the pre-Bug-#2 baseline — it compares against the prior
    scrape rather than the subscription-time snapshot.  Bug #2 will replace
    this with sub.baseline_price.
    """
    if sub.plan_id is not None:
        rows = db.execute(
            select(PlanPriceHistory.price)
            .where(PlanPriceHistory.plan_id == sub.plan_id)
            .order_by(PlanPriceHistory.recorded_at.desc())
            .limit(2)
        ).all()
        return rows[1][0] if len(rows) >= 2 else None
    return None


def _apt_label(sub: PriceSubscription, db: Session) -> str:
    if sub.apartment_id is not None:
        title = db.execute(
            select(Apartment.title).where(Apartment.id == sub.apartment_id)
        ).scalar_one_or_none()
        return title if title else f"Apartment #{sub.apartment_id}"
    if sub.city:
        return sub.city
    return "tracked area"


def _send_notifications(
    sub: PriceSubscription,
    subject: str,
    body: str,
    tg_msg: str,
    db: Session,
) -> None:
    user = db.execute(
        select(User).where(User.id == sub.user_id)
    ).scalar_one_or_none()

    async def _run():
        coros = []
        if sub.notify_email and user and user.email:
            coros.append(send_email_alert(user.email, subject, body))
        if sub.notify_telegram and sub.telegram_chat_id:
            coros.append(send_telegram_alert(sub.telegram_chat_id, tg_msg))
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    asyncio.run(_run())
