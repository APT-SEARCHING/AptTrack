from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.limiter import limiter
from app.core.security import require_admin
from app.db.session import get_db
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.models.user import User
from app.schemas.apartment import PlanCreate, PlanResponse, PlanUpdate, PriceTrend

router = APIRouter()


@router.get("/apartments/{apartment_id}/plans", response_model=List[PlanResponse])
@limiter.limit("60/minute")
def get_apartment_plans(
    request: Request,
    apartment_id: int,
    db: Session = Depends(get_db),
):
    db_apartment = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    return db_apartment.plans


@router.post("/apartments/{apartment_id}/plans", response_model=PlanResponse, status_code=201)
@limiter.limit("10/minute")
def create_apartment_plan(
    request: Request,
    apartment_id: int,
    plan: PlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db_apartment = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")

    db_plan = Plan(**plan.model_dump(), apartment_id=apartment_id)
    db_plan.price_history = [PlanPriceHistory(price=plan.price)]
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan


@router.get("/apartments/{apartment_id}/plans/{plan_id}", response_model=PlanResponse)
@limiter.limit("60/minute")
def get_apartment_plan(
    request: Request,
    apartment_id: int,
    plan_id: int,
    db: Session = Depends(get_db),
):
    db_apartment = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")

    db_plan = db.execute(
        select(Plan).where(Plan.id == plan_id, Plan.apartment_id == apartment_id)
    ).scalar_one_or_none()
    if db_plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return db_plan


@router.put("/apartments/{apartment_id}/plans/{plan_id}", response_model=PlanResponse)
@limiter.limit("10/minute")
def update_apartment_plan(
    request: Request,
    apartment_id: int,
    plan_id: int,
    plan: PlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db_apartment = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")

    db_plan = db.execute(
        select(Plan).where(Plan.id == plan_id, Plan.apartment_id == apartment_id)
    ).scalar_one_or_none()
    if db_plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    update_data = plan.model_dump(exclude_unset=True)
    if "price" in update_data and update_data["price"] != db_plan.price:
        db.add(PlanPriceHistory(plan_id=plan_id, price=update_data["price"]))

    for key, value in update_data.items():
        setattr(db_plan, key, value)

    db.commit()
    db.refresh(db_plan)
    return db_plan


@router.delete("/apartments/{apartment_id}/plans/{plan_id}", response_model=dict)
@limiter.limit("10/minute")
def delete_apartment_plan(
    request: Request,
    apartment_id: int,
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db_apartment = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")

    db_plan = db.execute(
        select(Plan).where(Plan.id == plan_id, Plan.apartment_id == apartment_id)
    ).scalar_one_or_none()
    if db_plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    db.delete(db_plan)
    db.commit()
    return {"message": "Plan deleted successfully"}


@router.get(
    "/apartments/{apartment_id}/plans/{plan_id}/price-history",
    response_model=List[PriceTrend],
)
@limiter.limit("60/minute")
def get_plan_price_history(
    request: Request,
    apartment_id: int,
    plan_id: int,
    db: Session = Depends(get_db),
):
    db_apartment = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")

    db_plan = db.execute(
        select(Plan).where(Plan.id == plan_id, Plan.apartment_id == apartment_id)
    ).scalar_one_or_none()
    if db_plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    price_history = db.execute(
        select(PlanPriceHistory)
        .where(PlanPriceHistory.plan_id == plan_id)
        .order_by(PlanPriceHistory.recorded_at)
    ).scalars().all()
    return [{"date": ph.recorded_at, "avg_price": ph.price} for ph in price_history]
