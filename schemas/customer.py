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
    last_viewed_product_ids: List[int] = []
    preferred_language: Optional[str] = 'fr'
    loyalty_points: Optional[int] = 0


class CustomerCreate(CustomerBase):
    pass

class Customer(CustomerBase):
    id: int
    created_at: datetime.datetime
    # cart: Optional[CartSchema] = None # Example: if you want to nest cart
    # orders: List[OrderSchema] = []  # Example: if you want to nest orders

    if pydantic.VERSION.startswith("2."):
        model_config = {"from_attributes": True}

        @pydantic.field_validator("last_viewed_product_ids", mode="before")
        @classmethod
        def parse_json_string_to_list(cls, value):
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return [] # Default to empty list on error
            if value is None: # Handle case where db might return None before default "[]" kicks in
                return []
            return value # Expect list if not a string

        # No specific serializer needed here for model_dump if the field is already a list.
        # Pydantic will serialize the list to JSON array in output if model_dump(mode='json') is used.
        # The database update logic in CRUD will handle serializing to string before DB commit.
    else: # Pydantic v1
        class Config:
            orm_mode = True
            # For Pydantic v1, validation of JSON string would typically happen in the CRUD layer
            # or by using a custom root validator or a regular validator that handles str input.
            # Pydantic v1 does not have field_serializer in the same way.
            # Let's assume for v1, the CRUD handles the string-to-list conversion upon reading from DB,
            # and list-to-string before writing.

import json # Add this import
