"""Navigation path cache for the agentic scraper.

Stores the sequence of browser tool calls that successfully extracted data
from a site. On repeat visits the cached path is replayed using only browser
operations (zero LLM calls for extract_all_units paths), falling back to the
full agent loop if replay fails (e.g. after a site redesign).

Cache files live in a ``path_cache/`` subdirectory alongside this file
(one JSON file per URL, e.g. ``www_rentmiro_com__a8098c1a.json``).

Key format (v2): ``{domain}__{md5(path)[:8]}``
  - domain  — netloc lowercased, non-word chars replaced with ``_``
  - path    — URL path only (query string stripped), MD5-hashed, first 8 hex chars

Legacy key format (v1): ``{domain}`` only — files in this format are migrated
to v2 on first successful ``load_path`` call (see migration logic below).

Cache entries expire after ``CACHE_TTL_DAYS`` days without a successful use.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from hashlib import md5
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

CACHE_DIR = Path(__file__).parent / "path_cache"
CACHE_TTL_DAYS = 30

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _url_key(url: str) -> str:
    """Convert a URL to a filesystem-safe cache key: ``{domain}__{md5(path)[:8]}``.

    Query string is stripped; only scheme + domain + path contribute to the key.

    Examples
    --------
    ``https://www.rentmiro.com/floorplans``
        →  ``www_rentmiro_com__a8098c1a``
    ``https://www.themarc-pa.com/apartments/ca/palo-alto/floor-plans``
        →  ``www_themarc_pa_com__3f110876``
    ``https://www.themarc-pa.com/apartments/ca/mountain-view/floor-plans``
        →  ``www_themarc_pa_com__9d3b2f01``  (different hash — no collision)
    """
    parsed = urlparse(url)
    domain = re.sub(r"[^\w]", "_", parsed.netloc.lower())
    path_hash = md5(parsed.path.encode()).hexdigest()[:8]
    return f"{domain}__{path_hash}"


def _legacy_key(url: str) -> str:
    """Old domain-only key — used exclusively for migration fallback in load_path."""
    domain = re.sub(r"https?://", "", url).split("/")[0]
    return re.sub(r"[^\w]", "_", domain)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_entry(key: str, cache_file: Path) -> Optional[Dict[str, Any]]:
    """Read and TTL-check a cache file.  Returns the entry dict or ``None``."""
    if not cache_file.exists():
        return None
    try:
        entry: Dict[str, Any] = json.loads(cache_file.read_text())
        last_success_str = entry.get("last_success", "2000-01-01T00:00:00+00:00")
        last_success = datetime.fromisoformat(last_success_str)
        if last_success.tzinfo is None:
            last_success = last_success.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - last_success
        if age > timedelta(days=CACHE_TTL_DAYS):
            logger.info("Path cache expired for %s (age=%d days)", key, age.days)
            return None
        return entry
    except Exception as exc:
        logger.warning("Path cache read error for %s: %s", key, exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_path(url: str) -> Optional[Dict[str, Any]]:
    """Return the cached path entry for *url*, or ``None`` if absent / expired.

    Lookup order
    ------------
    1. New v2 key (``{domain}__{md5(path)[:8]}``) — fast path for all new entries.
    2. Legacy v1 key (``{domain}`` only) — migration grace period.
       Only migrates if the stored URL matches *url* exactly (collision guard).
       On match: writes v2 file, deletes v1 file, returns entry.
    """
    # 1. New format
    key = _url_key(url)
    entry = _read_entry(key, CACHE_DIR / f"{key}.json")
    if entry is not None:
        return entry

    # 2. Legacy format — migrate on hit
    legacy_key = _legacy_key(url)
    legacy_file = CACHE_DIR / f"{legacy_key}.json"
    entry = _read_entry(legacy_key, legacy_file)
    if entry is None:
        return None

    # Collision guard: don't let a legacy entry for URL A serve URL B
    if entry.get("url") != url:
        logger.info(
            "Path cache legacy collision: %s stores %r, requested %r — skipping migration",
            legacy_key, entry.get("url"), url,
        )
        return None

    # Migrate: persist under new key, remove old file
    logger.info("Migrating path cache %s → %s", legacy_key, key)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(
        json.dumps(entry, indent=2, ensure_ascii=False)
    )
    legacy_file.unlink()
    return entry


def save_path(url: str, steps: List[Dict[str, Any]], apartment_name: str) -> None:
    """Write or update the cache entry for *url*."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _url_key(url)
    cache_file = CACHE_DIR / f"{key}.json"

    # Preserve previous success count
    prev_count = 0
    if cache_file.exists():
        try:
            prev_count = json.loads(cache_file.read_text()).get("success_count", 0)
        except Exception:
            pass

    entry: Dict[str, Any] = {
        "url": url,
        "domain": key,
        "steps": steps,
        "apartment_name": apartment_name,
        "last_success": datetime.now(timezone.utc).isoformat(),
        "success_count": prev_count + 1,
    }
    cache_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
    logger.info(
        "Path cache saved: %s (%d steps, success_count=%d)",
        key, len(steps), entry["success_count"],
    )


def invalidate_path(url: str) -> None:
    """Delete the cache entry for *url* (e.g. after a failed replay).

    Tries both v2 and legacy v1 filenames since an entry could still be in the
    old format if it was never loaded (and thus never migrated).
    """
    key = _url_key(url)
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        cache_file.unlink()
        logger.info("Path cache invalidated: %s", key)

    legacy_key = _legacy_key(url)
    legacy_file = CACHE_DIR / f"{legacy_key}.json"
    if legacy_file.exists():
        # Only delete the legacy file if it actually belongs to this URL
        try:
            stored_url = json.loads(legacy_file.read_text()).get("url")
            if stored_url == url:
                legacy_file.unlink()
                logger.info("Path cache invalidated (legacy): %s", legacy_key)
        except Exception:
            pass
