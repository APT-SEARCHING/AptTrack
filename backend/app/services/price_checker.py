"""Price-drop checker.

``check_all_subscriptions(db)`` is called by the Celery beat task.
It queries every active PriceSubscription, computes the latest
relevant price, and fires notifications when thresholds are crossed.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.models.user import PriceSubscription, User
from app.services.notification import send_email_alert, send_telegram_alert

logger = logging.getLogger(__name__)

_DEBOUNCE_HOURS = 24  # minimum gap between repeated notifications


def check_all_subscriptions(db: Session) -> None:
    """Main entry point — iterate active subscriptions and notify if triggered."""
    subs = db.query(PriceSubscription).filter(PriceSubscription.is_active.is_(True)).all()
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

    triggered, reason = _is_triggered(sub, latest_price, db)
    if not triggered:
        return

    # Debounce: skip if we notified within the last 24 h
    if sub.last_notified_at is not None:
        age = datetime.now(timezone.utc) - sub.last_notified_at.replace(tzinfo=timezone.utc)
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

    # Fire notifications (fire-and-forget via asyncio)
    _send_notifications(sub, subject, body, tg_msg, db)

    # Update last_notified_at
    sub.last_notified_at = datetime.now(timezone.utc)
    db.commit()


def _get_latest_price(sub: PriceSubscription, db: Session) -> Optional[float]:
    """Return the most recent price relevant to this subscription."""
    if sub.plan_id is not None:
        row = (
            db.query(PlanPriceHistory.price)
            .filter(PlanPriceHistory.plan_id == sub.plan_id)
            .order_by(PlanPriceHistory.recorded_at.desc())
            .first()
        )
        if row:
            return row[0]
        # Fallback to plan.price
        plan = db.query(Plan.price).filter(Plan.id == sub.plan_id).first()
        return plan[0] if plan else None

    if sub.apartment_id is not None:
        # Cheapest available plan for this apartment
        row = (
            db.query(func.min(Plan.price))
            .filter(Plan.apartment_id == sub.apartment_id, Plan.is_available.is_(True))
            .first()
        )
        return row[0] if row and row[0] is not None else None

    # Area-level: average price across matching plans
    query = (
        db.query(func.avg(Plan.price))
        .join(Apartment, Plan.apartment_id == Apartment.id)
        .filter(Plan.is_available.is_(True))
    )
    if sub.city:
        query = query.filter(Apartment.city.ilike(f"%{sub.city}%"))
    if sub.zipcode:
        query = query.filter(Apartment.zipcode == sub.zipcode)
    if sub.min_bedrooms is not None:
        query = query.filter(Plan.bedrooms >= sub.min_bedrooms)
    if sub.max_bedrooms is not None:
        query = query.filter(Plan.bedrooms <= sub.max_bedrooms)
    row = query.first()
    return row[0] if row and row[0] is not None else None


def _is_triggered(
    sub: PriceSubscription, latest_price: float, db: Session
) -> tuple:
    """Return (triggered: bool, reason: str)."""
    if sub.target_price is not None and latest_price < sub.target_price:
        return True, f"price ${latest_price:,.0f} dropped below target ${sub.target_price:,.0f}"

    if sub.price_drop_pct is not None:
        prev = _get_previous_price(sub, db)
        if prev is not None and prev > 0:
            drop = (prev - latest_price) / prev * 100
            if drop >= sub.price_drop_pct:
                return True, f"price dropped {drop:.1f}% (was ${prev:,.0f}, now ${latest_price:,.0f})"

    return False, ""


def _get_previous_price(sub: PriceSubscription, db: Session) -> Optional[float]:
    """Return the second-most-recent price for percentage-drop calculation."""
    if sub.plan_id is not None:
        rows = (
            db.query(PlanPriceHistory.price)
            .filter(PlanPriceHistory.plan_id == sub.plan_id)
            .order_by(PlanPriceHistory.recorded_at.desc())
            .limit(2)
            .all()
        )
        return rows[1][0] if len(rows) >= 2 else None
    return None


def _apt_label(sub: PriceSubscription, db: Session) -> str:
    if sub.apartment_id is not None:
        apt = db.query(Apartment.title).filter(Apartment.id == sub.apartment_id).first()
        return apt[0] if apt else f"Apartment #{sub.apartment_id}"
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
    user = db.query(User).filter(User.id == sub.user_id).first()

    async def _run():
        coros = []
        if sub.notify_email and user and user.email:
            coros.append(send_email_alert(user.email, subject, body))
        if sub.notify_telegram and sub.telegram_chat_id:
            coros.append(send_telegram_alert(sub.telegram_chat_id, tg_msg))
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    # Celery workers run in a plain synchronous thread with no running event loop.
    # asyncio.run() creates a fresh loop, runs to completion, and tears it down —
    # guaranteeing the coroutines are actually awaited.  The old loop.create_task()
    # path was fire-and-forget: tasks were scheduled but never awaited, so
    # notifications were silently dropped.
    asyncio.run(_run())
