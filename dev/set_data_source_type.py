"""Mark a domain and all its apartments with a data_source_type.

Usage:
    python dev/set_data_source_type.py <domain> <type>

Examples:
    python dev/set_data_source_type.py parkmerced.com unscrapeable
    python dev/set_data_source_type.py telegraphgardens.com unscrapeable
    python dev/set_data_source_type.py www.121tasman.com corporate_parent

Allowed types:
    brand_site           default — scrape normally
    corporate_parent     label only; redirect already handled via corporate_parent_url
    unscrapeable         site doesn't publish pricing; UI shows "no pricing published"
    aggregator_readonly  reserved, not yet implemented
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.apartment import Apartment
from app.models.site_registry import ScrapeSiteRegistry

VALID_TYPES = ("brand_site", "corporate_parent", "unscrapeable", "aggregator_readonly")


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    domain, dstype = sys.argv[1].lower(), sys.argv[2].lower()

    if dstype not in VALID_TYPES:
        print(f"ERROR: type must be one of {VALID_TYPES}")
        sys.exit(1)

    with SessionLocal() as db:
        reg = db.execute(
            select(ScrapeSiteRegistry).where(ScrapeSiteRegistry.domain == domain)
        ).scalar_one_or_none()

        if reg is None:
            print(f"ERROR: No registry row for domain '{domain}'")
            print("  Run scripts/populate_site_registry.py first, or check the domain spelling.")
            sys.exit(1)

        old_type = reg.data_source_type
        reg.data_source_type = dstype

        apts = db.execute(
            select(Apartment).where(Apartment.source_url.contains(domain))
        ).scalars().all()

        for apt in apts:
            apt.data_source_type = dstype

        db.commit()

        print(
            f"Marked '{domain}' as '{dstype}' "
            f"(was '{old_type}', {len(apts)} apartment(s) updated)"
        )
        for apt in apts:
            print(f"  apt_id={apt.id}  {apt.title}")


if __name__ == "__main__":
    main()
