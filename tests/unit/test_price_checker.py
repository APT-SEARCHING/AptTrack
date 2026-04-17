"""Unit tests for backend/app/services/price_checker.py.

Uses an in-memory SQLite database; _send_notifications is patched out so no
real email/Telegram calls are made.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.base  # noqa: F401 — registers all models with Base.metadata
from app.core.security import hash_password
from app.db.base_class import Base
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.models.user import PriceSubscription, User
from app.services.price_checker import _check_subscription, check_all_subscriptions


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _make_user(db: Session) -> User:
    user = User(
        email="checker@test.example",
        hashed_password=hash_password("password123"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _make_plan(db: Session, price: float = 3000.0) -> tuple:
    """Create Apartment + Plan; return (apartment_id, plan_id)."""
    apt = Apartment(
        title="Checker Test Apts", city="San Jose", state="CA",
        zipcode="95110", property_type="apartment", is_available=True,
    )
    db.add(apt)
    db.flush()
    plan = Plan(
        apartment_id=apt.id, name="1BR", bedrooms=1, bathrooms=1,
        area_sqft=600, price=price, is_available=True,
    )
    db.add(plan)
    db.flush()
    return apt.id, plan.id


def _add_history(db: Session, plan_id: int, prices: list) -> None:
    """Insert PlanPriceHistory; prices[0] is most recent, prices[-1] is oldest."""
    now = datetime.now(timezone.utc)
    for i, price in enumerate(prices):
        db.add(PlanPriceHistory(
            plan_id=plan_id,
            price=price,
            recorded_at=now - timedelta(days=i),
        ))
    db.flush()


def _make_sub(
    db: Session,
    user_id: int,
    plan_id: int,
    *,
    target_price: float | None = None,
    price_drop_pct: float | None = None,
    baseline_price: float | None = None,
) -> PriceSubscription:
    sub = PriceSubscription(
        user_id=user_id,
        plan_id=plan_id,
        target_price=target_price,
        price_drop_pct=price_drop_pct,
        baseline_price=baseline_price,
        notify_email=True,
        notify_telegram=False,
        is_active=True,
        trigger_count=0,
    )
    db.add(sub)
    db.flush()
    return sub


# ---------------------------------------------------------------------------
# Bug #1: target_price crossing detection
# ---------------------------------------------------------------------------

class TestTargetPriceCrossing:

    def test_first_crossing_triggers_and_pauses(self, db: Session):
        """Price crosses ≥→< threshold for the first time: must trigger and
        set is_active=False (auto-pause)."""
        user = _make_user(db)
        _, plan_id = _make_plan(db)
        # History: was $3200 (above target), now $2800 (below target)
        _add_history(db, plan_id, prices=[2800.0, 3200.0])
        sub = _make_sub(db, user.id, plan_id, target_price=3000.0, baseline_price=3200.0)

        with patch("app.services.price_checker._send_notifications"):
            _check_subscription(sub, db)

        assert sub.is_active is False
        assert sub.trigger_count == 1
        assert sub.last_notified_at is not None

    def test_already_below_does_not_trigger(self, db: Session):
        """Price was already below target before this scrape: must NOT trigger."""
        user = _make_user(db)
        _, plan_id = _make_plan(db)
        # History: was $2900 (already below $3000), now $2800 (still below)
        _add_history(db, plan_id, prices=[2800.0, 2900.0])
        sub = _make_sub(db, user.id, plan_id, target_price=3000.0, baseline_price=2900.0)

        with patch("app.services.price_checker._send_notifications") as mock_notify:
            _check_subscription(sub, db)

        mock_notify.assert_not_called()
        assert sub.is_active is True
        assert sub.trigger_count == 0

    def test_exact_equal_does_not_trigger(self, db: Session):
        """latest_price == target_price: condition is strict '<', must NOT trigger."""
        user = _make_user(db)
        _, plan_id = _make_plan(db)
        _add_history(db, plan_id, prices=[3000.0, 3200.0])
        sub = _make_sub(db, user.id, plan_id, target_price=3000.0, baseline_price=3200.0)

        with patch("app.services.price_checker._send_notifications") as mock_notify:
            _check_subscription(sub, db)

        mock_notify.assert_not_called()
        assert sub.is_active is True

    def test_no_prior_history_treats_as_first_crossing(self, db: Session):
        """Only one price history entry (no 'before'): treated as first crossing → trigger."""
        user = _make_user(db)
        _, plan_id = _make_plan(db)
        # Single history entry — no previous to compare against
        _add_history(db, plan_id, prices=[2800.0])
        sub = _make_sub(db, user.id, plan_id, target_price=3000.0, baseline_price=None)

        with patch("app.services.price_checker._send_notifications"):
            _check_subscription(sub, db)

        assert sub.is_active is False
        assert sub.trigger_count == 1

    def test_re_run_after_auto_pause_does_not_re_trigger(self, db: Session):
        """After auto-pause (is_active=False), check_all_subscriptions must skip it."""
        user = _make_user(db)
        _, plan_id = _make_plan(db)
        _add_history(db, plan_id, prices=[2800.0, 3200.0])
        sub = _make_sub(db, user.id, plan_id, target_price=3000.0, baseline_price=3200.0)

        with patch("app.services.price_checker._send_notifications"):
            # First run: triggers and pauses
            check_all_subscriptions(db)

        assert sub.is_active is False
        assert sub.trigger_count == 1

        with patch("app.services.price_checker._send_notifications") as mock_notify:
            # Second run with identical data: subscription is inactive, skipped
            check_all_subscriptions(db)

        mock_notify.assert_not_called()
        assert sub.trigger_count == 1  # unchanged
