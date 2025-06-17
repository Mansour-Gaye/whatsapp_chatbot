from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import database # For get_db and models
import schemas.cart as cart_schema
import schemas.shoe as shoe_schema # For response model of shoe within cart item
import crud

router = APIRouter(
    tags=["cart"],
    responses={404: {"description": "Not found"}},
)

# Helper to check if customer exists
def get_customer_or_404(db: Session, customer_id: int):
    customer = crud.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer with id {customer_id} not found")
    return customer

@router.post("/customers/{customer_id}/cart/items/", response_model=cart_schema.CartItem)
async def add_item_to_customer_cart(
    customer_id: int,
    item: cart_schema.CartItemCreate,
    db: Session = Depends(database.get_db)
):
    """
    Add a shoe to the customer's cart or update quantity if it already exists.
    - Gets or creates a cart for the `customer_id`.
    - Adds the shoe to the cart or updates quantity.
    """
    get_customer_or_404(db, customer_id) # Ensure customer exists

    cart = crud.get_or_create_cart(db, customer_id)
    if not cart: # Should not happen if get_or_create_cart works as expected
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not get or create cart.")

    try:
        # Attempt to add item
        db_cart_item = crud.add_item_to_cart(db, cart_id=cart.id, shoe_id=item.shoe_id, quantity=item.quantity)
    except ValueError as e: # Catch stock issues or shoe not found from CRUD
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Eagerly load shoe details for the response
    db.refresh(db_cart_item, attribute_names=['shoe'])
    return db_cart_item


@router.get("/customers/{customer_id}/cart/", response_model=cart_schema.Cart)
async def get_customer_cart(customer_id: int, db: Session = Depends(database.get_db)):
    """
    Retrieve the current cart for the customer_id.
    Calculates total items and total price.
    """
    get_customer_or_404(db, customer_id) # Ensure customer exists

    cart = crud.get_cart_by_customer_id(db, customer_id=customer_id)
    if not cart:
        # Return an empty cart representation if no cart exists
        # This aligns with the idea that a customer might just not have a cart yet
        return cart_schema.Cart(id=-1, customer_id=customer_id, created_at=database.datetime.datetime.utcnow(), items=[])


    # Manually construct the response to include total_price and total_items if not part of schema
    # The schema `Cart` has `items: List[CartItem]`. `CartItem` has `shoe: ShoeSchema`.
    # We need to ensure shoes are loaded for items and calculate totals.

    # Refresh cart to potentially load items if not already loaded (depends on session state)
    # db.refresh(cart, attribute_names=['items']) # This loads cart.items

    # For each item, ensure its 'shoe' attribute is loaded for price calculation
    cart_items_response = []
    total_price = 0.0
    total_items_count = 0

    for item_db in cart.items: # cart.items should be ORM CartItem objects
        db.refresh(item_db, attribute_names=['shoe']) # Ensure item_db.shoe is loaded
        if item_db.shoe:
            total_price += item_db.shoe.price * item_db.quantity
        total_items_count += item_db.quantity
        cart_items_response.append(item_db) # These are already ORM objects, Pydantic will handle conversion

    # The schema `cart_schema.Cart` expects `id`, `customer_id`, `created_at`, `items`.
    # It does not have total_price or total_items_count.
    # For now, these calculated values are not part of the response model.
    # If they need to be, the Pydantic schema for Cart would need to be updated.
    # Let's return the cart as is, the client can compute totals if needed, or we adjust schema later.

    return cart


@router.delete("/customers/{customer_id}/cart/items/{cart_item_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item_from_customer_cart(
    customer_id: int,
    cart_item_id: int,
    db: Session = Depends(database.get_db)
):
    """
    Remove a specific item from the cart.
    """
    get_customer_or_404(db, customer_id) # Ensure customer exists
    cart = crud.get_cart_by_customer_id(db, customer_id)
    if not cart:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart not found for this customer.")

    # Ensure the cart_item_id belongs to the customer's cart
    cart_item = crud.get_cart_item(db, cart_item_id=cart_item_id, cart_id=cart.id)
    if not cart_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Cart item with id {cart_item_id} not found in customer's cart.")

    crud.remove_cart_item(db, cart_item_id=cart_item.id)
    return None # Returns 204 No Content


@router.put("/customers/{customer_id}/cart/items/{cart_item_id}/", response_model=cart_schema.CartItem)
async def update_customer_cart_item_quantity(
    customer_id: int,
    cart_item_id: int,
    item_update: cart_schema.CartItemCreate, # Reusing CartItemCreate for quantity, shoe_id will be ignored
    db: Session = Depends(database.get_db)
):
    """
    Update the quantity of a specific item in the cart.
    """
    get_customer_or_404(db, customer_id) # Ensure customer exists
    cart = crud.get_cart_by_customer_id(db, customer_id)
    if not cart:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart not found for this customer.")

    # Ensure the cart_item_id belongs to the customer's cart
    cart_item = crud.get_cart_item(db, cart_item_id=cart_item_id, cart_id=cart.id)
    if not cart_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Cart item with id {cart_item_id} not found in customer's cart.")

    if item_update.quantity <= 0: # Remove item if quantity is zero or less
        crud.remove_cart_item(db, cart_item_id=cart_item.id)
        # Return a representation of a deleted item or an empty response with 204
        # For simplicity, let's return 204 as if it was a DELETE for 0 quantity
        # However, the response_model is CartItem. This path needs careful thought.
        # Let's assume quantity must be > 0 for an update. Client should use DELETE for removal.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be positive. To remove an item, use the DELETE endpoint.")

    try:
        updated_item = crud.update_cart_item_quantity(db, cart_item_id=cart_item.id, quantity=item_update.quantity)
    except ValueError as e: # Catch stock issues from CRUD
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    db.refresh(updated_item, attribute_names=['shoe']) # Eager load shoe for response
    return updated_item
