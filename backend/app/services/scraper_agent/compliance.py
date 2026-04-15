"""
CEASE & DESIST RESPONSE PROTOCOL
=================================
If AptTrack receives a C&D letter or formal objection from any property
management company or website operator:

1. IMMEDIATELY set is_active=False on the domain's ScrapeSiteRegistry row:
       db.query(ScrapeSiteRegistry).filter_by(domain=domain).update({
           "is_active": False,
           "ceased_reason": "C&D received YYYY-MM-DD — <sender>",
       })
2. DELETE all Apartment and Plan data originating from that domain:
       db.query(Apartment).filter(Apartment.source_url.ilike(f"%{domain}%")).delete()
3. Respond to the sender confirming compliance within 48 hours.
4. Log the incident in ceased_reason with date and details.
5. Do NOT re-enable scraping for that domain without legal review.

LEGAL CONTEXT
=============
- hiQ v. LinkedIn (9th Cir. 2022): scraping publicly visible logged-out
  data does not violate CFAA.
- Meta v. Bright Data (N.D. Cal. 2024): same principle confirmed.
- Craigslist v. RadPad (N.D. Cal. 2017): $60.5M judgment — NEVER scrape
  Craigslist or other UGC/marketplace platforms.
- AptTrack only scrapes individual apartment complex websites (not
  aggregators), collects factual pricing data only, and requires no login.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import aiohttp

logger = logging.getLogger(__name__)

OUR_USER_AGENT = "AptTrack/1.0"

# Hard-banned domains — never scrape regardless of robots.txt
_BANNED_DOMAINS = frozenset([
    "craigslist.org",
    "www.craigslist.org",
    "zillow.com",
    "www.zillow.com",
    "apartments.com",
    "www.apartments.com",
    "realtor.com",
    "www.realtor.com",
])


def get_domain(url: str) -> str:
    """Return the lowercased netloc of *url* (e.g. ``'www.rentmiro.com'``)."""
    return urlparse(url).netloc.lower()


async def check_robots_txt(url: str) -> dict:
    """Fetch and parse robots.txt for the domain of *url*.

    Returns a dict with keys:
        ``allowed``   – True if our UA is permitted (or no robots.txt exists)
        ``raw``       – raw robots.txt text, or None if not found
        ``checked_at`` – UTC datetime of the check
    """
    checked_at = datetime.now(timezone.utc)
    domain = get_domain(url)

    # Hard ban — never even check
    if domain in _BANNED_DOMAINS:
        logger.warning("Domain %s is hard-banned — skipping", domain)
        return {"allowed": False, "raw": None, "checked_at": checked_at}

    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                robots_url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 404:
                    # No robots.txt → no restrictions
                    return {"allowed": True, "raw": None, "checked_at": checked_at}
                raw = await resp.text()
    except Exception as exc:
        # Network error fetching robots.txt — assume allowed, log the issue
        logger.warning("Could not fetch robots.txt for %s: %s — assuming allowed", domain, exc)
        return {"allowed": True, "raw": None, "checked_at": checked_at}

    rp = RobotFileParser()
    rp.parse(raw.splitlines())
    # Check our UA first; fall back to generic "*"
    allowed = rp.can_fetch(OUR_USER_AGENT, url)
    if not allowed:
        logger.warning("robots.txt disallows %s for UA=%s", url, OUR_USER_AGENT)
    return {"allowed": allowed, "raw": raw, "checked_at": checked_at}


async def update_registry(url: str, db) -> Optional[bool]:
    """Check robots.txt and upsert the result into ``scrape_site_registry``.

    Returns the ``allowed`` boolean, or ``None`` if the domain is not in the
    registry and was newly inserted.
    """
    from datetime import datetime

    from app.models.site_registry import ScrapeSiteRegistry

    domain = get_domain(url)
    result = await check_robots_txt(url)

    row = db.query(ScrapeSiteRegistry).filter(ScrapeSiteRegistry.domain == domain).first()
    if row is None:
        row = ScrapeSiteRegistry(domain=domain)
        db.add(row)

    row.robots_txt_allows = result["allowed"]
    row.robots_txt_checked_at = result["checked_at"]
    row.robots_txt_raw = result["raw"]
    db.commit()
    return result["allowed"]
