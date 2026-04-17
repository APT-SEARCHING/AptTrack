"""POST /api/v1/webhooks/sendgrid — SendGrid Event Webhook receiver.

SendGrid signs each delivery using ECDSA-P256.  The public key lives in
``SENDGRID_WEBHOOK_VERIFICATION_KEY`` (PEM format, from the SendGrid dashboard
→ Settings → Mail Settings → Event Webhook → Signature Verification).

If the key is not configured the endpoint still accepts requests so the dev
environment works without a real SendGrid account.  Log a warning so it's
obvious the signature check is skipped.

SendGrid event types we handle:
  bounce        → bounced
  delivered     → delivered
  open          → opened
  click         → clicked
  unsubscribe   → unsubscribed     (list-unsubscribe or group unsubscribe)
  spamreport    → bounced          (treat as a hard failure for engagement)
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.notification_event import NotificationEvent

logger = logging.getLogger(__name__)

router = APIRouter()

# Map SendGrid event.event values to our status column values
_SG_STATUS_MAP: Dict[str, str] = {
    "bounce": "bounced",
    "blocked": "bounced",
    "deferred": "failed",
    "delivered": "delivered",
    "open": "opened",
    "click": "clicked",
    "unsubscribe": "unsubscribed",
    "group_unsubscribe": "unsubscribed",
    "spamreport": "bounced",
}


def _verify_sendgrid_signature(
    public_key_pem: str,
    raw_body: bytes,
    signature_b64: str,
    timestamp: str,
) -> bool:
    """Verify SendGrid's ECDSA-P256 webhook signature.

    Message = timestamp_string + raw_body_string
    Signature = base64-decoded ECDSA-P256 signature over SHA-256 of message.
    """
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        public_key = load_pem_public_key(public_key_pem.encode())
        message = (timestamp + raw_body.decode("utf-8", errors="replace")).encode()
        sig_bytes = base64.b64decode(signature_b64)
        public_key.verify(sig_bytes, message, ECDSA(hashes.SHA256()))
        return True
    except Exception:  # InvalidSignature or decoding errors
        return False


@router.post(
    "/webhooks/sendgrid",
    status_code=status.HTTP_200_OK,
    tags=["webhooks"],
    summary="SendGrid Event Webhook receiver",
    # Public — SendGrid pushes here; auth is via ECDSA signature
    include_in_schema=False,
)
async def sendgrid_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    raw_body = await request.body()

    # Signature verification
    if settings.SENDGRID_WEBHOOK_VERIFICATION_KEY:
        sig = request.headers.get("X-Twilio-Email-Event-Webhook-Signature", "")
        ts = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp", "")
        if not sig or not ts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing SendGrid signature headers",
            )
        if not _verify_sendgrid_signature(
            settings.SENDGRID_WEBHOOK_VERIFICATION_KEY, raw_body, sig, ts
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid SendGrid signature",
            )
    else:
        logger.warning(
            "SENDGRID_WEBHOOK_VERIFICATION_KEY not set — accepting webhook without verification"
        )

    try:
        events: List[Dict[str, Any]] = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body",
        )

    if not isinstance(events, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expected a JSON array of events",
        )

    updated = 0
    for event in events:
        sg_event_type = event.get("event", "")
        our_status = _SG_STATUS_MAP.get(sg_event_type)
        if our_status is None:
            continue  # event type we don't track (e.g. processed, group_resubscribe)

        # SendGrid sets sg_message_id — format: "<uuid>.<filter>@..."
        # We stored the X-Message-Id header value, which equals the first segment.
        sg_msg_id = event.get("sg_message_id", "")
        if not sg_msg_id:
            continue

        # Normalise: strip filter suffix if present
        external_id = sg_msg_id.split(".")[0] if "." in sg_msg_id else sg_msg_id

        row = db.execute(
            select(NotificationEvent).where(
                NotificationEvent.external_id == external_id,
                NotificationEvent.channel == "email",
            )
        ).scalar_one_or_none()

        if row is None:
            logger.debug(
                "sendgrid_webhook: no NotificationEvent found for external_id=%s event=%s",
                external_id, sg_event_type,
            )
            continue

        # Only advance status — don't regress from 'clicked' back to 'opened', etc.
        _STATUS_RANK = {
            "sent": 0, "failed": 0, "delivered": 1, "opened": 2,
            "clicked": 3, "bounced": 4, "unsubscribed": 4,
        }
        current_rank = _STATUS_RANK.get(row.status, 0)
        new_rank = _STATUS_RANK.get(our_status, 0)
        if new_rank >= current_rank:
            row.status = our_status
            updated += 1

    if updated:
        db.commit()

    logger.info(
        "sendgrid_webhook: processed %d event(s), updated %d row(s)", len(events), updated
    )
    return {"processed": len(events), "updated": updated}
