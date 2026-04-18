from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import asc, case, func, select, text
from sqlalchemy.orm import Session, aliased

from app.core.limiter import limiter
from app.db.session import get_db
from app.models.apartment import Apartment, Plan
from app.schemas.apartment import SimilarApartment, SimilarResponse

router = APIRouter()


def _python_median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 == 1 else (s[mid - 1] + s[mid]) / 2


@router.get("/apartments/{apartment_id}/similar", response_model=SimilarResponse)
@limiter.limit("60/minute")
def get_similar_apartments(
    request: Request,
    apartment_id: int,
    db: Session = Depends(get_db),
) -> SimilarResponse:
    # ── Step 1: confirm target exists ─────────────────────────────────────────
    target_apt = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if target_apt is None:
        raise HTTPException(status_code=404, detail="Apartment not found")

    city: str = target_apt.city

    # ── Step 2: primary plan = cheapest available plan with a non-null price ──
    primary = db.execute(
        select(Plan.bedrooms, Plan.price)
        .where(
            Plan.apartment_id == apartment_id,
            Plan.is_available.is_(True),
            Plan.price.isnot(None),
        )
        .order_by(asc(Plan.price))
        .limit(1)
    ).first()

    if primary is None:
        # No priced plans — nothing to anchor similarity against
        return SimilarResponse()

    target_beds: float = primary.bedrooms
    target_price: float = primary.price

    # ── Step 3: city-wide median for same bedroom count (computed in Python) ──
    city_prices: List[float] = list(
        db.execute(
            select(Plan.price)
            .join(Apartment, Apartment.id == Plan.apartment_id)
            .where(
                Apartment.city == city,
                Plan.bedrooms == target_beds,
                Plan.is_available.is_(True),
                Apartment.is_available.is_(True),
                Plan.price.isnot(None),
            )
        )
        .scalars()
        .all()
    )
    city_median = _python_median(city_prices)

    pct_vs_median: Optional[float] = None
    if city_median is not None and city_median > 0:
        pct_vs_median = round((target_price - city_median) / city_median, 4)

    # ── Step 4: similar apartments ────────────────────────────────────────────
    p_match = aliased(Plan, name="p_match")
    p_all = aliased(Plan, name="p_all")

    rows = (
        db.execute(
            select(
                Apartment.id,
                Apartment.title,
                Apartment.city,
                Apartment.state,
                Apartment.address,
                Apartment.source_url,
                Apartment.latitude,
                Apartment.longitude,
                func.min(p_all.price).label("min_price"),
                func.max(p_all.price).label("max_price"),
                func.min(p_all.bedrooms).label("min_beds"),
                func.max(p_all.bedrooms).label("max_beds"),
                func.count(p_all.id).label("plan_count"),
                func.sum(case((p_all.is_available == True, 1), else_=0)).label("available_count"),  # noqa: E712
                func.min(func.abs(p_match.price - target_price)).label("price_diff"),
            )
            .join(p_match, Apartment.id == p_match.apartment_id)
            .join(p_all, Apartment.id == p_all.apartment_id)
            .where(
                Apartment.id != apartment_id,
                Apartment.city == city,
                Apartment.is_available.is_(True),
                p_match.is_available.is_(True),
                p_match.bedrooms == target_beds,
                p_match.price.between(target_price * 0.75, target_price * 1.25),
            )
            .group_by(
                Apartment.id,
                Apartment.title,
                Apartment.city,
                Apartment.state,
                Apartment.address,
                Apartment.source_url,
                Apartment.latitude,
                Apartment.longitude,
            )
            .order_by(text("price_diff"))
            .limit(5)
        )
        .mappings()
        .all()
    )

    similar = [
        SimilarApartment(
            id=row["id"],
            title=row["title"],
            city=row["city"],
            location=(
                f"{row['address']}, {row['city']}, {row['state']}"
                if row["address"]
                else f"{row['city']}, {row['state']}"
            ),
            source_url=row["source_url"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            min_price=row["min_price"],
            max_price=row["max_price"],
            min_beds=row["min_beds"],
            max_beds=row["max_beds"],
            plan_count=row["plan_count"],
            available_count=row["available_count"],
        )
        for row in rows
    ]

    return SimilarResponse(
        city_median_price=city_median,
        pct_vs_median=pct_vs_median,
        similar=similar,
    )
