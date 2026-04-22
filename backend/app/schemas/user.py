from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordResetRequestEmail(BaseModel):
    email: EmailStr


class PasswordResetWithToken(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# PriceSubscription schemas
# ---------------------------------------------------------------------------

class SubscriptionCreate(BaseModel):
    # Target (at least one of apartment_id/plan_id OR city must be provided)
    apartment_id: Optional[int] = None
    plan_id: Optional[int] = None

    # Area-level
    city: Optional[str] = None
    zipcode: Optional[str] = None
    min_bedrooms: Optional[float] = None
    max_bedrooms: Optional[float] = None

    # Thresholds
    target_price: Optional[float] = None
    price_drop_pct: Optional[float] = Field(None, ge=0, le=100)

    # Baseline — frontend may pass the currently displayed price so the
    # server doesn't need an extra DB round-trip.  If omitted, the endpoint
    # infers it from the latest price history.
    baseline_price: Optional[float] = None

    # Channels
    notify_email: bool = True
    notify_telegram: bool = False
    telegram_chat_id: Optional[str] = None

    # Set True only by the server when auto-creating a demo subscription on register
    is_demo: bool = False

    @model_validator(mode="after")
    def _validate_target_below_baseline(self) -> SubscriptionCreate:
        if self.target_price is not None and self.baseline_price is not None:
            if self.target_price >= self.baseline_price:
                raise ValueError(
                    f"target_price ({self.target_price}) must be below baseline_price "
                    f"({self.baseline_price})"
                )
        return self


class SubscriptionUpdate(BaseModel):
    city: Optional[str] = None
    zipcode: Optional[str] = None
    min_bedrooms: Optional[float] = None
    max_bedrooms: Optional[float] = None
    target_price: Optional[float] = None
    price_drop_pct: Optional[float] = Field(None, ge=0, le=100)
    notify_email: Optional[bool] = None
    notify_telegram: Optional[bool] = None
    telegram_chat_id: Optional[str] = None
    is_active: Optional[bool] = None


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    apartment_id: Optional[int]
    plan_id: Optional[int]
    city: Optional[str]
    zipcode: Optional[str]
    min_bedrooms: Optional[float]
    max_bedrooms: Optional[float]
    target_price: Optional[float]
    price_drop_pct: Optional[float]
    baseline_price: Optional[float]
    baseline_recorded_at: Optional[datetime]
    notify_email: bool
    notify_telegram: bool
    telegram_chat_id: Optional[str]
    is_active: bool
    is_demo: bool
    last_notified_at: Optional[datetime]
    trigger_count: int
    created_at: datetime

    # Enriched fields — populated by list_subscriptions, None on create/update
    apartment_title: Optional[str] = None
    apartment_city: Optional[str] = None
    plan_name: Optional[str] = None
    plan_spec: Optional[str] = None   # e.g. "1BR · 1BA · 520 sqft"
    latest_price: Optional[float] = None
