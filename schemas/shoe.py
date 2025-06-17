from typing import Optional
from pydantic import BaseModel

class ShoeBase(BaseModel):
    name: str
    size_available: str
    color: str
    price: float
    brand: str
    image_url: Optional[str] = None
    category: str
    description: Optional[str] = None
    quantity_available: int

class ShoeCreate(ShoeBase):
    pass

class ShoeUpdate(ShoeBase): # Added for potential future use
    pass

class Shoe(ShoeBase):
    id: int

    id: int

    if pydantic.VERSION.startswith("2."):
        model_config = {"from_attributes": True}
    else:
        class Config:
            orm_mode = True
