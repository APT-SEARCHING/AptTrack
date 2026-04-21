"""Content-hash utility for the scraper short-circuit.

``compute_content_hash(html)`` strips noise from a page's raw HTML and returns
a SHA256 hex digest.  Two fetches of the same page that return the same digest
mean the pricing content almost certainly hasn't changed — safe to skip the
path-cache replay and the LLM entirely.

What is stripped (in order):
  1. <script>, <style>, <noscript> tags and their content
  2. HTML comments
  3. CSRF / nonce tokens  (name="csrf…", value="…", nonce="…")
  4. Session IDs in URLs  (PHPSESSID, jsessionid, sid=…)
  5. ISO-8601 timestamps  (server-rendered "Last updated: 2026-04-16T…")
  6. Unix epoch numbers   (13-digit ms timestamps in JS data blobs)
  7. Normalise whitespace (collapse runs, strip leading/trailing)

What is NOT stripped:
  - Price figures, floor-plan names, availability strings — the signal.
  - Structural HTML (divs, classes, hrefs) so that layout rearrangements
    are detected as a change (prompting a re-scrape).
"""

from __future__ import annotations

import re
from hashlib import sha256

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Noise patterns to strip before hashing
# ---------------------------------------------------------------------------

# CSRF / anti-forgery tokens embedded in inputs or meta tags
_RE_CSRF = re.compile(
    r'(value|content|data-token|nonce)\s*=\s*"[A-Za-z0-9+/=_\-]{16,}"',
    re.IGNORECASE,
)

# Session IDs in query strings or path segments
_RE_SESSION = re.compile(
    r"(PHPSESSID|jsessionid|sid|_csrf|__RequestVerificationToken)"
    r"[=\/][A-Za-z0-9%_\-]{8,}",
    re.IGNORECASE,
)

# ISO-8601 timestamps  e.g. 2026-04-16T10:32:00Z  or  2026-04-16T10:32:00+00:00
_RE_ISO_TS = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?",
    re.IGNORECASE,
)

# Unix epoch timestamps (13-digit ms precision, common in JS bundles/data blobs)
_RE_EPOCH_MS = re.compile(r"\b1[0-9]{12}\b")

# HTML comments  <!-- … -->
_RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def compute_content_hash(html: str) -> str:
    """Return a SHA256 hex digest of the pricing-relevant content in *html*.

    Parameters
    ----------
    html:
        Raw HTML string as returned by an HTTP GET of the apartment listing page.

    Returns
    -------
    str
        64-character lowercase hex string (SHA256 digest).
    """
    # 1. Remove <script>, <style>, <noscript> blocks entirely
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # 2. Work on the remaining HTML text (not the parsed tree) for regex passes
    cleaned = str(soup)

    # 3. Strip HTML comments
    cleaned = _RE_HTML_COMMENT.sub("", cleaned)

    # 4. Strip CSRF tokens / nonces
    cleaned = _RE_CSRF.sub("", cleaned)

    # 5. Strip session IDs
    cleaned = _RE_SESSION.sub("", cleaned)

    # 6. Strip ISO-8601 timestamps
    cleaned = _RE_ISO_TS.sub("", cleaned)

    # 7. Strip ms-epoch numbers
    cleaned = _RE_EPOCH_MS.sub("", cleaned)

    # 8. Normalise whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return sha256(cleaned.encode("utf-8", errors="replace")).hexdigest()
