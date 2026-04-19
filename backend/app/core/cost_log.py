"""Append-only cost log for API spend tracking.

Each operation (scraper run, Google Maps import) appends one JSON line to
``logs/cost_log.jsonl`` at the repo root.  The file is human-readable and
can be queried with ``dev/cost_summary.py``.

Entry format
------------
{
    "ts":          "2026-04-19T10:23:45+00:00",  # UTC ISO-8601
    "source":      "scraper" | "google_maps",
    "name":        str,          # apartment name or city searched
    "url":         str | null,   # scraper: source URL; google_maps: null
    "outcome":     str,          # "ok" | "no_data" | "error" | "cache_hit"
    "input_tok":   int | null,   # scraper only
    "output_tok":  int | null,   # scraper only
    "total_tok":   int | null,   # scraper only
    "api_calls":   int | null,   # google_maps: Place Details calls made
    "cache_hits":  int | null,   # google_maps: Place Details served from cache
    "cost_usd":    float         # calculated cost for this entry
}
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Resolve log file relative to repo root regardless of CWD
_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # backend/app/core → repo root
_LOG_FILE = _REPO_ROOT / "logs" / "cost_log.jsonl"


def append_scraper_entry(
    *,
    name: str,
    url: str,
    outcome: str,           # "ok" | "no_data" | "error" | "cache_hit"
    input_tok: int = 0,
    output_tok: int = 0,
    cost_usd: float = 0.0,
) -> None:
    """Log one scraper run (one apartment)."""
    _write({
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "scraper",
        "name": name,
        "url": url,
        "outcome": outcome,
        "input_tok": input_tok,
        "output_tok": output_tok,
        "total_tok": input_tok + output_tok,
        "api_calls": None,
        "cache_hits": None,
        "cost_usd": round(cost_usd, 6),
    })


def append_google_maps_entry(
    *,
    location: str,
    total_places: int,
    api_calls: int,
    cache_hits: int,
    failed: int,
    cost_usd: float,
) -> None:
    """Log one Google Maps import run (one city/location)."""
    _write({
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "google_maps",
        "name": location,
        "url": None,
        "outcome": "ok" if failed == 0 else "partial",
        "input_tok": None,
        "output_tok": None,
        "total_tok": None,
        "api_calls": api_calls,
        "cache_hits": cache_hits,
        "cost_usd": round(cost_usd, 6),
    })


def _write(entry: dict) -> None:
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("cost_log: failed to write entry: %s", exc)
