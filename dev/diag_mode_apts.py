#!/usr/bin/env python3
"""Diagnostic for Mode Apartments (id=153, modesanmateo.com).

Checks every stage the scraper goes through:
  A) fetch_static → RentCafe detection signal?
  B) fetch_rendered → RentCafe detection signal?
  C) _fetch_html('/floorplans') via urllib → 403?
  D) Playwright render of /floorplans → works?
  E) _parse_rentcafe_floorplans on rendered HTML → any plans?
  F) Full agent.scrape() with DEBUG logging → root cause
"""
from __future__ import annotations
import asyncio, sys, logging
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv; load_dotenv(ROOT / "backend" / ".env")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# Quiet noisy libs
for lib in ("playwright", "asyncio", "urllib3", "httpcore", "httpx"):
    logging.getLogger(lib).setLevel(logging.WARNING)

from app.services.scraper_agent.fetch import (
    fetch_static, fetch_rendered, has_sufficient_plan_signals, is_cloudflare_challenge,
)
from app.services.scraper_agent.platforms.rentcafe import (
    RentCafeAdapter, _RENTCAFE_RE, _floorplans_url, _fetch_html, _parse_rentcafe_floorplans,
)
from app.services.scraper_agent.browser_tools import BrowserSession

URL = "https://www.modesanmateo.com/?utm_source=apartmentseo&utm_medium=gmb&utm_campaign=organicmaplisting"
FP_URL = "https://www.modesanmateo.com/floorplans"

SEP = "─" * 70


async def main():
    # ── A) Static fetch ───────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("A) fetch_static")
    static_html = await fetch_static(URL)
    cloudflare = is_cloudflare_challenge(static_html)
    sufficient = has_sufficient_plan_signals(static_html)
    rentcafe_signal = bool(_RENTCAFE_RE.search(static_html)) if static_html else False
    print(f"   len={len(static_html)}  cloudflare={cloudflare}  sufficient={sufficient}")
    print(f"   _RENTCAFE_RE match in static HTML: {rentcafe_signal}")
    if rentcafe_signal:
        m = _RENTCAFE_RE.search(static_html)
        ctx = static_html[max(0,m.start()-30):m.end()+40]
        print(f"   context: {ctx!r}")

    # ── B) Rendered fetch ─────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("B) fetch_rendered (Playwright)")
    async with BrowserSession(headless=True) as browser:
        rendered_html = await fetch_rendered(URL, browser)
        cloudflare_r = is_cloudflare_challenge(rendered_html)
        sufficient_r = has_sufficient_plan_signals(rendered_html)
        rentcafe_r = bool(_RENTCAFE_RE.search(rendered_html)) if rendered_html else False
        print(f"   len={len(rendered_html)}  cloudflare={cloudflare_r}  sufficient={sufficient_r}")
        print(f"   _RENTCAFE_RE match in rendered HTML: {rentcafe_r}")
        if rentcafe_r:
            m = _RENTCAFE_RE.search(rendered_html)
            ctx = rendered_html[max(0,m.start()-30):m.end()+40]
            print(f"   context: {ctx!r}")

        adapter = RentCafeAdapter()
        detected = adapter.detect(rendered_html, URL)
        print(f"   RentCafeAdapter.detect() = {detected}")
        print(f"   adapter._floorplans_url  = {adapter._floorplans_url!r}")

        # ── C) urllib fetch of /floorplans ──────────────────────────────────
        print(f"\n{SEP}")
        print(f"C) urllib GET {FP_URL}")
        try:
            fp_html_urllib = _fetch_html(FP_URL)
            print(f"   SUCCESS len={len(fp_html_urllib)}")
            # Try parsing it
            plans = _parse_rentcafe_floorplans(fp_html_urllib)
            print(f"   _parse_rentcafe_floorplans → {len(plans)} plans")
            for p in plans[:5]:
                print(f"     {p}")
        except Exception as e:
            print(f"   FAILED: {e}")

        # ── D) Playwright fetch of /floorplans ──────────────────────────────
        print(f"\n{SEP}")
        print(f"D) Playwright navigate to {FP_URL}")
        state = await browser.navigate_to(FP_URL)
        print(f"   error={state.get('error')!r}  url={browser.page.url!r}")
        if not state.get("error"):
            fp_html_pw = await browser.page.content()
            print(f"   Playwright HTML len={len(fp_html_pw)}")
            rentcafe_fp = bool(_RENTCAFE_RE.search(fp_html_pw))
            print(f"   _RENTCAFE_RE in /floorplans rendered: {rentcafe_fp}")
            # Check for GA4 pricing signal
            import re as _re
            ga4_hits = _re.findall(r"setGA4Cookie\([^)]{10,}\)", fp_html_pw)
            print(f"   setGA4Cookie() calls found: {len(ga4_hits)}")
            if ga4_hits:
                print(f"   first: {ga4_hits[0][:100]}")
            # Parse
            plans_pw = _parse_rentcafe_floorplans(fp_html_pw)
            print(f"   _parse_rentcafe_floorplans(rendered) → {len(plans_pw)} plans")
            for p in plans_pw[:5]:
                print(f"     {p}")

            # ── E) Check what blocks the urllib but not Playwright ───────────
            print(f"\n{SEP}")
            print("E) First 800 chars of Playwright /floorplans body:")
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(fp_html_pw, "html.parser")
            for t in soup(["script","style"]): t.decompose()
            text = soup.get_text(separator="\n", strip=True)
            print(text[:800])

    print(f"\n{SEP}")
    print("CONCLUSION")
    print(f"  static RentCafe signal:    {rentcafe_signal}")
    print(f"  rendered RentCafe signal:  {rentcafe_r}")
    print(f"  adapter.detect(rendered):  {detected}")


asyncio.run(main())
