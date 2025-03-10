from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.models.apartment import Neighborhood
from app.schemas.apartment import NeighborhoodCreate, NeighborhoodUpdate, NeighborhoodInDB

router = APIRouter()

@router.post("/neighborhoods", response_model=NeighborhoodInDB)
def create_neighborhood(
    neighborhood: NeighborhoodCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new neighborhood
    """
    db_neighborhood = Neighborhood(**neighborhood.dict())
    db.add(db_neighborhood)
    db.commit()
    db.refresh(db_neighborhood)
    return db_neighborhood

@router.get("/neighborhoods", response_model=List[NeighborhoodInDB])
def get_neighborhoods(
    db: Session = Depends(get_db),
    city: Optional[str] = None,
    state: Optional[str] = None
):
    """
    Get all neighborhoods with optional filtering
    """
    query = db.query(Neighborhood)
    
    if city:
        query = query.filter(Neighborhood.city.ilike(f"%{city}%"))
    if state:
        query = query.filter(Neighborhood.state == state)
    
    return query.all()

@router.get("/neighborhoods/{neighborhood_id}", response_model=NeighborhoodInDB)
def get_neighborhood(
    neighborhood_id: int = Path(..., description="The ID of the neighborhood to retrieve"),
    db: Session = Depends(get_db)
):
    """
    Get a specific neighborhood by ID
    """
    db_neighborhood = db.query(Neighborhood).filter(Neighborhood.id == neighborhood_id).first()
    if db_neighborhood is None:
        raise HTTPException(status_code=404, detail="Neighborhood not found")
    return db_neighborhood

@router.put("/neighborhoods/{neighborhood_id}", response_model=NeighborhoodInDB)
def update_neighborhood(
    neighborhood_id: int,
    neighborhood: NeighborhoodUpdate,
    db: Session = Depends(get_db)
):
    """
    Update a neighborhood
    """
    db_neighborhood = db.query(Neighborhood).filter(Neighborhood.id == neighborhood_id).first()
    if db_neighborhood is None:
        raise HTTPException(status_code=404, detail="Neighborhood not found")
    
    # Update neighborhood fields
    update_data = neighborhood.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_neighborhood, key, value)
    
    db.commit()
    db.refresh(db_neighborhood)
    return db_neighborhood

@router.delete("/neighborhoods/{neighborhood_id}", response_model=dict)
def delete_neighborhood(
    neighborhood_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a neighborhood
    """
    db_neighborhood = db.query(Neighborhood).filter(Neighborhood.id == neighborhood_id).first()
    if db_neighborhood is None:
        raise HTTPException(status_code=404, detail="Neighborhood not found")
    
    db.delete(db_neighborhood)
    db.commit()
    return {"message": "Neighborhood deleted successfully"} 