import logging
import secrets
from datetime import datetime, timedelta, timezone

import requests as _requests
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.limiter import limiter
from app.core.security import get_current_user, require_admin
from app.db.session import get_db
from app.models.user import PriceSubscription, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

_LINK_TOKEN_TTL_SECONDS = 900  # 15 minutes


def _tg_api(path: str, **kwargs):
    """Call the Telegram Bot API synchronously. Raises on HTTP errors."""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{path}"
    r = _requests.post(url, timeout=10, **kwargs)
    r.raise_for_status()
    return r.json()


def _get_bot_username() -> str:
    try:
        data = _tg_api("getMe")
        return data["result"]["username"]
    except Exception as exc:
        logger.error("telegram: getMe failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot unavailable",
        )


# ── Auth-required endpoints ──────────────────────────────────────────────────


@router.post("/link-token")
@limiter.limit("5/minute")
def generate_link_token(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a one-time deep-link token the user taps in Telegram to bind their chat."""
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram not configured",
        )

    bot_username = _get_bot_username()
    token = secrets.token_urlsafe(24)
    current_user.telegram_link_token = token
    current_user.telegram_link_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=_LINK_TOKEN_TTL_SECONDS
    )
    db.add(current_user)
    db.commit()

    deep_link = f"https://t.me/{bot_username}?start={token}"
    return {"deep_link": deep_link, "expires_in": _LINK_TOKEN_TTL_SECONDS}


@router.get("/status")
@limiter.limit("60/minute")
def telegram_status(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Return whether the current user has a linked Telegram account."""
    return {"linked": current_user.telegram_chat_id is not None}


@router.delete("/unlink")
@limiter.limit("10/minute")
def unlink_telegram(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove Telegram binding and disable Telegram on all subscriptions."""
    current_user.telegram_chat_id = None
    current_user.telegram_link_token = None
    current_user.telegram_link_expires_at = None

    subs = db.execute(
        select(PriceSubscription).where(PriceSubscription.user_id == current_user.id)
    ).scalars().all()
    for sub in subs:
        sub.notify_telegram = False
        sub.telegram_chat_id = None

    db.commit()
    return {"ok": True}


# ── Webhook (public, verified by secret header) ──────────────────────────────


@router.post("/webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive Telegram Bot API updates.

    Security: Telegram sends the TELEGRAM_WEBHOOK_SECRET value as the
    X-Telegram-Bot-Api-Secret-Token header on every request.  We reject
    requests that don't carry the correct secret.
    """
    secret = settings.TELEGRAM_WEBHOOK_SECRET
    if secret:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not secrets.compare_digest(incoming, secret):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bad secret")

    try:
        body = await request.json()
    except Exception:
        return {"ok": True}

    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"ok": True}

    text: str = message.get("text", "")
    chat_id = str(message.get("chat", {}).get("id", ""))
    if not chat_id:
        return {"ok": True}

    # Only handle /start <token>
    if not text.startswith("/start "):
        return {"ok": True}

    token = text.removeprefix("/start ").strip()
    if not token:
        return {"ok": True}

    user = db.execute(
        select(User).where(User.telegram_link_token == token)
    ).scalar_one_or_none()

    if user is None:
        _send_message(chat_id, "❌ This link has already been used or is invalid. Please generate a new one from AptTrack.")
        return {"ok": True}

    if user.telegram_link_expires_at and user.telegram_link_expires_at < datetime.now(timezone.utc):
        _send_message(chat_id, "⏱ This link has expired. Please generate a new one from AptTrack.")
        return {"ok": True}

    # Bind the Telegram account to the user
    user.telegram_chat_id = chat_id
    user.telegram_link_token = None
    user.telegram_link_expires_at = None

    # Enable Telegram on all existing active subscriptions
    subs = db.execute(
        select(PriceSubscription).where(
            PriceSubscription.user_id == user.id,
            PriceSubscription.is_active.is_(True),
        )
    ).scalars().all()
    for sub in subs:
        sub.notify_telegram = True
        sub.telegram_chat_id = chat_id

    db.commit()
    logger.info("telegram: linked chat_id=%s to user_id=%d (%d subs updated)", chat_id, user.id, len(subs))

    _send_message(
        chat_id,
        "✅ *AptTrack connected!*\n\nYou'll receive price drop alerts here. "
        "Manage your alerts at apttrack-production-6c87.up.railway.app",
    )
    return {"ok": True}


# ── Admin: register webhook ──────────────────────────────────────────────────


@router.post("/set-webhook")
@limiter.limit("3/minute")
def set_webhook(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Register the Telegram webhook URL with Telegram (admin only, run once)."""
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN not set")

    webhook_url = f"{settings.APP_BASE_URL}/api/v1/telegram/webhook"
    payload: dict = {"url": webhook_url, "allowed_updates": ["message"]}
    if settings.TELEGRAM_WEBHOOK_SECRET:
        payload["secret_token"] = settings.TELEGRAM_WEBHOOK_SECRET

    try:
        result = _tg_api("setWebhook", json=payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Telegram API error: {exc}")

    logger.info("telegram: setWebhook → %s", result)
    return {"ok": True, "webhook_url": webhook_url, "telegram_response": result}


def _send_message(chat_id: str, text: str) -> None:
    """Fire-and-forget Telegram sendMessage. Errors are logged, never raised."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    try:
        _tg_api("sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
    except Exception as exc:
        logger.warning("telegram: sendMessage to %s failed: %s", chat_id, exc)
