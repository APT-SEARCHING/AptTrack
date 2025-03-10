from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.schemas.apartment import PlanCreate, PlanUpdate, PlanResponse, PlanPriceHistoryBase, PriceTrend

router = APIRouter()

@router.get("/apartments/{apartment_id}/plans", response_model=List[PlanResponse])
def get_apartment_plans(
    apartment_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all plans for an apartment
    """
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    return db_apartment.plans

@router.post("/apartments/{apartment_id}/plans", response_model=PlanResponse)
def create_apartment_plan(
    apartment_id: int,
    plan: PlanCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new plan for an apartment
    """
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    db_plan = Plan(**plan.dict(), apartment_id=apartment_id)
    
    # Create initial price history entry
    price_history = PlanPriceHistory(price=plan.price)
    db_plan.price_history = [price_history]
    
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan

@router.get("/apartments/{apartment_id}/plans/{plan_id}", response_model=PlanResponse)
def get_apartment_plan(
    apartment_id: int,
    plan_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific plan for an apartment
    """
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    db_plan = db.query(Plan).filter(
        Plan.id == plan_id,
        Plan.apartment_id == apartment_id
    ).first()
    
    if db_plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    return db_plan

@router.put("/apartments/{apartment_id}/plans/{plan_id}", response_model=PlanResponse)
def update_apartment_plan(
    apartment_id: int,
    plan_id: int,
    plan: PlanUpdate,
    db: Session = Depends(get_db)
):
    """
    Update a plan for an apartment
    """
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    db_plan = db.query(Plan).filter(
        Plan.id == plan_id,
        Plan.apartment_id == apartment_id
    ).first()
    
    if db_plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    # Update plan fields
    update_data = plan.dict(exclude_unset=True)
    
    # If price is updated, add a new price history entry
    if "price" in update_data and update_data["price"] != db_plan.price:
        new_price = update_data["price"]
        price_history = PlanPriceHistory(plan_id=plan_id, price=new_price)
        db.add(price_history)
    
    # Update the plan object
    for key, value in update_data.items():
        setattr(db_plan, key, value)
    
    db.commit()
    db.refresh(db_plan)
    return db_plan

@router.delete("/apartments/{apartment_id}/plans/{plan_id}", response_model=dict)
def delete_apartment_plan(
    apartment_id: int,
    plan_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a plan for an apartment
    """
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    db_plan = db.query(Plan).filter(
        Plan.id == plan_id,
        Plan.apartment_id == apartment_id
    ).first()
    
    if db_plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    db.delete(db_plan)
    db.commit()
    return {"message": "Plan deleted successfully"}

@router.get("/apartments/{apartment_id}/plans/{plan_id}/price-history", response_model=List[PriceTrend])
def get_plan_price_history(
    apartment_id: int,
    plan_id: int,
    db: Session = Depends(get_db)
):
    """
    Get price history for a specific plan
    """
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    db_plan = db.query(Plan).filter(
        Plan.id == plan_id,
        Plan.apartment_id == apartment_id
    ).first()
    
    if db_plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    price_history = db.query(PlanPriceHistory).filter(
        PlanPriceHistory.plan_id == plan_id
    ).order_by(PlanPriceHistory.recorded_at).all()
    
    return [{"date": ph.recorded_at, "avg_price": ph.price} for ph in price_history] 