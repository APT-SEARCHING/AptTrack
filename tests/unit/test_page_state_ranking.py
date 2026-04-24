"""Unit tests for _page_state link ranking (rank-then-truncate).

_page_state requires a live browser, so we test the two independently-importable
pieces: _score_link() and the rank-then-truncate pipeline replicated as a helper.
"""
from __future__ import annotations

import re
from typing import List

from bs4 import BeautifulSoup

from app.services.scraper_agent.browser_tools import (
    MAX_LINKS,
    _score_link,
)


# ---------------------------------------------------------------------------
# Helper: replicate the _page_state link pipeline without a browser
# ---------------------------------------------------------------------------

def _collect_ranked_links(html: str, page_url: str, max_links: int = MAX_LINKS) -> List[dict]:
    """Replicate the rank-then-truncate link collection from _page_state."""
    from urllib.parse import urlparse
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "meta", "head"]):
        tag.decompose()
    base_domain = urlparse(page_url).netloc.lower()
    scored = []
    for a in soup.find_all("a", href=True):
        link_text = a.get_text(strip=True)
        if not link_text:
            continue
        href = str(a["href"])
        scored.append((_score_link(link_text, href, base_domain),
                       {"text": link_text[:80], "href": href[:150]}))
    scored.sort(key=lambda x: -x[0])
    return [entry for _, entry in scored[:max_links]]


def _make_html(links: list[tuple[str, str]]) -> str:
    """Build minimal HTML with the given (text, href) anchor pairs."""
    items = "".join(f'<a href="{href}">{text}</a>\n' for text, href in links)
    return f"<html><body>{items}</body></html>"


# ---------------------------------------------------------------------------
# Test 1 — Floor Plans link beats social links even when socials appear first
# ---------------------------------------------------------------------------

def test_floor_plans_beats_social_links():
    """'Floor Plans' at DOM position 21 must appear in top-20; socials must not."""
    # 3 socials at top, then noise, then Floor Plans buried at position 21
    links = (
        [("Instagram", "https://instagram.com/revela")] * 3
        + [("Home", "/"), ("Gallery", "/gallery"), ("About Us", "/about"),
           ("Schedule a Tour", "/schedule"), ("Apply Now", "/apply"),
           ("Contact Us", "/contact"), ("Privacy Policy", "/privacy"),
           ("Terms of Use", "/terms"), ("Accessibility", "/accessibility"),
           ("Fair Housing", "/fair-housing"), ("Sitemap", "/sitemap"),
           ("Resident Login", "/login"), ("Refer a Friend", "/refer"),
           ("Blog", "/blog"), ("FAQs", "/faqs"), ("Pets", "/pets"),
           ("Parking", "/parking"), ("Neighborhood", "/neighborhood"),
           ("Photos", "/photos"), ("Map", "/map")]
        + [("Floor Plans", "/floorplans")]   # position 25 in DOM
        + [("Specials", "/specials"), ("Amenities", "/amenities")]
    )
    html = _make_html(links)
    result = _collect_ranked_links(html, "https://www.revela.com/")
    texts = [r["text"] for r in result]

    assert "Floor Plans" in texts, "'Floor Plans' must appear in top-20"
    assert "Instagram" not in texts, "Instagram must be pushed out by negative score"
    assert len(result) == MAX_LINKS


# ---------------------------------------------------------------------------
# Test 2 — Relevant href wins even with generic link text
# ---------------------------------------------------------------------------

def test_plans_href_matched_without_text():
    """/floorplans href scores highly even with generic 'view →' text."""
    links = [
        ("Home", "/"),
        ("view →", "/floorplans"),
        ("Contact", "/contact"),
    ]
    html = _make_html(links)
    result = _collect_ranked_links(html, "https://example.com/")
    hrefs = [r["href"] for r in result]
    assert "/floorplans" in hrefs


def test_availability_href_scores_well():
    """/availability href gets a positive score."""
    score = _score_link("Check it out", "/availability", "example.com")
    assert score > 0


# ---------------------------------------------------------------------------
# Test 3 — Scoring is deterministic (same inputs → same score)
# ---------------------------------------------------------------------------

def test_scoring_symmetric():
    """Same (text, href, domain) produces the same score regardless of call order."""
    s1 = _score_link("Floor Plans", "/floorplans", "example.com")
    s2 = _score_link("Floor Plans", "/floorplans", "example.com")
    assert s1 == s2


# ---------------------------------------------------------------------------
# Test 4 — No crash when base_domain is empty
# ---------------------------------------------------------------------------

def test_no_crash_on_missing_page_context():
    """_score_link with base_domain='' must not raise."""
    score = _score_link("Floor Plans", "/floorplans", "")
    assert isinstance(score, int)


# ---------------------------------------------------------------------------
# Test 5 — Stable sort for ties (DOM order preserved)
# ---------------------------------------------------------------------------

def test_stable_sort_for_ties():
    """Two links with equal scores retain their original DOM order."""
    # Two generic links with no positive/negative signals — both score 0
    links = [
        ("Alpha", "/alpha"),
        ("Beta", "/beta"),
    ]
    html = _make_html(links)
    result = _collect_ranked_links(html, "https://example.com/")
    assert result[0]["text"] == "Alpha"
    assert result[1]["text"] == "Beta"


# ---------------------------------------------------------------------------
# Test 6 — mailto: links are penalised and pushed out
# ---------------------------------------------------------------------------

def test_mailto_excluded():
    """mailto: link scores very negatively and is pushed below 20 real links."""
    padding = [(f"Page {i}", f"/page-{i}") for i in range(20)]
    links = padding + [("Email Us", "mailto:info@example.com")]
    html = _make_html(links)
    result = _collect_ranked_links(html, "https://example.com/")
    hrefs = [r["href"] for r in result]
    assert "mailto:info@example.com" not in hrefs, "mailto: must be pushed out"


# ---------------------------------------------------------------------------
# Score sanity checks
# ---------------------------------------------------------------------------

def test_floor_plans_text_scores_highest():
    """'Floor Plans' link text produces the maximum positive text score."""
    s_fp = _score_link("Floor Plans", "/other", "example.com")
    s_home = _score_link("Home", "/", "example.com")
    assert s_fp > s_home


def test_social_href_scores_very_negative():
    """Instagram href produces a strongly negative score."""
    score = _score_link("Follow us", "https://instagram.com/revela", "revela.com")
    assert score < -50


def test_external_non_platform_penalised():
    """External link to non-platform domain gets -20 penalty."""
    score_internal = _score_link("Gallery", "/gallery", "example.com")
    score_external = _score_link("Gallery", "https://other.com/gallery", "example.com")
    assert score_internal > score_external


def test_platform_embed_not_penalised():
    """SightMap / RentCafe external links skip the external-domain penalty."""
    score = _score_link("View Map", "https://sightmap.com/embed/xyz123", "example.com")
    # Should not have the -20 external penalty
    score_plain_external = _score_link("View Map", "https://random-cdn.com/embed/xyz123", "example.com")
    assert score > score_plain_external
