"""Navigation path cache for the agentic scraper.

Stores the sequence of browser tool calls that successfully extracted data
from a site. On repeat visits the cached path is replayed using only browser
operations (zero LLM calls for extract_all_units paths), falling back to the
full agent loop if replay fails (e.g. after a site redesign).

Cache files live in a ``path_cache/`` subdirectory alongside this file
(one JSON file per domain, e.g. ``www_rentmiro_com.json``).

Cache entries expire after ``CACHE_TTL_DAYS`` days without a successful use.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

CACHE_DIR = Path(__file__).parent / "path_cache"
CACHE_TTL_DAYS = 30

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _domain_key(url: str) -> str:
    """Convert a URL to a filesystem-safe cache key derived from its domain.

    Examples
    --------
    ``https://www.rentmiro.com/floorplans``  →  ``www_rentmiro_com``
    """
    domain = re.sub(r"https?://", "", url).split("/")[0]
    return re.sub(r"[^\w]", "_", domain)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_path(url: str) -> Optional[Dict[str, Any]]:
    """Return the cached path entry for *url*, or ``None`` if absent / expired."""
    key = _domain_key(url)
    cache_file = CACHE_DIR / f"{key}.json"
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


def save_path(url: str, steps: List[Dict[str, Any]], apartment_name: str) -> None:
    """Write or update the cache entry for *url*.

    Only caches paths that end with ``extract_all_units`` — the only action
    whose result can be replayed without any LLM call.  Steps recorded *after*
    the last ``extract_all_units`` (e.g., the agent verifying its findings) are
    trimmed because they are not needed for replay and would break it.
    """
    # Find the last extract_all_units index and truncate there (inclusive).
    last_eau = next(
        (i for i in reversed(range(len(steps))) if steps[i]["action"] == "extract_all_units"),
        None,
    )
    if last_eau is None:
        logger.info(
            "Path cache skipped for %s: no extract_all_units step found "
            "(site needs LLM for interpretation; cannot replay offline)",
            _domain_key(url),
        )
        return

    steps = steps[: last_eau + 1]  # trim anything after the last EAU

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _domain_key(url)
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
        "Path cache saved: %s (%d steps → extract_all_units, success_count=%d)",
        key, len(steps), entry["success_count"],
    )


def invalidate_path(url: str) -> None:
    """Delete the cache entry for *url* (e.g. after a failed replay)."""
    key = _domain_key(url)
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        cache_file.unlink()
        logger.info("Path cache invalidated: %s", key)
