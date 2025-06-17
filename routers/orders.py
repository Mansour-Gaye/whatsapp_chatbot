from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import database # For get_db and models
import schemas.order as order_schema
import schemas.cart as cart_schema # For type hinting if needed
import crud
from utils.whatsapp_utils import send_whatsapp_message # Added for recommendations
import logging # For logging

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["orders"],
    responses={404: {"description": "Not found"}},
)

# Helper to check if customer exists (can be shared or defined per router)
def get_customer_or_404(db: Session, customer_id: int):
    customer = crud.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer with id {customer_id} not found")
    return customer

@router.post("/customers/{customer_id}/orders/", response_model=order_schema.Order, status_code=status.HTTP_201_CREATED)
async def place_customer_order(
    customer_id: int,
    order_create_data: order_schema.OrderCreate, # Contains delivery_address, payment_method
    db: Session = Depends(database.get_db)
):
    """
    Place an order for a customer using their current cart.
    - Retrieves the customer's cart.
    - If cart is empty, returns an error.
    - Creates an order and order items.
    - Clears the cart.
    - Updates shoe quantities.
    """
    get_customer_or_404(db, customer_id) # Ensure customer exists

    cart = crud.get_cart_by_customer_id(db, customer_id=customer_id)
    if not cart or not cart.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty. Cannot place an order.")

    # The order_create_data Pydantic model might not have customer_id,
    # but our crud.create_order function expects it.
    # We also need to pass the cart items to crud.create_order.

    # The schema `order_schema.OrderCreate` currently expects `customer_id`.
    # Let's adjust the schema or how we call the CRUD.
    # For now, let's assume `order_create_data` might not have `customer_id` and we supply it from the path.
    # The `order_create_data` schema (OrderCreate) was defined with `customer_id: int`.
    # This is redundant if customer_id is in path. Let's assume the schema is for the body payload
    # and might not need customer_id if it's a path param.
    # I will proceed assuming `order_data.customer_id` from the schema might be ignored or validated against path `customer_id`.
    # The CRUD function `create_order` takes `customer_id` as a separate argument.

    # Ensure all cart items and their shoes are loaded for price_at_purchase and quantity checks
    for item in cart.items:
        db.refresh(item, attribute_names=['shoe'])
        if not item.shoe:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Cart item with ID {item.id} has no associated shoe data.")

    try:
        # Pass the Pydantic model `order_create_data` directly
        # The CRUD function will extract delivery_address and payment_method
        db_order = crud.create_order(
            db=db,
            customer_id=customer_id,
            order_data=order_create_data, # This is schemas.order.OrderCreate
            cart_items=list(cart.items) # Pass the list of ORM objects
        )
    except ValueError as e: # Catch stock issues or other validation errors from CRUD
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e: # Catch any other unexpected errors during order creation
        # Log the exception e
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while creating the order.")


    # After successful order creation, clear the cart
    crud.clear_cart(db, cart_id=cart.id)

    # Eagerly load order items and their shoes for the response
    db.refresh(db_order, attribute_names=['items'])
    for item_model in db_order.items: # Renamed to avoid conflict with loop var 'item'
        db.refresh(item_model, attribute_names=['shoe'])

    # --- Send Post-Purchase Recommendations ---
    try:
        customer = crud.get_customer(db, customer_id=customer_id) # Fetch customer for WA ID
        if customer and customer.whatsapp_id:
            recommendations = crud.get_recommendations_after_purchase(db, order_id=db_order.id, limit=2) # Limit to 2 per category/brand

            rec_texts = []
            if recommendations.get("based_on_category") and recommendations["based_on_category"]["items"]:
                cat_name = recommendations["based_on_category"]["name"]
                cat_items = ", ".join([f"{s.name} ({s.price} XOF)" for s in recommendations["based_on_category"]["items"]])
                rec_texts.append(f"Vous pourriez également aimer ces articles de la catégorie '{cat_name}': {cat_items}")

            if recommendations.get("based_on_brand") and recommendations["based_on_brand"]["items"]:
                brand_name = recommendations["based_on_brand"]["name"]
                brand_items = ", ".join([f"{s.name} ({s.price} XOF)" for s in recommendations["based_on_brand"]["items"]])
                rec_texts.append(f"Ou d'autres articles de la marque '{brand_name}': {brand_items}")

            if rec_texts:
                full_rec_message = "Merci pour votre commande ! 🎉\n" + "\n\n".join(rec_texts)
                # We need send_whatsapp_message, which is async. This endpoint is also async.
                # Ensure utils.whatsapp_utils.send_whatsapp_message is imported (now at top of file).

                # Schedule as a background task if possible, or await directly if simple.
                # For now, await directly.
                await send_whatsapp_message(customer.whatsapp_id, full_rec_message)
                logger.info(f"Sent post-purchase recommendations to {customer.whatsapp_id} for order {db_order.id}")
        else:
            logger.warning(f"Could not send post-purchase recommendations for order {db_order.id}: Customer or WhatsApp ID not found.")

    except Exception as e:
        logger.error(f"Failed to send post-purchase recommendations for order {db_order.id}: {e}")
        # Do not let recommendation failure affect the main order response.

    return db_order
