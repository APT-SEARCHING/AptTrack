"""Unit tests for backend/app/services/price_checker.py.

Uses an in-memory SQLite database; _send_notifications is patched out so no
real email/Telegram calls are made.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

# Fixed-offset stand-in for America/Los_Angeles (PST = UTC-8).
# Using a fixed offset avoids a zoneinfo / pytz dependency in tests.
_PT = timezone(timedelta(hours=-8))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.base  # noqa: F401 — registers all models with Base.metadata
from app.core.security import hash_password
from app.db.base_class import Base
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.models.user import PriceSubscription, User
from app.services.price_checker import _check_subscription, check_all_subscriptions, _is_triggered


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


# ---------------------------------------------------------------------------
# Bug #2: price_drop_pct uses baseline_price as anchor
# ---------------------------------------------------------------------------

class TestPriceDropPct:

    def test_drop_meets_threshold_triggers(self, db: Session):
        """10% actual drop against a 10% threshold → triggered, auto-paused."""
        user = _make_user(db)
        _, plan_id = _make_plan(db, price=2700.0)
        _add_history(db, plan_id, prices=[2700.0])
        sub = _make_sub(db, user.id, plan_id, price_drop_pct=10.0, baseline_price=3000.0)
        sub.baseline_recorded_at = datetime(2026, 3, 15, tzinfo=timezone.utc)
        db.flush()

        with patch("app.services.price_checker._send_notifications") as mock_notify:
            _check_subscription(sub, db)

        mock_notify.assert_called_once()
        assert sub.is_active is False
        assert sub.trigger_count == 1
        # Reason string must show baseline amount, baseline date, current price.
        # _send_notifications(sub, subject, body, tg_msg, db) → body is at index [2]
        body = mock_notify.call_args[0][2]
        assert "3,000" in body
        assert "2,700" in body
        assert "Mar" in body

    def test_drop_below_threshold_does_not_trigger(self, db: Session):
        """5% actual drop against a 10% threshold → not triggered."""
        user = _make_user(db)
        _, plan_id = _make_plan(db, price=2850.0)
        _add_history(db, plan_id, prices=[2850.0])
        sub = _make_sub(db, user.id, plan_id, price_drop_pct=10.0, baseline_price=3000.0)

        with patch("app.services.price_checker._send_notifications") as mock_notify:
            _check_subscription(sub, db)

        mock_notify.assert_not_called()
        assert sub.is_active is True
        assert sub.trigger_count == 0

    def test_baseline_none_skips_with_warning(self, db: Session):
        """No baseline_price → skip without notification, log a warning."""
        user = _make_user(db)
        _, plan_id = _make_plan(db, price=2700.0)
        _add_history(db, plan_id, prices=[2700.0])
        sub = _make_sub(db, user.id, plan_id, price_drop_pct=5.0, baseline_price=None)

        with patch("app.services.price_checker._send_notifications") as mock_notify, \
             patch("app.services.price_checker.logger") as mock_logger:
            _check_subscription(sub, db)

        mock_notify.assert_not_called()
        assert sub.is_active is True
        mock_logger.warning.assert_called_once()
        assert "baseline_price" in mock_logger.warning.call_args[0][0]

    def test_pct_zero_triggers_on_any_drop(self, db: Session):
        """pct=0: drop >= 0 satisfied when latest_price <= baseline → triggers.
        Documented: pct=0 means 'alert on any price decrease (or no change)'."""
        user = _make_user(db)
        _, plan_id = _make_plan(db, price=2999.0)
        _add_history(db, plan_id, prices=[2999.0])
        sub = _make_sub(db, user.id, plan_id, price_drop_pct=0.0, baseline_price=3000.0)

        with patch("app.services.price_checker._send_notifications"):
            _check_subscription(sub, db)

        assert sub.is_active is False
        assert sub.trigger_count == 1

    def test_pct_zero_triggers_on_exact_equal(self, db: Session):
        """pct=0 with latest == baseline: 0% drop satisfies drop >= 0 → triggers."""
        user = _make_user(db)
        _, plan_id = _make_plan(db, price=3000.0)
        _add_history(db, plan_id, prices=[3000.0])
        sub = _make_sub(db, user.id, plan_id, price_drop_pct=0.0, baseline_price=3000.0)

        with patch("app.services.price_checker._send_notifications"):
            _check_subscription(sub, db)

        assert sub.is_active is False
        assert sub.trigger_count == 1


# ---------------------------------------------------------------------------
# Bug #3: debounce last_notified_at timezone handling
# ---------------------------------------------------------------------------

class TestDebounceTimezone:
    """Verify _check_subscription correctly computes debounce age regardless of
    whether last_notified_at is naive, UTC-aware, or non-UTC-aware."""

    def _sub_already_triggered(
        self, db: Session, last_notified: datetime
    ) -> PriceSubscription:
        """Create a subscription that would trigger (price just crossed below target)
        but has last_notified_at set to *last_notified* to test debounce."""
        user = _make_user(db)
        _, plan_id = _make_plan(db, price=2800.0)
        _add_history(db, plan_id, prices=[2800.0, 3200.0])
        sub = _make_sub(db, user.id, plan_id, target_price=3000.0, baseline_price=3200.0)
        sub.last_notified_at = last_notified
        db.flush()
        return sub

    def test_aware_utc_recent_debounces(self, db: Session):
        """Aware UTC datetime 1 hour ago → within 24h window → debounced."""
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        sub = self._sub_already_triggered(db, last_notified=recent)

        with patch("app.services.price_checker._send_notifications") as mock_notify:
            _check_subscription(sub, db)

        mock_notify.assert_not_called()

    def test_aware_non_utc_recent_debounces(self, db: Session):
        """Aware PT datetime 1 hour ago → still within 24h after astimezone → debounced."""
        recent_pt = datetime.now(_PT) - timedelta(hours=1)
        sub = self._sub_already_triggered(db, last_notified=recent_pt)

        with patch("app.services.price_checker._send_notifications") as mock_notify:
            _check_subscription(sub, db)

        mock_notify.assert_not_called()

    def test_naive_recent_debounces(self, db: Session):
        """Naive datetime 1 hour ago → assumed UTC → within 24h → debounced."""
        recent_naive = datetime.utcnow() - timedelta(hours=1)
        assert recent_naive.tzinfo is None
        sub = self._sub_already_triggered(db, last_notified=recent_naive)

        with patch("app.services.price_checker._send_notifications") as mock_notify:
            _check_subscription(sub, db)

        mock_notify.assert_not_called()

    def test_aware_utc_old_does_not_debounce(self, db: Session):
        """Aware UTC datetime 25 hours ago → outside 24h window → fires."""
        old = datetime.now(timezone.utc) - timedelta(hours=25)
        sub = self._sub_already_triggered(db, last_notified=old)

        with patch("app.services.price_checker._send_notifications") as mock_notify:
            _check_subscription(sub, db)

        mock_notify.assert_called_once()
