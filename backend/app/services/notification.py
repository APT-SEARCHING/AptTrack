"""Fire-and-forget notification helpers.

Both functions catch all exceptions internally so a failed notification
never crashes the caller (price checker / Celery task).

Return value: ``(external_id: str | None, status: str, is_403: bool)``
  - external_id: provider message ID for webhook correlation
  - status: 'sent' | 'failed'
  - is_403: True only for Telegram 403 (bot blocked by user) — caller should
             disable notify_telegram on the subscription
"""

import logging
from typing import Optional, Tuple

import aiohttp

from app.core.config import settings

logger = logging.getLogger(__name__)

# (external_id | None, status, is_403)
_NotifResult = Tuple[Optional[str], str, bool]


async def send_email_alert(to_email: str, subject: str, body: str) -> _NotifResult:
    """Send an email via the SendGrid Web API v3.

    Returns ``(x_message_id, status, False)``.
    """
    if not settings.SENDGRID_API_KEY:
        logger.warning("send_email_alert: SENDGRID_API_KEY not configured, skipping")
        return (None, "failed", False)

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": settings.SENDGRID_FROM_EMAIL},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status not in (200, 202):
                    text = await resp.text()
                    logger.error(
                        "send_email_alert failed: status=%d body=%s", resp.status, text[:200]
                    )
                    return (None, "failed", False)

                # SendGrid returns the message ID in X-Message-Id response header
                external_id = resp.headers.get("X-Message-Id")
                logger.info(
                    "Email alert sent to %s (subject: %s, msg_id: %s)",
                    to_email, subject, external_id,
                )
                return (external_id, "sent", False)
    except Exception as exc:
        logger.error("send_email_alert exception: %s", exc)
        return (None, "failed", False)


async def send_telegram_alert(chat_id: str, message: str) -> _NotifResult:
    """Send a message via the Telegram Bot API.

    Returns ``(str(telegram_message_id), status, is_403)``.
    A 403 means the user blocked the bot — caller disables the channel.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("send_telegram_alert: TELEGRAM_BOT_TOKEN not configured, skipping")
        return (None, "failed", False)

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.json(content_type=None)
                if resp.status == 200 and body.get("ok"):
                    msg_id = str(body.get("result", {}).get("message_id", ""))
                    logger.info(
                        "Telegram alert sent to chat_id=%s (msg_id=%s)", chat_id, msg_id
                    )
                    return (msg_id or None, "sent", False)

                if resp.status == 403:
                    logger.warning(
                        "send_telegram_alert: 403 for chat_id=%s (bot blocked) — "
                        "will disable telegram notifications for this subscription",
                        chat_id,
                    )
                    return (None, "failed", True)

                logger.error(
                    "send_telegram_alert failed: status=%d body=%s",
                    resp.status, str(body)[:200],
                )
                return (None, "failed", False)
    except Exception as exc:
        logger.error("send_telegram_alert exception: %s", exc)
        return (None, "failed", False)
