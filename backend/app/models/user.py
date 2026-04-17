from app.db.base_class import Base
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    subscriptions = relationship(
        "PriceSubscription",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class PriceSubscription(Base):
    __tablename__ = "price_subscriptions"

    id = Column(Integer, primary_key=True, index=True)

    # Owner
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Optional target: specific apartment and/or plan
    apartment_id = Column(Integer, ForeignKey("apartments.id", ondelete="CASCADE"), nullable=True)
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=True)

    # Area-level subscription (used when apartment_id/plan_id are null)
    city = Column(String, nullable=True)
    zipcode = Column(String(10), nullable=True)
    min_bedrooms = Column(Float, nullable=True)
    max_bedrooms = Column(Float, nullable=True)

    # Alert thresholds (at least one should be set)
    target_price = Column(Float, nullable=True, comment="Alert when price drops below this value")
    price_drop_pct = Column(Float, nullable=True, comment="Alert when price drops by this percentage")

    # Notification channels
    notify_email = Column(Boolean, default=True, nullable=False)
    notify_telegram = Column(Boolean, default=False, nullable=False)
    telegram_chat_id = Column(String, nullable=True)

    # Baseline price — captured at subscription-creation time.
    # Used as denominator for price_drop_pct and as the "last known price
    # above target" seed for target_price crossing detection.
    baseline_price = Column(Float, nullable=True,
        comment="Price at subscription-creation time")
    baseline_recorded_at = Column(DateTime(timezone=True), nullable=True,
        comment="When baseline_price was captured")

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    last_notified_at = Column(DateTime(timezone=True), nullable=True)
    trigger_count = Column(Integer, default=0, nullable=False,
        comment="Number of times a notification has been fired for this subscription")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="subscriptions")
    apartment = relationship("Apartment")
    plan = relationship("Plan")
