"""Fire-and-forget notification helpers.

Both functions catch all exceptions internally so a failed notification
never crashes the caller (price checker / Celery task).
"""

import logging

import aiohttp

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_email_alert(to_email: str, subject: str, body: str) -> None:
    """Send an email via the SendGrid Web API v3.

    Requires ``SENDGRID_API_KEY`` and ``SENDGRID_FROM_EMAIL`` to be set.
    Silently logs errors without raising.
    """
    if not settings.SENDGRID_API_KEY:
        logger.warning("send_email_alert: SENDGRID_API_KEY not configured, skipping")
        return

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
                else:
                    logger.info("Email alert sent to %s (subject: %s)", to_email, subject)
    except Exception as exc:
        logger.error("send_email_alert exception: %s", exc)


async def send_telegram_alert(chat_id: str, message: str) -> None:
    """Send a message via the Telegram Bot API.

    Requires ``TELEGRAM_BOT_TOKEN`` to be set.
    Silently logs errors without raising.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("send_telegram_alert: TELEGRAM_BOT_TOKEN not configured, skipping")
        return

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(
                        "send_telegram_alert failed: status=%d body=%s", resp.status, text[:200]
                    )
                else:
                    logger.info("Telegram alert sent to chat_id=%s", chat_id)
    except Exception as exc:
        logger.error("send_telegram_alert exception: %s", exc)
