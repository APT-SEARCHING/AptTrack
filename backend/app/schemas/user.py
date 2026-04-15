from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


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

    # Channels
    notify_email: bool = True
    notify_telegram: bool = False
    telegram_chat_id: Optional[str] = None


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
    notify_email: bool
    notify_telegram: bool
    telegram_chat_id: Optional[str]
    is_active: bool
    last_notified_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True
