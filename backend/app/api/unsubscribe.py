"""One-click unsubscribe endpoints (CAN-SPAM compliance).

Two routes, both unauthenticated — the token in the URL is the credential:
  GET /unsubscribe/{token}        — deactivate a single subscription
  GET /unsubscribe/all/{token}    — deactivate all subscriptions for a user

Returns HTML by default (for email clients that open the link directly).
Returns JSON when the caller sends ``Accept: application/json``
(used by the React SPA to render its own styled confirmation page).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.limiter import limiter
from app.db.session import get_db
from app.models.user import PriceSubscription, User

router = APIRouter(tags=["unsubscribe"])

# ---------------------------------------------------------------------------
# Minimal inline HTML pages (plain fallback for no-JS email clients)
# ---------------------------------------------------------------------------

_STYLE = """
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{font-family:system-ui,sans-serif;max-width:480px;margin:80px auto;padding:0 20px;color:#1e293b}
  h1{font-size:1.4rem;margin-bottom:.5rem}
  p{color:#64748b;line-height:1.6;margin:.5rem 0}
  .actions{margin-top:1.5rem;display:flex;gap:.75rem;flex-wrap:wrap}
  .btn{padding:.5rem 1.25rem;border-radius:.375rem;text-decoration:none;font-weight:500;font-size:.9rem}
  .primary{background:#4f46e5;color:#fff}
  .secondary{background:#f1f5f9;color:#475569}
  .logo{font-size:.8rem;color:#94a3b8;margin-top:2.5rem}
</style>
"""

_HTML_UNSUBSCRIBED_ONE = """\
<!DOCTYPE html><html lang="en"><head><title>Unsubscribed · AptTrack</title>{style}</head>
<body>
<h1>&#10003; You've been unsubscribed</h1>
<p>This price alert has been paused. You won't receive any more notifications for it.</p>
<p>You can re-enable it any time from your alerts page.</p>
<div class="actions">
  <a class="btn primary" href="/alerts">Manage alerts</a>
  <a class="btn secondary" href="/">Back to AptTrack</a>
</div>
<p class="logo">AptTrack &middot; Bay Area rental price transparency</p>
</body></html>""".format(style=_STYLE)

_HTML_UNSUBSCRIBED_ALL = """\
<!DOCTYPE html><html lang="en"><head><title>All alerts paused · AptTrack</title>{style}</head>
<body>
<h1>&#10003; All price alerts paused</h1>
<p>You won't receive any more price-drop notifications from AptTrack.</p>
<p>You can re-enable individual alerts any time from your alerts page.</p>
<div class="actions">
  <a class="btn primary" href="/alerts">Manage alerts</a>
  <a class="btn secondary" href="/">Back to AptTrack</a>
</div>
<p class="logo">AptTrack &middot; Bay Area rental price transparency</p>
</body></html>""".format(style=_STYLE)

_HTML_NOT_FOUND = """\
<!DOCTYPE html><html lang="en"><head><title>Link expired · AptTrack</title>{style}</head>
<body>
<h1>Link not found</h1>
<p>This unsubscribe link is invalid or has already been used.</p>
<div class="actions">
  <a class="btn primary" href="/alerts">Manage alerts</a>
</div>
<p class="logo">AptTrack &middot; Bay Area rental price transparency</p>
</body></html>""".format(style=_STYLE)


def _wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def _respond(request: Request, html: str, payload: dict, status_code: int = 200):
    if _wants_json(request):
        return JSONResponse(payload, status_code=status_code)
    return HTMLResponse(html, status_code=status_code)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/unsubscribe/all/{token}")
@limiter.limit("20/minute")
def unsubscribe_all(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    """Deactivate every subscription belonging to the token's owner."""
    user = db.execute(
        select(User).where(User.unsubscribe_all_token == token)
    ).scalar_one_or_none()

    if user is None:
        return _respond(
            request, _HTML_NOT_FOUND,
            {"detail": "Token not found"}, status_code=404,
        )

    subs = db.execute(
        select(PriceSubscription).where(PriceSubscription.user_id == user.id)
    ).scalars().all()
    for sub in subs:
        sub.is_active = False
    db.commit()

    return _respond(
        request, _HTML_UNSUBSCRIBED_ALL,
        {"message": f"All {len(subs)} alert(s) paused"},
    )


@router.get("/unsubscribe/{token}")
@limiter.limit("20/minute")
def unsubscribe_one(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    """Deactivate a single subscription by its unsubscribe token."""
    sub = db.execute(
        select(PriceSubscription).where(PriceSubscription.unsubscribe_token == token)
    ).scalar_one_or_none()

    if sub is None:
        return _respond(
            request, _HTML_NOT_FOUND,
            {"detail": "Token not found"}, status_code=404,
        )

    sub.is_active = False
    db.commit()

    return _respond(
        request, _HTML_UNSUBSCRIBED_ONE,
        {"message": "Unsubscribed successfully"},
    )
