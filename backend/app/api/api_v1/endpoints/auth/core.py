import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.limiter import limiter
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import PasswordResetRequest, Token, UserCreate, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(
    request: Request,
    payload: UserCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Create a new account and return a JWT.

    Also creates a demo price-drop subscription and queues a welcome email
    so new users immediately see an example alert. Both steps are
    fault-tolerant — registration succeeds even if they fail.
    """
    if db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        unsubscribe_all_token=secrets.token_urlsafe(16),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _maybe_create_demo_subscription(user, db, background_tasks)

    token = create_access_token({"sub": str(user.id)})
    return Token(access_token=token)


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Verify credentials and return a JWT.

    Accepts ``application/x-www-form-urlencoded`` with ``username`` (email)
    and ``password`` fields — standard OAuth2 password flow.
    """
    user = db.execute(select(User).where(User.email == form.username)).scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )
    token = create_access_token({"sub": str(user.id)})
    return Token(access_token=token)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
def reset_password(
    request: Request,
    payload: PasswordResetRequest,
    db: Session = Depends(get_db),
):
    """Reset password by email without verification (development-grade)."""
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if not user:
        # Return 204 even on unknown email to avoid user enumeration
        return
    user.hashed_password = hash_password(payload.new_password)
    db.commit()


@router.get("/me", response_model=UserResponse)
@limiter.limit("60/minute")
def me(request: Request, current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return current_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _maybe_create_demo_subscription(
    user: User,
    db: Session,
    background_tasks: BackgroundTasks,
) -> None:
    """Create a demo price alert for newly registered users and queue a welcome email.

    Selection logic:
      1. Cheapest available 1BR plan in settings.DEFAULT_DEMO_CITY
      2. Fallback: cheapest available 1BR anywhere in the DB
      3. If no 1BR plan exists at all, skip gracefully

    Completely fault-tolerant — wraps everything in try/except so
    registration never fails due to this step.
    """
    try:
        from app.models.apartment import Apartment, Plan
        from app.models.user import PriceSubscription
        from app.services.notification import send_welcome_email

        def _find_cheapest_1br(city_filter: str | None):
            stmt = (
                select(
                    Plan.id,
                    Plan.price,
                    Plan.name,
                    Apartment.title,
                    Apartment.city,
                )
                .join(Apartment, Apartment.id == Plan.apartment_id)
                .where(
                    Plan.is_available.is_(True),
                    Plan.price.is_not(None),
                    Plan.bedrooms == 1.0,
                )
                .order_by(Plan.price.asc())
                .limit(1)
            )
            if city_filter:
                stmt = stmt.where(func.lower(Apartment.city) == city_filter.lower())
            return db.execute(stmt).first()

        row = _find_cheapest_1br(settings.DEFAULT_DEMO_CITY) or _find_cheapest_1br(None)

        if row is None:
            logger.info(
                "No available 1BR plan found — skipping demo subscription for user %d",
                user.id,
            )
            return

        plan_id, price, plan_name, apt_title, apt_city = row

        sub = PriceSubscription(
            user_id=user.id,
            plan_id=plan_id,
            price_drop_pct=5.0,
            notify_email=True,
            is_demo=True,
            is_active=True,
            baseline_price=price,
            baseline_recorded_at=datetime.now(timezone.utc),
            unsubscribe_token=secrets.token_urlsafe(16),
        )
        db.add(sub)
        db.commit()
        logger.info(
            "Demo subscription created for user %d → plan %d (%s %s $%.0f)",
            user.id, plan_id, apt_title, plan_name, price,
        )

        background_tasks.add_task(
            send_welcome_email, user.email, apt_title, plan_name, price, apt_city
        )

    except Exception as exc:
        logger.warning(
            "Demo subscription setup failed for user %d (registration unaffected): %s",
            user.id, exc,
        )
