import datetime
from typing import List, Optional
from pydantic import BaseModel
import pydantic # For version check

from .shoe import Shoe as ShoeSchema # For OrderItem details

class OrderItemBase(BaseModel):
    shoe_id: int
    quantity: int
    price_at_purchase: float # Capture price at the time of order

class OrderItemCreate(OrderItemBase):
    pass

class OrderItem(OrderItemBase):
    id: int
    order_id: int
    shoe: Optional[ShoeSchema] = None # Populate in router

    if pydantic.VERSION.startswith("2."):
        model_config = {"from_attributes": True}
    else:
        class Config:
            orm_mode = True

class OrderBase(BaseModel):
    delivery_address: Optional[str] = None
    payment_method: Optional[str] = None
    # total_amount will be calculated, status has a default

class OrderCreate(OrderBase):
    # customer_id will likely be derived from context (e.g. authenticated user)
    # For now, let's assume it's passed or handled by the endpoint logic
    customer_id: int # Or determine from context
    # items will be crucial for creating an order
    # This might be a list of cart_item_ids or shoe_ids with quantities
    # For simplicity, let's assume we pass what's needed to create OrderItems
    # This part can be complex depending on how orders are created (e.g., from a cart)
    # Let's assume a list of items to be ordered (shoe_id, quantity)
    # The actual creation logic in the router will handle creating OrderItem records
    # and calculating total_amount.

class Order(OrderBase):
    id: int
    customer_id: int
    created_at: datetime.datetime
    total_amount: float
    status: str
    items: List[OrderItem] = []

    if pydantic.VERSION.startswith("2."):
        model_config = {"from_attributes": True}
    else:
        class Config:
            orm_mode = True
