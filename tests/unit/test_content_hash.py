"""Tests for compute_content_hash — scraper content-hash short-circuit."""
import pytest

from app.services.scraper_agent.content_hash import compute_content_hash


BASE_HTML = """
<html>
<head><title>Miro Apartments</title></head>
<body>
  <div class="floorplan">
    <h2>Studio A</h2>
    <span class="price">$2,450/mo</span>
    <span class="availability">Available Now</span>
  </div>
  <div class="floorplan">
    <h2>1BR Classic</h2>
    <span class="price">$2,950/mo</span>
    <span class="availability">Available Jun 1</span>
  </div>
</body>
</html>
"""


def test_identical_html_same_hash():
    assert compute_content_hash(BASE_HTML) == compute_content_hash(BASE_HTML)


def test_whitespace_differences_same_hash():
    compact = BASE_HTML.replace("  ", "").replace("\n", " ")
    assert compute_content_hash(BASE_HTML) == compute_content_hash(compact)


def test_csrf_token_difference_same_hash():
    html_a = BASE_HTML + '<input type="hidden" name="csrf_token" value="abc123xyz789abc1">'
    html_b = BASE_HTML + '<input type="hidden" name="csrf_token" value="zzz999qqq111rrr2">'
    assert compute_content_hash(html_a) == compute_content_hash(html_b)


def test_nonce_difference_same_hash():
    html_a = BASE_HTML.replace("<head>", '<head><meta content="aaabbbccc111222333">')
    html_b = BASE_HTML.replace("<head>", '<head><meta content="zzzxxxyyy999888777">')
    assert compute_content_hash(html_a) == compute_content_hash(html_b)


def test_iso_timestamp_difference_same_hash():
    html_a = BASE_HTML + "<span>Updated: 2026-04-10T08:00:00Z</span>"
    html_b = BASE_HTML + "<span>Updated: 2026-04-19T15:30:00+00:00</span>"
    assert compute_content_hash(html_a) == compute_content_hash(html_b)


def test_html_comment_difference_same_hash():
    html_a = BASE_HTML + "<!-- build: v1.0.1 ts=1713510000000 -->"
    html_b = BASE_HTML + "<!-- build: v1.0.2 ts=1713596400000 -->"
    assert compute_content_hash(html_a) == compute_content_hash(html_b)


def test_script_tag_difference_same_hash():
    html_a = BASE_HTML + "<script>var X = 1;</script>"
    html_b = BASE_HTML + "<script>var X = 99999;</script>"
    assert compute_content_hash(html_a) == compute_content_hash(html_b)


def test_price_change_different_hash():
    html_cheaper = BASE_HTML.replace("$2,450/mo", "$2,200/mo")
    assert compute_content_hash(BASE_HTML) != compute_content_hash(html_cheaper)


def test_new_floorplan_different_hash():
    html_extra = BASE_HTML.replace(
        "</body>",
        '<div class="floorplan"><h2>2BR Deluxe</h2><span class="price">$3,500/mo</span></div></body>',
    )
    assert compute_content_hash(BASE_HTML) != compute_content_hash(html_extra)


def test_availability_change_different_hash():
    html_waitlist = BASE_HTML.replace("Available Now", "Waitlist")
    assert compute_content_hash(BASE_HTML) != compute_content_hash(html_waitlist)


def test_returns_64_char_hex():
    h = compute_content_hash(BASE_HTML)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_empty_html_does_not_raise():
    h = compute_content_hash("")
    assert len(h) == 64
