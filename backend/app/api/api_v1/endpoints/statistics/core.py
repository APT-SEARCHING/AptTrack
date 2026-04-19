import threading
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from app.core.limiter import limiter
from app.db.session import get_db
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.schemas.apartment import CheapestItem, MedianByCityBedsResponse, PriceTrend, TopDropItem
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import Date, Float, cast, func, select, text
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# In-process cache for median-by-city-beds (24 h TTL)
# ---------------------------------------------------------------------------

_median_cache: dict = {}
_median_lock = threading.Lock()
_MEDIAN_TTL = timedelta(hours=24)

router = APIRouter()


@router.get("/stats/top-drops", response_model=List[TopDropItem])
@limiter.limit("60/minute")
def get_top_drops(
    request: Request,
    db: Session = Depends(get_db),
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(5, ge=1, le=20),
):
    """Plans with the biggest price drop (%) over the last N days.

    Returns at most `limit` results ordered by drop_pct descending.
    Returns an empty list when there is insufficient price history.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Latest price per plan within the window
    latest_sq = (
        select(
            PlanPriceHistory.plan_id.label("plan_id"),
            PlanPriceHistory.price.label("price"),
            func.row_number().over(
                partition_by=PlanPriceHistory.plan_id,
                order_by=PlanPriceHistory.recorded_at.desc(),
            ).label("rn"),
        )
        .where(PlanPriceHistory.recorded_at >= cutoff)
        .subquery()
    )

    # Earliest price per plan within the window (the "previous" baseline)
    earliest_sq = (
        select(
            PlanPriceHistory.plan_id.label("plan_id"),
            PlanPriceHistory.price.label("price"),
            func.row_number().over(
                partition_by=PlanPriceHistory.plan_id,
                order_by=PlanPriceHistory.recorded_at.asc(),
            ).label("rn"),
        )
        .where(PlanPriceHistory.recorded_at >= cutoff)
        .subquery()
    )

    drop_expr = (
        cast(earliest_sq.c.price - latest_sq.c.price, Float)
        / earliest_sq.c.price * 100
    )

    rows = db.execute(
        select(
            latest_sq.c.plan_id,
            Plan.apartment_id,
            Apartment.title.label("apartment_title"),
            Plan.name.label("plan_name"),
            earliest_sq.c.price.label("previous_price"),
            latest_sq.c.price.label("current_price"),
            drop_expr.label("drop_pct"),
        )
        .where(latest_sq.c.rn == 1)
        .where(earliest_sq.c.rn == 1)
        .join(earliest_sq, latest_sq.c.plan_id == earliest_sq.c.plan_id)
        .join(Plan, Plan.id == latest_sq.c.plan_id)
        .join(Apartment, Apartment.id == Plan.apartment_id)
        .where(latest_sq.c.price < earliest_sq.c.price)
        .where(Plan.is_available.is_(True))
        .order_by(drop_expr.desc())
        .limit(limit)
    ).all()

    return [
        {
            "plan_id": r.plan_id,
            "apartment_id": r.apartment_id,
            "apartment_title": r.apartment_title,
            "plan_name": r.plan_name,
            "previous_price": r.previous_price,
            "current_price": r.current_price,
            "drop_pct": round(r.drop_pct, 1),
        }
        for r in rows
    ]


@router.get("/stats/cheapest", response_model=List[CheapestItem])
@limiter.limit("60/minute")
def get_cheapest(
    request: Request,
    db: Session = Depends(get_db),
    city: Optional[str] = None,
    bedrooms: Optional[float] = None,
    limit: int = Query(5, ge=1, le=20),
):
    """Cheapest currently-available plans matching optional city/bedrooms filters."""
    stmt = (
        select(
            Plan.id.label("plan_id"),
            Plan.apartment_id,
            Apartment.title.label("apartment_title"),
            Plan.name.label("plan_name"),
            Plan.price,
            Plan.bedrooms,
            Plan.area_sqft,
        )
        .join(Apartment, Apartment.id == Plan.apartment_id)
        .where(Plan.is_available.is_(True))
        .where(Plan.price.is_not(None))
    )
    if city:
        stmt = stmt.where(func.lower(Apartment.city) == city.lower())
    if bedrooms is not None:
        stmt = stmt.where(Plan.bedrooms == bedrooms)
    stmt = stmt.order_by(Plan.price.asc()).limit(limit)

    rows = db.execute(stmt).all()
    return [
        {
            "plan_id": r.plan_id,
            "apartment_id": r.apartment_id,
            "apartment_title": r.apartment_title,
            "plan_name": r.plan_name,
            "price": r.price,
            "bedrooms": r.bedrooms,
            "area_sqft": r.area_sqft,
        }
        for r in rows
    ]


@router.get("/stats/median-by-city-beds", response_model=MedianByCityBedsResponse)
@limiter.limit("60/minute")
def get_median_by_city_beds(
    request: Request,
    city: str,
    bedrooms: float,
    db: Session = Depends(get_db),
):
    """Median asking price for city + bedroom count, cached 24 h in-process.

    Uses ``percentile_cont`` on Postgres; falls back to a Python sort-and-split
    on SQLite (test environment).
    """
    key = (city.lower(), bedrooms)
    now = datetime.now(timezone.utc)

    with _median_lock:
        entry = _median_cache.get(key)
        if entry and now < entry["expires"]:
            return MedianByCityBedsResponse(
                city=city,
                bedrooms=bedrooms,
                median=entry["median"],
                count=entry["count"],
            )

    median_val, count_val = _compute_median(city, bedrooms, db)

    with _median_lock:
        _median_cache[key] = {
            "median": median_val,
            "count": count_val,
            "expires": now + _MEDIAN_TTL,
        }

    return MedianByCityBedsResponse(
        city=city, bedrooms=bedrooms, median=median_val, count=count_val
    )


def _compute_median(city: str, bedrooms: float, db: Session) -> Tuple[Optional[float], int]:
    """Compute (median, count). Postgres path first, SQLite fallback for tests."""
    try:
        row = db.execute(
            text(
                """
                SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY p.price),
                       count(*)
                FROM plans p
                JOIN apartments a ON p.apartment_id = a.id
                WHERE lower(a.city) = lower(:city)
                  AND p.bedrooms = :bedrooms
                  AND p.is_available = true
                  AND p.price IS NOT NULL
                """
            ),
            {"city": city, "bedrooms": float(bedrooms)},
        ).first()
        return (row[0], int(row[1])) if row else (None, 0)
    except Exception:
        # SQLite (test env) — percentile_cont not supported
        prices = sorted(
            db.execute(
                select(Plan.price)
                .join(Apartment, Apartment.id == Plan.apartment_id)
                .where(
                    func.lower(Apartment.city) == city.lower(),
                    Plan.bedrooms == bedrooms,
                    Plan.is_available.is_(True),
                    Plan.price.is_not(None),
                )
            )
            .scalars()
            .all()
        )
        n = len(prices)
        if n == 0:
            return None, 0
        mid = n // 2
        median = prices[mid] if n % 2 == 1 else (prices[mid - 1] + prices[mid]) / 2
        return median, n


@router.get("/stats/price-trends", response_model=List[PriceTrend])
@limiter.limit("60/minute")
def get_price_trends(
    request: Request,
    db: Session = Depends(get_db),
    days: int = 30,
    city: Optional[str] = None,
    bedrooms: Optional[float] = None,
):
    start_date = datetime.now() - timedelta(days=days)

    stmt = (
        select(
            cast(PlanPriceHistory.recorded_at, Date).label("date"),
            func.avg(PlanPriceHistory.price).label("avg_price"),
        )
        .join(Plan)
        .join(Apartment)
    )

    if city:
        stmt = stmt.where(Apartment.city.ilike(f"%{city}%"))
    if bedrooms is not None:
        stmt = stmt.where(Plan.bedrooms == bedrooms)

    stmt = (
        stmt.where(PlanPriceHistory.recorded_at >= start_date)
        .group_by(cast(PlanPriceHistory.recorded_at, Date))
        .order_by(cast(PlanPriceHistory.recorded_at, Date))
    )
    result = db.execute(stmt).all()
    return [{"date": date, "avg_price": avg_price} for date, avg_price in result]


@router.get("/stats/apartments-by-city", response_model=List[dict])
@limiter.limit("60/minute")
def get_apartments_by_city(
    request: Request,
    db: Session = Depends(get_db),
):
    result = db.execute(
        select(Apartment.city, func.count(Apartment.id).label("count"))
        .group_by(Apartment.city)
    ).all()
    return [{"city": city, "count": count} for city, count in result]


@router.get("/stats/apartments-by-property-type", response_model=List[dict])
@limiter.limit("60/minute")
def get_apartments_by_property_type(
    request: Request,
    db: Session = Depends(get_db),
):
    result = db.execute(
        select(Apartment.property_type, func.count(Apartment.id).label("count"))
        .group_by(Apartment.property_type)
    ).all()
    return [{"property_type": pt, "count": count} for pt, count in result]


@router.get("/stats/average-price-by-bedrooms", response_model=List[dict])
@limiter.limit("60/minute")
def get_average_price_by_bedrooms(
    request: Request,
    db: Session = Depends(get_db),
    city: Optional[str] = None,
):
    stmt = (
        select(Plan.bedrooms, func.avg(Plan.price).label("avg_price"))
        .join(Apartment)
    )
    if city:
        stmt = stmt.where(Apartment.city.ilike(f"%{city}%"))
    stmt = stmt.group_by(Plan.bedrooms).order_by(Plan.bedrooms)
    result = db.execute(stmt).all()
    return [{"bedrooms": bedrooms, "avg_price": avg_price} for bedrooms, avg_price in result]


@router.get("/stats/plans-by-bedrooms", response_model=List[dict])
@limiter.limit("60/minute")
def get_plans_by_bedrooms(
    request: Request,
    db: Session = Depends(get_db),
):
    result = db.execute(
        select(Plan.bedrooms, func.count(Plan.id).label("count"))
        .group_by(Plan.bedrooms)
        .order_by(Plan.bedrooms)
    ).all()
    return [{"bedrooms": bedrooms, "count": count} for bedrooms, count in result]


@router.get("/stats/average-area-by-bedrooms", response_model=List[dict])
@limiter.limit("60/minute")
def get_average_area_by_bedrooms(
    request: Request,
    db: Session = Depends(get_db),
    city: Optional[str] = None,
):
    stmt = (
        select(Plan.bedrooms, func.avg(Plan.area_sqft).label("avg_area"))
        .join(Apartment)
    )
    if city:
        stmt = stmt.where(Apartment.city.ilike(f"%{city}%"))
    stmt = stmt.group_by(Plan.bedrooms).order_by(Plan.bedrooms)
    result = db.execute(stmt).all()
    return [{"bedrooms": bedrooms, "avg_area": avg_area} for bedrooms, avg_area in result]
