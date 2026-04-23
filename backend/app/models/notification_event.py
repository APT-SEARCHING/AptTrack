from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.sql import func

from app.db.base_class import Base


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id = Column(Integer, primary_key=True)

    # subscription_id is nullable so we can log channel-disable events where the
    # sub may have been deleted, or future system-level events with no sub.
    subscription_id = Column(
        Integer,
        ForeignKey("price_subscriptions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Denormalised for analytics queries that don't need to join PriceSubscription
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    sent_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # 'email' | 'telegram'
    channel = Column(String(16), nullable=False)

    # Lifecycle status — set to 'sent' at dispatch time; updated by webhook or
    # error handling later.
    # Values: 'sent' | 'failed' | 'bounced' | 'delivered' | 'opened' | 'clicked' | 'unsubscribed'
    status = Column(String(16), nullable=False, default="sent")

    # Provider-assigned message ID (SendGrid X-Message-Id or Telegram message_id integer).
    # Used to correlate incoming webhook events back to this row.
    external_id = Column(String, nullable=True, index=True)

    # What rule fired
    trigger_type = Column(String(32), nullable=True)   # 'target_price' | 'price_drop_pct'
    trigger_price = Column(Float, nullable=True)        # the price that crossed the threshold
    baseline_price = Column(Float, nullable=True)       # snapshot from sub at fire time

    subject = Column(String, nullable=True)             # email subject or first line of TG msg
    error_message = Column(String, nullable=True)       # failure detail when status='failed'

    __table_args__ = (
        # Efficient look-back queries per subscription
        Index("ix_notification_events_sub_sent", "subscription_id", "sent_at"),
        # Efficient aggregation / funnel queries across all events
        Index("ix_notification_events_status_sent", "status", "sent_at"),
    )
