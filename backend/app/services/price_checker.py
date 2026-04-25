"""Price-drop checker.

``check_all_subscriptions(db)`` is called by the Celery beat task.
It queries every active PriceSubscription, computes the latest
relevant price, and fires notifications when thresholds are crossed.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.apartment import Apartment, Plan, PlanPriceHistory, Unit
from app.models.notification_event import NotificationEvent
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

    triggered, reason = _is_triggered(sub, latest_price, prev_price)
    if not triggered:
        return

    # Debounce: skip if we notified within the last 24 h
    if sub.last_notified_at is not None:
        last = sub.last_notified_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)  # legacy naive rows — assume UTC
        else:
            last = last.astimezone(timezone.utc)  # normalise any non-UTC aware tz
        age = datetime.now(timezone.utc) - last
        if age < timedelta(hours=_DEBOUNCE_HOURS):
            logger.debug("Subscription %d debounced (last notified %s ago)", sub.id, age)
            return

    ctx = _render_alert_context(sub, latest_price, db)
    subject = _build_subject(ctx, sub)
    body = _build_body_plaintext(ctx, sub)
    tg_msg = _build_telegram_msg(ctx, sub)

    _send_notifications(sub, subject, body, tg_msg, latest_price, reason, db)

    # Auto-pause after firing so the same crossing doesn't re-notify every day.
    # User must re-activate manually to re-arm.
    sub.last_notified_at = datetime.now(timezone.utc)
    sub.is_active = False
    sub.trigger_count = (sub.trigger_count or 0) + 1
    db.commit()


def _get_latest_price(sub: PriceSubscription, db: Session) -> Optional[float]:
    """Return the most recent price relevant to this subscription."""
    if sub.unit_id is not None:
        # Unit-level: use the unit's current price directly
        return db.execute(
            select(Unit.price).where(Unit.id == sub.unit_id, Unit.is_available.is_(True))
        ).scalar_one_or_none()

    if sub.plan_id is not None:
        # Only use recorded price history — Plan.price is a stale seed column
        # and could trigger false alerts. Return None if no history yet.
        return db.execute(
            select(PlanPriceHistory.price)
            .where(PlanPriceHistory.plan_id == sub.plan_id)
            .order_by(PlanPriceHistory.recorded_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    if sub.apartment_id is not None:
        # Use current_price (set by scraper) — Plan.price is a deprecated seed column
        return db.execute(
            select(func.min(Plan.current_price))
            .where(
                Plan.apartment_id == sub.apartment_id,
                Plan.is_available.is_(True),
                Plan.current_price.isnot(None),
            )
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
    if sub.unit_id is not None:
        # For unit-level subs, use baseline_price as previous (no Unit price history)
        return sub.baseline_price

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
) -> tuple:
    """Return (triggered: bool, reason: str).

    target_price (Bug #1): fires only on the ≥→< crossing.
      - prev_price >= target AND latest < target  →  trigger (just crossed)
      - prev_price <  target AND latest < target  →  skip   (already below)
      - prev_price is None (no history)           →  trigger (treat as first crossing)

    price_drop_pct (Bug #2): anchored to sub.baseline_price (subscription-time
    snapshot), not the previous scrape.  Fires when the cumulative drop from
    baseline reaches the threshold.
      - baseline_price is None                    →  skip with warning (no anchor)
      - drop = (baseline - latest) / baseline * 100
      - pct=0 triggers whenever latest_price <= baseline_price (any drop)
    """
    if sub.target_price is not None and latest_price < sub.target_price:
        if prev_price is None or prev_price >= sub.target_price:
            return (
                True,
                f"price ${latest_price:,.0f} dropped below target ${sub.target_price:,.0f}",
            )

    if sub.price_drop_pct is not None:
        if sub.baseline_price is None:
            logger.warning(
                "Subscription %d has price_drop_pct but no baseline_price — skipping",
                sub.id,
            )
        else:
            drop = (sub.baseline_price - latest_price) / sub.baseline_price * 100
            if drop >= sub.price_drop_pct:
                date_str = ""
                if sub.baseline_recorded_at is not None:
                    date_str = f" ({sub.baseline_recorded_at.strftime('%b %-d')})"
                return (
                    True,
                    f"price dropped {drop:.1f}% — was ${sub.baseline_price:,.0f} when you"
                    f" subscribed{date_str}, now ${latest_price:,.0f}",
                )

    return False, ""


# ---------------------------------------------------------------------------
# Notification content
# ---------------------------------------------------------------------------

def _render_alert_context(
    sub: PriceSubscription,
    latest_price: float,
    db: Session,
) -> Dict[str, Any]:
    """Gather all displayable fields for a price-drop notification."""
    from app.core.config import settings

    ctx: Dict[str, Any] = {
        "now_price": latest_price,
        "was_price": sub.baseline_price,
        "was_date": None,
        "drop_pct": None,
        "apartment_title": "your tracked property",
        "apartment_id": None,
        "apartment_url_internal": None,
        "apartment_url_external": None,
        "city_state": None,
        "plan_name": None,
        "plan_spec": None,
        "unit_number": None,
        "thirty_day_low": None,
        "unsub_url": None,
        "unsub_all_url": None,
        "alerts_url": f"{settings.APP_BASE_URL}/alerts",
    }

    # Cumulative drop percentage from baseline
    if sub.baseline_price:
        ctx["drop_pct"] = (sub.baseline_price - latest_price) / sub.baseline_price * 100

    # Baseline capture date
    if sub.baseline_recorded_at:
        ctx["was_date"] = sub.baseline_recorded_at.strftime("%b %-d")

    # Unsubscribe links (use stored tokens; fall back gracefully if not yet set)
    if sub.unsubscribe_token:
        ctx["unsub_url"] = f"{settings.APP_BASE_URL}/unsubscribe/{sub.unsubscribe_token}"

    # "Unsubscribe from all alerts" — requires fetching the user's token
    user = db.execute(select(User).where(User.id == sub.user_id)).scalar_one_or_none()
    if user and user.unsubscribe_all_token:
        ctx["unsub_all_url"] = (
            f"{settings.APP_BASE_URL}/unsubscribe/all/{user.unsubscribe_all_token}"
        )

    # Resolve unit (for unit-level subscriptions)
    if sub.unit_id is not None:
        unit = db.execute(select(Unit).where(Unit.id == sub.unit_id)).scalar_one_or_none()
        if unit:
            ctx["unit_number"] = unit.unit_number
            # derive plan + apartment from unit
            plan = db.execute(select(Plan).where(Plan.id == unit.plan_id)).scalar_one_or_none()
            if plan:
                ctx["plan_name"] = plan.name
                ctx["plan_spec"] = _fmt_plan_spec(plan)
                apt_from_plan = db.execute(
                    select(Apartment).where(Apartment.id == plan.apartment_id)
                ).scalar_one_or_none()
                if apt_from_plan:
                    ctx["apartment_title"] = apt_from_plan.title
                    ctx["apartment_id"] = apt_from_plan.id
                    ctx["apartment_url_internal"] = f"{settings.APP_BASE_URL}/apartments/{apt_from_plan.id}"
                    ctx["apartment_url_external"] = apt_from_plan.source_url or None
                    if apt_from_plan.city and apt_from_plan.state:
                        ctx["city_state"] = f"{apt_from_plan.city}, {apt_from_plan.state}"
        return ctx

    # Resolve apartment
    apt: Optional[Apartment] = None
    if sub.apartment_id is not None:
        apt = db.execute(
            select(Apartment).where(Apartment.id == sub.apartment_id)
        ).scalar_one_or_none()
    elif sub.plan_id is not None:
        apt = db.execute(
            select(Apartment)
            .join(Plan, Plan.apartment_id == Apartment.id)
            .where(Plan.id == sub.plan_id)
        ).scalar_one_or_none()

    if apt:
        ctx["apartment_title"] = apt.title
        ctx["apartment_id"] = apt.id
        ctx["apartment_url_internal"] = f"{settings.APP_BASE_URL}/apartments/{apt.id}"
        ctx["apartment_url_external"] = apt.source_url or None
        if apt.city and apt.state:
            ctx["city_state"] = f"{apt.city}, {apt.state}"

    # Resolve plan details
    if sub.plan_id is not None:
        plan = db.execute(
            select(Plan).where(Plan.id == sub.plan_id)
        ).scalar_one_or_none()
        if plan:
            ctx["plan_name"] = plan.name
            ctx["plan_spec"] = _fmt_plan_spec(plan)

            ctx["thirty_day_low"] = db.execute(
                select(func.min(PlanPriceHistory.price))
                .where(
                    PlanPriceHistory.plan_id == sub.plan_id,
                    PlanPriceHistory.recorded_at >= datetime.now(timezone.utc) - timedelta(days=30),
                )
            ).scalar_one_or_none()

    elif sub.apartment_id is not None:
        # 30-day low across all available plans for this apartment
        ctx["thirty_day_low"] = db.execute(
            select(func.min(PlanPriceHistory.price))
            .join(Plan, PlanPriceHistory.plan_id == Plan.id)
            .where(
                Plan.apartment_id == sub.apartment_id,
                PlanPriceHistory.recorded_at >= datetime.now(timezone.utc) - timedelta(days=30),
            )
        ).scalar_one_or_none()

    return ctx


def _fmt_plan_spec(plan: Plan) -> Optional[str]:
    """Format '1 bed / 1 bath / 520 sqft' from a Plan row."""
    parts = []
    if plan.bedrooms is not None:
        if plan.bedrooms == 0:
            parts.append("Studio")
        else:
            b = int(plan.bedrooms) if plan.bedrooms == int(plan.bedrooms) else plan.bedrooms
            parts.append(f"{b} bed")
    if plan.bathrooms is not None:
        ba = int(plan.bathrooms) if plan.bathrooms == int(plan.bathrooms) else plan.bathrooms
        parts.append(f"{ba} bath")
    if plan.area_sqft:
        parts.append(f"{int(plan.area_sqft):,} sqft")
    return " / ".join(parts) if parts else None


def _build_subject(ctx: Dict[str, Any], sub: PriceSubscription) -> str:
    title = ctx["apartment_title"]
    now = ctx["now_price"]
    if ctx["drop_pct"] is not None and ctx["drop_pct"] > 0 and ctx["was_price"]:
        return (
            f"\U0001f514 {title} dropped to ${now:,.0f}/mo"
            f" (\u2212{ctx['drop_pct']:.1f}% from ${ctx['was_price']:,.0f})"
        )
    if sub.target_price is not None:
        return (
            f"\U0001f514 {title} now below your ${sub.target_price:,.0f} target"
            f" (${now:,.0f}/mo)"
        )
    return f"\U0001f514 Price drop alert: {title} (${now:,.0f}/mo)"


def _build_body_plaintext(ctx: Dict[str, Any], sub: PriceSubscription) -> str:
    title = ctx["apartment_title"]
    now = ctx["now_price"]
    was = ctx["was_price"]
    drop_pct = ctx["drop_pct"]

    # Opening line
    if drop_pct is not None and drop_pct > 0 and was:
        open_line = (
            f"{ctx['plan_name'] or title} dropped from ${was:,.0f} to ${now:,.0f}/mo"
            f" (\u2212{drop_pct:.1f}%)."
        )
    elif sub.target_price is not None:
        open_line = (
            f"{title} is now ${now:,.0f}/mo \u2014 below your ${sub.target_price:,.0f} target."
        )
    else:
        open_line = f"{title} has a new price: ${now:,.0f}/mo."

    # Property / plan block
    location = ctx["city_state"] or ""
    prop_line = f"  Property  : {title}" + (f" \u00b7 {location}" if location else "")

    spec_line = ""
    if ctx["plan_name"]:
        spec = ctx["plan_spec"] or ""
        spec_line = f"  Plan      : {ctx['plan_name']}" + (f" \u00b7 {spec}" if spec else "")

    was_line = ""
    if was:
        was_str = f"${was:,.0f}/mo"
        if ctx["was_date"]:
            was_str += f" (your baseline, {ctx['was_date']})"
        was_line = f"  Was       : {was_str}"

    now_line = f"  Now       : ${now:,.0f}/mo"

    low_line = ""
    if ctx["thirty_day_low"] is not None:
        low_line = f"  30-day low: ${ctx['thirty_day_low']:,.0f}/mo"

    detail_lines = "\n".join(
        line for line in [prop_line, spec_line, was_line, now_line, low_line] if line
    )

    # CTA links
    cta_parts = []
    if ctx["apartment_url_internal"]:
        cta_parts.append(f"  View in AptTrack  \u2192 {ctx['apartment_url_internal']}")
    if ctx["apartment_url_external"]:
        cta_parts.append(f"  Official listing  \u2192 {ctx['apartment_url_external']}")
    cta_block = "\n".join(cta_parts)

    # Why + pause note
    if drop_pct is not None and drop_pct > 0 and was:
        why = (
            f"Why you got this: price dropped {drop_pct:.1f}% from your"
            f" ${was:,.0f} baseline"
            + (f" (set {ctx['was_date']})" if ctx["was_date"] else "")
            + "."
        )
    elif sub.target_price is not None:
        why = f"Why you got this: price crossed below your ${sub.target_price:,.0f} target."
    else:
        why = "Why you got this: a price drop matched your alert settings."

    pause_note = (
        "We've paused this alert so you won't get duplicate notifications.\n"
        f"To re-arm it, visit AptTrack Alerts: {ctx['alerts_url']}"
    )

    sep = "\u2500" * 54

    sections = [
        f"Price drop alert \u2014 {title}",
        "=" * (len(f"Price drop alert \u2014 {title}")),
        "",
        open_line,
        "",
        detail_lines,
    ]
    if cta_block:
        sections += ["", cta_block]
    sections += [
        "",
        sep,
        why,
        "",
        pause_note,
    ]
    unsub_lines = []
    if ctx["unsub_url"]:
        unsub_lines.append(f"Unsubscribe from this alert:\n  \u2192 {ctx['unsub_url']}")
    if ctx["unsub_all_url"]:
        unsub_lines.append(f"Unsubscribe from all AptTrack alerts:\n  \u2192 {ctx['unsub_all_url']}")
    if unsub_lines:
        sections += [""] + unsub_lines
    sections += [
        sep,
        "AptTrack \u00b7 Bay Area rental price transparency",
    ]

    return "\n".join(sections)


def _build_telegram_msg(ctx: Dict[str, Any], sub: PriceSubscription) -> str:
    title = ctx["apartment_title"]
    now = ctx["now_price"]
    was = ctx["was_price"]
    drop_pct = ctx["drop_pct"]

    # Headline
    if drop_pct is not None and drop_pct > 0 and was:
        headline = (
            f"\U0001f514 *{title}* dropped to ${now:,.0f}/mo"
            f" (\u2212{drop_pct:.1f}%)"
        )
    elif sub.target_price is not None:
        headline = (
            f"\U0001f514 *{title}* now below ${sub.target_price:,.0f} target"
            f" (${now:,.0f}/mo)"
        )
    else:
        headline = f"\U0001f514 *{title}* new price: ${now:,.0f}/mo"

    # Detail line
    detail_parts = []
    if ctx["plan_spec"]:
        detail_parts.append(ctx["plan_spec"])
    if ctx["city_state"]:
        detail_parts.append(ctx["city_state"])
    detail_line = "\U0001f4cb " + " \u00b7 ".join(detail_parts) if detail_parts else ""

    # Price line
    price_parts = []
    if was:
        was_str = f"Was ${was:,.0f}"
        if ctx["was_date"]:
            was_str += f" ({ctx['was_date']})"
        price_parts.append(was_str)
    price_parts.append(f"now ${now:,.0f}")
    if ctx["thirty_day_low"] is not None:
        price_parts.append(f"30d low ${ctx['thirty_day_low']:,.0f}")
    price_line = "\U0001f4c9 " + " \u2192 ".join(price_parts[:2])
    if ctx["thirty_day_low"] is not None:
        price_line += f" \u00b7 {price_parts[-1]}"

    # Links
    link_parts = []
    if ctx["apartment_url_internal"]:
        link_parts.append(f"[AptTrack]({ctx['apartment_url_internal']})")
    if ctx["apartment_url_external"]:
        link_parts.append(f"[Official listing]({ctx['apartment_url_external']})")
    links_line = " \u00b7 ".join(link_parts) if link_parts else ""

    pause_note = "_Alert paused. Re-arm at AptTrack Alerts._"

    lines = [headline]
    if detail_line:
        lines.append(detail_line)
    lines.append(price_line)
    if links_line:
        lines.append("")
        lines.append(links_line)
    lines += ["", pause_note]

    return "\n".join(lines)


def _send_notifications(
    sub: PriceSubscription,
    subject: str,
    body: str,
    tg_msg: str,
    trigger_price: float,
    trigger_reason: str,
    db: Session,
) -> None:
    """Dispatch notifications and persist a NotificationEvent row for each channel."""
    user = db.execute(
        select(User).where(User.id == sub.user_id)
    ).scalar_one_or_none()

    # Resolve trigger_type from the reason string produced by _is_triggered
    trigger_type: Optional[str] = None
    if "target" in trigger_reason:
        trigger_type = "target_price"
    elif "%" in trigger_reason:
        trigger_type = "price_drop_pct"

    async def _run():
        tasks = []
        labels = []
        if sub.notify_email and user and user.email:
            tasks.append(send_email_alert(user.email, subject, body))
            labels.append("email")
        if sub.notify_telegram and sub.telegram_chat_id:
            tasks.append(send_telegram_alert(sub.telegram_chat_id, tg_msg))
            labels.append("telegram")
        if not tasks:
            return []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return list(zip(labels, results))

    pairs = asyncio.run(_run())

    for channel, result in pairs:
        # result is either the (external_id, status, is_403) tuple or an Exception
        if isinstance(result, Exception):
            external_id, status, is_403 = None, "failed", False
            err_msg = str(result)
        else:
            external_id, status, is_403 = result
            err_msg = None

        db.add(NotificationEvent(
            subscription_id=sub.id,
            user_id=sub.user_id,
            channel=channel,
            status=status,
            external_id=external_id,
            trigger_type=trigger_type,
            trigger_price=trigger_price,
            baseline_price=sub.baseline_price,
            subject=subject if channel == "email" else tg_msg[:200],
            error_message=err_msg,
        ))

        # 403 = user blocked the bot; disable the channel so we stop spamming
        if is_403 and channel == "telegram":
            sub.notify_telegram = False
            logger.warning(
                "Disabled telegram notifications for subscription %d (bot blocked)", sub.id
            )

    db.commit()
