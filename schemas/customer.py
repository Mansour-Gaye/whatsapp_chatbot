import datetime
from typing import Optional, List
from pydantic import BaseModel
import pydantic

# Forward references might be needed if Cart and Order schemas are imported here
# from .cart import Cart as CartSchema
# from .order import Order as OrderSchema
# For now, we'll keep it simple and not include nested Cart/Order lists by default in Customer schema
# to avoid circular dependencies at module load time.
# These can be added to specific response models if needed.

class CustomerBase(BaseModel):
    whatsapp_id: str
    name: Optional[str] = None

class CustomerCreate(CustomerBase):
    pass

class Customer(CustomerBase):
    id: int
    created_at: datetime.datetime
    # cart: Optional[CartSchema] = None # Example: if you want to nest cart
    # orders: List[OrderSchema] = []  # Example: if you want to nest orders

    if pydantic.VERSION.startswith("2."):
        model_config = {"from_attributes": True}
    else:
        class Config:
            orm_mode = True
