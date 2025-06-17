from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

# Assuming models are in database.py and schemas in schemas.shoe
# Adjust paths if your project structure is different
import database # This will give access to models.Shoe, get_db
import schemas.shoe as shoe_schema # Alias to avoid confusion
import crud # Added import for crud functions

router = APIRouter(
    prefix="/shoes",
    tags=["shoes"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_model=List[shoe_schema.Shoe])
async def list_shoes(skip: int = 0, limit: int = 10, db: Session = Depends(database.get_db)):
    """
    Retrieve a list of shoes with pagination.
    """
    if skip < 0:
        raise HTTPException(status_code=400, detail="Skip parameter cannot be negative.")
    if limit <= 0:
        raise HTTPException(status_code=400, detail="Limit parameter must be positive.")

    # Use CRUD function
    shoes = crud.get_shoes(db=db, skip=skip, limit=limit)
    return shoes

@router.get("/search/", response_model=List[shoe_schema.Shoe])
async def search_shoes_endpoint(query: str, skip: int = 0, limit: int = 10, db: Session = Depends(database.get_db)):
    """
    Search for shoes by name, brand, category, or description.
    """
    if skip < 0:
        raise HTTPException(status_code=400, detail="Skip parameter cannot be negative.")
    if limit <= 0:
        raise HTTPException(status_code=400, detail="Limit parameter must be positive.")

    shoes = crud.search_shoes(db=db, query=query, skip=skip, limit=limit)
    return shoes

# Example of how you might create a shoe (for future reference, not part of current task)
# @router.post("/", response_model=shoe_schema.Shoe, status_code=201)
# async def create_shoe_endpoint(shoe: shoe_schema.ShoeCreate, db: Session = Depends(database.get_db)):
#     return crud.create_shoe(db=db, shoe=shoe)
