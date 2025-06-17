import datetime
from typing import List, Optional
from pydantic import BaseModel
import pydantic # For version check

# Assuming schemas.shoe.Shoe will be available for type hinting
# If not, we might need to adjust imports or use forward references if there are circular dependencies
from .shoe import Shoe as ShoeSchema # Use an alias to avoid naming conflicts

class CartItemBase(BaseModel):
    shoe_id: int
    quantity: int

class CartItemCreate(CartItemBase):
    pass

class CartItem(CartItemBase):
    id: int
    cart_id: int
    added_at: datetime.datetime
    shoe: Optional[ShoeSchema] = None # Populate this in the router

    if pydantic.VERSION.startswith("2."):
        model_config = {"from_attributes": True}
    else:
        class Config:
            orm_mode = True

class CartBase(BaseModel):
    pass # No specific fields for base, customer_id will be path/dependency based

class CartCreate(CartBase):
    # customer_id will likely be derived from the authenticated user or path parameter
    # For now, let's assume it might be passed if creating a cart explicitly for a customer
    customer_id: int # Or this could be implicit

class Cart(CartBase):
    id: int
    customer_id: int
    created_at: datetime.datetime
    items: List[CartItem] = []

    if pydantic.VERSION.startswith("2."):
        model_config = {"from_attributes": True}
    else:
        class Config:
            orm_mode = True
