#!/usr/bin/env python3
"""
Read-only diagnostic: compare _page_state links the LLM sees on iteration 1
BEFORE PR B (DOM order, first 20) vs AFTER PR B (scored, ranked top 20).

Apartment: Centerra (apt 176) — smallest regression-risk case (10 iter, 7 plans)
URL: https://www.centerraapts.com/floorplans
"""
from __future__ import annotations
import asyncio, sys, re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv; load_dotenv(ROOT / "backend" / ".env")

from bs4 import BeautifulSoup
from app.services.scraper_agent.browser_tools import (
    BrowserSession,
    MAX_LINKS,
    _score_link,
)

TARGET_URL = "https://www.centerraapts.com/floorplans"


def collect_before(soup: BeautifulSoup) -> list[dict]:
    """Pre-PR-B: DOM order, first MAX_LINKS with non-empty text."""
    links = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if not text:
            continue
        links.append({"text": text[:80], "href": str(a["href"])[:150]})
        if len(links) >= MAX_LINKS:
            break
    return links


def collect_after(soup: BeautifulSoup, page_url: str) -> list[tuple[int, dict]]:
    """Post-PR-B: score each link, stable-sort descending, keep top MAX_LINKS."""
    base_domain = urlparse(page_url).netloc.lower()
    scored: list[tuple[int, dict]] = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if not text:
            continue
        href = str(a["href"])
        score = _score_link(text, href, base_domain)
        scored.append((score, {"text": text[:80], "href": href[:150]}))
    scored.sort(key=lambda x: -x[0])  # stable, preserves DOM order for ties
    return scored[:MAX_LINKS]


async def main():
    print(f"Navigating to {TARGET_URL} ...")
    async with BrowserSession(headless=True) as browser:
        state = await browser.navigate_to(TARGET_URL)
        if state.get("error"):
            print(f"Navigate failed: {state['error']}")
            return

        actual_url = browser.page.url
        print(f"Landed on: {actual_url}\n")

        # Get rendered HTML (same as _page_state does)
        try:
            html = await browser._active_frame.content() if browser._active_frame else await browser.page.content()
        except Exception:
            html = await browser.page.content()

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "meta", "head"]):
            tag.decompose()

        # --- BEFORE ---
        before_links = collect_before(soup)

        # --- AFTER ---
        after_scored = collect_after(soup, actual_url)
        after_links = [entry for _, entry in after_scored]
        after_scores = [score for score, _ in after_scored]

        # Count total links for context
        all_links = [(a.get_text(strip=True), str(a["href"])) for a in soup.find_all("a", href=True) if a.get_text(strip=True)]
        print(f"Total <a> links on page (non-empty text): {len(all_links)}")
        print(f"MAX_LINKS cap: {MAX_LINKS}\n")

        # --- Side-by-side table ---
        col = 38
        print(f"{'Pos':>3}  {'BEFORE (DOM order)':<{col}}  {'Score':>5}  {'AFTER (PR B ranked)':<{col}}")
        print("-" * (3 + 2 + col + 2 + 5 + 2 + col))

        n = max(len(before_links), len(after_links))
        for i in range(n):
            b = before_links[i] if i < len(before_links) else None
            a = after_links[i] if i < len(after_links) else None
            s = after_scores[i] if i < len(after_scores) else None

            b_str = f"{b['text'][:22]} → {b['href'][:14]}" if b else ""
            a_str = f"{a['text'][:22]} → {a['href'][:14]}" if a else ""
            s_str = f"{s:+d}" if s is not None else ""

            # Highlight if link is in after but not in before (newly visible)
            flag = ""
            if a and b:
                before_hrefs = {x["href"] for x in before_links}
                after_hrefs_set = {x["href"] for x in after_links}
                if a["href"] not in before_hrefs:
                    flag = " ◄ NEW"
                if b["href"] not in after_hrefs_set:
                    pass  # before link pushed out

            print(f"{i+1:>3}  {b_str:<{col}}  {s_str:>5}  {a_str:<{col}}{flag}")

        # --- Pushed-out links (in before but not in after) ---
        before_hrefs = {x["href"] for x in before_links}
        after_hrefs = {x["href"] for x in after_links}

        pushed_out = [x for x in before_links if x["href"] not in after_hrefs]
        newly_in = [x for x, s in zip(after_links, after_scores) if x["href"] not in before_hrefs]

        print(f"\n{'─'*80}")
        print(f"Links in BEFORE but NOT in AFTER (pushed out by ranking): {len(pushed_out)}")
        for x in pushed_out:
            score = _score_link(x["text"], x["href"], urlparse(actual_url).netloc.lower())
            print(f"  score={score:+d}  {x['text'][:30]!r} → {x['href'][:60]}")

        print(f"\nLinks in AFTER but NOT in BEFORE (newly visible from deeper DOM): {len(newly_in)}")
        for i, x in enumerate(newly_in):
            print(f"  score={after_scores[after_links.index(x)]:+d}  {x['text'][:30]!r} → {x['href'][:60]}")

        # --- Key question: Floor Plans link present in both? ---
        fp_keywords = re.compile(r"floor.?plan|availability|pricing", re.I)
        print(f"\n{'─'*80}")
        print("Key links for discovery:")
        for label, link_list, score_list in [("BEFORE", before_links, [None]*len(before_links)),
                                              ("AFTER", after_links, after_scores)]:
            hits = [(i+1, x, (score_list[i] if score_list[i] is not None else "?"))
                    for i, x in enumerate(link_list)
                    if fp_keywords.search(x["text"]) or fp_keywords.search(x["href"])]
            if hits:
                for pos, x, sc in hits:
                    print(f"  {label} pos={pos:>2}  score={sc!s:>4}  {x['text'][:35]!r} → {x['href'][:60]}")
            else:
                print(f"  {label}: NO floor-plan/availability/pricing link found in top {MAX_LINKS}")


asyncio.run(main())
