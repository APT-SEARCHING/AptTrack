from typing import List, Optional

from app.core.limiter import limiter
from app.core.security import require_admin
from app.db.session import get_db
from app.models.apartment import Neighborhood
from app.models.user import User
from app.schemas.apartment import NeighborhoodCreate, NeighborhoodInDB, NeighborhoodUpdate
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/neighborhoods", response_model=List[NeighborhoodInDB])
@limiter.limit("60/minute")
def get_neighborhoods(
    request: Request,
    db: Session = Depends(get_db),
    city: Optional[str] = None,
    state: Optional[str] = None,
):
    stmt = select(Neighborhood)
    if city:
        stmt = stmt.where(Neighborhood.city.ilike(f"%{city}%"))
    if state:
        stmt = stmt.where(Neighborhood.state == state)
    return db.execute(stmt).scalars().all()


@router.post("/neighborhoods", response_model=NeighborhoodInDB, status_code=201)
@limiter.limit("10/minute")
def create_neighborhood(
    request: Request,
    neighborhood: NeighborhoodCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db_neighborhood = Neighborhood(**neighborhood.model_dump())
    db.add(db_neighborhood)
    db.commit()
    db.refresh(db_neighborhood)
    return db_neighborhood


@router.get("/neighborhoods/{neighborhood_id}", response_model=NeighborhoodInDB)
@limiter.limit("60/minute")
def get_neighborhood(
    request: Request,
    neighborhood_id: int = Path(..., description="The ID of the neighborhood to retrieve"),
    db: Session = Depends(get_db),
):
    db_neighborhood = db.execute(
        select(Neighborhood).where(Neighborhood.id == neighborhood_id)
    ).scalar_one_or_none()
    if db_neighborhood is None:
        raise HTTPException(status_code=404, detail="Neighborhood not found")
    return db_neighborhood


@router.put("/neighborhoods/{neighborhood_id}", response_model=NeighborhoodInDB)
@limiter.limit("10/minute")
def update_neighborhood(
    request: Request,
    neighborhood_id: int,
    neighborhood: NeighborhoodUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db_neighborhood = db.execute(
        select(Neighborhood).where(Neighborhood.id == neighborhood_id)
    ).scalar_one_or_none()
    if db_neighborhood is None:
        raise HTTPException(status_code=404, detail="Neighborhood not found")

    for key, value in neighborhood.model_dump(exclude_unset=True).items():
        setattr(db_neighborhood, key, value)

    db.commit()
    db.refresh(db_neighborhood)
    return db_neighborhood


@router.delete("/neighborhoods/{neighborhood_id}", response_model=dict)
@limiter.limit("10/minute")
def delete_neighborhood(
    request: Request,
    neighborhood_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db_neighborhood = db.execute(
        select(Neighborhood).where(Neighborhood.id == neighborhood_id)
    ).scalar_one_or_none()
    if db_neighborhood is None:
        raise HTTPException(status_code=404, detail="Neighborhood not found")

    db.delete(db_neighborhood)
    db.commit()
    return {"message": "Neighborhood deleted successfully"}
