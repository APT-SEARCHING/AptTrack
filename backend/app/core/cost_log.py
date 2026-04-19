"""Append-only cost log for API spend tracking.

Primary storage: ``api_cost_log`` Postgres table (survives Railway redeploys).
Fallback: ``logs/cost_log.jsonl`` at repo root (used when db is unavailable or
not provided — e.g. dry-run CLI mode or unexpected DB error).

Usage
-----
Pass ``db`` (a live SQLAlchemy Session) whenever one is available:

    append_scraper_entry(name=..., url=..., outcome=..., db=db)

Omit ``db`` (or pass ``None``) to write JSONL only — useful in dry-run or
test contexts where no session exists.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Fallback JSONL file (ephemeral on Railway, but better than losing the entry)
_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # backend/app/core → repo root
_LOG_FILE = _REPO_ROOT / "logs" / "cost_log.jsonl"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def append_scraper_entry(
    *,
    name: str,
    url: str,
    outcome: str,           # "ok" | "no_data" | "error" | "cache_hit"
    input_tok: int = 0,
    output_tok: int = 0,
    cost_usd: float = 0.0,
    db: Optional["Session"] = None,
) -> None:
    """Log one scraper run (one apartment).

    Parameters
    ----------
    db:
        Live SQLAlchemy session.  When provided, writes to ``api_cost_log``
        table and commits.  On commit failure falls back to JSONL.
        When ``None``, writes JSONL only (dry-run / no-session contexts).
    """
    row = dict(
        source="scraper",
        name=name,
        url=url,
        outcome=outcome,
        input_tok=input_tok,
        output_tok=output_tok,
        api_calls=0,
        cache_hits=0,
        cost_usd=round(cost_usd, 6),
    )
    _write(row, db=db)


def append_google_maps_entry(
    *,
    location: str,
    total_places: int,
    api_calls: int,
    cache_hits: int,
    failed: int,
    cost_usd: float,
    db: Optional["Session"] = None,
) -> None:
    """Log one Google Maps import run (one city/location).

    Parameters
    ----------
    db:
        Live SQLAlchemy session.  Same semantics as ``append_scraper_entry``.
    """
    row = dict(
        source="google_maps",
        name=location,
        url=None,
        outcome="ok" if failed == 0 else "partial",
        input_tok=0,
        output_tok=0,
        api_calls=api_calls,
        cache_hits=cache_hits,
        cost_usd=round(cost_usd, 6),
    )
    _write(row, db=db)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _write(row: dict, db: Optional["Session"]) -> None:
    """Write cost entry to DB (primary) with JSONL fallback."""
    if db is not None:
        try:
            from app.models.api_cost_log import ApiCostLog
            entry = ApiCostLog(
                source=row["source"],
                name=row.get("name"),
                url=row.get("url"),
                outcome=row["outcome"],
                input_tok=row.get("input_tok", 0),
                output_tok=row.get("output_tok", 0),
                api_calls=row.get("api_calls", 0),
                cache_hits=row.get("cache_hits", 0),
                cost_usd=row["cost_usd"],
            )
            db.add(entry)
            db.commit()
            return
        except Exception:
            logger.exception("cost_log: DB write failed, falling back to JSONL")
            try:
                db.rollback()
            except Exception:
                pass

    # JSONL fallback (always used when db=None, also used after DB failure)
    _write_jsonl(row)


def _write_jsonl(row: dict) -> None:
    """Append one JSON line to the fallback log file."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **row,
        # Add total_tok for scraper rows (kept for backward compatibility with dev/cost_summary.py)
        "total_tok": row.get("input_tok", 0) + row.get("output_tok", 0),
    }
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("cost_log: JSONL fallback also failed: %s", exc)
