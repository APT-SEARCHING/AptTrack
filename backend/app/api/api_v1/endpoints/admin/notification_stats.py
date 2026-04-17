"""GET /admin/notifications/stats — aggregate NotificationEvent data.

Returns delivery funnel (sent → delivered → opened → clicked) and failure
metrics per channel for the requested look-back window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.notification_event import NotificationEvent

router = APIRouter()


class ChannelStats(BaseModel):
    sent: int
    failed: int
    delivered: int
    opened: int
    clicked: int
    bounced: int
    unsubscribed: int
    # Rates expressed as fractions (0–1); None if denominator is 0
    delivery_rate: Optional[float]
    open_rate: Optional[float]
    click_rate: Optional[float]
    bounce_rate: Optional[float]


class NotificationStatsResponse(BaseModel):
    period_days: int
    total_events: int
    by_channel: Dict[str, ChannelStats]


@router.get(
    "/admin/notifications/stats",
    response_model=NotificationStatsResponse,
    tags=["admin"],
    summary="Notification delivery funnel metrics for the last N days (admin only)",
)
def get_notification_stats(
    days: int = Query(default=7, ge=1, le=90, description="Look-back window in days"),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> NotificationStatsResponse:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # One aggregate query: count per (channel, status)
    rows = db.execute(
        select(
            NotificationEvent.channel,
            NotificationEvent.status,
            func.count(NotificationEvent.id).label("cnt"),
        )
        .where(NotificationEvent.sent_at >= since)
        .group_by(NotificationEvent.channel, NotificationEvent.status)
    ).all()

    # Pivot into {channel: {status: count}}
    pivot: Dict[str, Dict[str, int]] = {}
    for channel, status, cnt in rows:
        pivot.setdefault(channel, {})[status] = cnt

    def _rate(num: int, denom: int) -> Optional[float]:
        return round(num / denom, 4) if denom > 0 else None

    by_channel: Dict[str, ChannelStats] = {}
    for channel, counts in pivot.items():
        sent = counts.get("sent", 0)
        failed = counts.get("failed", 0)
        delivered = counts.get("delivered", 0)
        opened = counts.get("opened", 0)
        clicked = counts.get("clicked", 0)
        bounced = counts.get("bounced", 0)
        unsubscribed = counts.get("unsubscribed", 0)

        attempted = sent + failed + delivered + opened + clicked + bounced + unsubscribed
        # Delivered + all downstream events = successful delivery
        delivered_total = delivered + opened + clicked + unsubscribed

        by_channel[channel] = ChannelStats(
            sent=sent,
            failed=failed,
            delivered=delivered,
            opened=opened,
            clicked=clicked,
            bounced=bounced,
            unsubscribed=unsubscribed,
            delivery_rate=_rate(delivered_total, attempted - failed),
            open_rate=_rate(opened + clicked, delivered_total) if delivered_total else None,
            click_rate=_rate(clicked, opened + clicked) if (opened + clicked) else None,
            bounce_rate=_rate(bounced, attempted),
        )

    total = sum(sum(counts.values()) for counts in pivot.values())
    return NotificationStatsResponse(
        period_days=days,
        total_events=total,
        by_channel=by_channel,
    )
