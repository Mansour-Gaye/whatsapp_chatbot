from sqlalchemy.orm import Session
from sqlalchemy import or_ # for search functionality

import database # models are accessed via database.ClassName
import schemas.shoe as shoe_schema
import schemas.cart as cart_schema
import schemas.order as order_schema
import schemas.customer as customer_schema # Though not explicitly used in this step, good to have for consistency

# Helper to get Pydantic version for model_dump
import pydantic
PYDANTIC_V2 = pydantic.VERSION.startswith("2.")

# --- Shoe CRUD ---
def get_shoe(db: Session, shoe_id: int):
    return db.query(database.Shoe).filter(database.Shoe.id == shoe_id).first()

def get_shoes(db: Session, skip: int = 0, limit: int = 100):
    return db.query(database.Shoe).offset(skip).limit(limit).all()

def create_shoe(db: Session, shoe: shoe_schema.ShoeCreate):
    if PYDANTIC_V2:
        db_shoe = database.Shoe(**shoe.model_dump())
    else:
        db_shoe = database.Shoe(**shoe.dict())
    db.add(db_shoe)
    db.commit()
    db.refresh(db_shoe)
    return db_shoe

def search_shoes(db: Session, query: str, skip: int = 0, limit: int = 100):
    search_term = f"%{query}%"
    return db.query(database.Shoe).filter(
        or_(
            database.Shoe.name.ilike(search_term),
            database.Shoe.brand.ilike(search_term),
            database.Shoe.category.ilike(search_term),
            database.Shoe.description.ilike(search_term)
        )
    ).offset(skip).limit(limit).all()

# --- Customer CRUD ---
def get_customer(db: Session, customer_id: int):
    return db.query(database.Customer).filter(database.Customer.id == customer_id).first()

def get_customer_by_whatsapp_id(db: Session, whatsapp_id: str):
    return db.query(database.Customer).filter(database.Customer.whatsapp_id == whatsapp_id).first()

def create_customer(db: Session, customer: customer_schema.CustomerCreate):
    if PYDANTIC_V2:
        db_customer = database.Customer(**customer.model_dump())
    else:
        db_customer = database.Customer(**customer.dict())
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

# --- Cart CRUD ---
def get_cart_by_customer_id(db: Session, customer_id: int):
    return db.query(database.Cart).filter(database.Cart.customer_id == customer_id).first()

def create_cart(db: Session, customer_id: int) -> database.Cart:
    db_cart = database.Cart(customer_id=customer_id)
    db.add(db_cart)
    db.commit()
    db.refresh(db_cart)
    return db_cart

def get_or_create_cart(db: Session, customer_id: int) -> database.Cart:
    cart = get_cart_by_customer_id(db, customer_id)
    if not cart:
        # Ensure customer exists before creating a cart for them
        customer = get_customer(db, customer_id)
        if not customer:
            # This case should ideally be handled by the router to return a 404
            # For now, let's assume customer validation happens before this call in a real scenario
            # or raise an internal error/exception.
            # For simplicity here, we'll proceed, but in a real app, you'd ensure customer exists.
            pass # Or raise ValueError(f"Customer with id {customer_id} not found")
        cart = create_cart(db, customer_id)
    return cart

def add_item_to_cart(db: Session, cart_id: int, shoe_id: int, quantity: int) -> database.CartItem:
    # Check if item already exists in cart
    db_cart_item = db.query(database.CartItem).filter(
        database.CartItem.cart_id == cart_id,
        database.CartItem.shoe_id == shoe_id
    ).first()

    shoe = get_shoe(db, shoe_id)
    if not shoe:
        raise ValueError(f"Shoe with id {shoe_id} not found.") # Will be caught and raised as HTTPException
    if shoe.quantity_available < quantity:
        raise ValueError(f"Not enough stock for shoe '{shoe.name}'. Available: {shoe.quantity_available}, Requested: {quantity}")


    if db_cart_item:
        # Update quantity if item exists
        new_quantity = db_cart_item.quantity + quantity
        if shoe.quantity_available < new_quantity: # Check again for cumulative quantity
             raise ValueError(f"Not enough stock for shoe '{shoe.name}'. Available: {shoe.quantity_available}, Requested total: {new_quantity}")
        db_cart_item.quantity = new_quantity
    else:
        # Add new item
        db_cart_item = database.CartItem(cart_id=cart_id, shoe_id=shoe_id, quantity=quantity)
        db.add(db_cart_item)

    db.commit()
    db.refresh(db_cart_item)
    return db_cart_item

def get_cart_item(db: Session, cart_item_id: int, cart_id: int): # Ensure item belongs to the cart
    return db.query(database.CartItem).filter(
        database.CartItem.id == cart_item_id,
        database.CartItem.cart_id == cart_id # Security: ensure item is part of the specified cart
    ).first()

def remove_cart_item(db: Session, cart_item_id: int):
    db_cart_item = db.query(database.CartItem).filter(database.CartItem.id == cart_item_id).first()
    if db_cart_item:
        db.delete(db_cart_item)
        db.commit()
    return db_cart_item # Return deleted item or None

def update_cart_item_quantity(db: Session, cart_item_id: int, quantity: int) -> database.CartItem:
    db_cart_item = db.query(database.CartItem).filter(database.CartItem.id == cart_item_id).first()
    if not db_cart_item:
        raise ValueError("Cart item not found.")

    shoe = get_shoe(db, db_cart_item.shoe_id)
    if not shoe:
        # This should not happen if data integrity is maintained
        raise ValueError("Associated shoe not found.")
    if shoe.quantity_available < quantity:
        raise ValueError(f"Not enough stock for shoe '{shoe.name}'. Available: {shoe.quantity_available}, Requested: {quantity}")

    db_cart_item.quantity = quantity
    db.commit()
    db.refresh(db_cart_item)
    return db_cart_item

# --- Order CRUD ---
def create_order(db: Session, customer_id: int, order_data: order_schema.OrderCreate, cart_items: list[database.CartItem]) -> database.Order:
    # Calculate total amount from cart items and their current prices
    total_amount = 0
    for item in cart_items:
        shoe = get_shoe(db, item.shoe_id)
        if not shoe:
            raise ValueError(f"Shoe with ID {item.shoe_id} not found during order creation.") # Should not happen
        total_amount += shoe.price * item.quantity

    if PYDANTIC_V2:
        db_order = database.Order(
            customer_id=customer_id,
            total_amount=total_amount,
            delivery_address=order_data.delivery_address,
            payment_method=order_data.payment_method,
            status="pending" # Default status
        )
    else: # Pydantic v1
         db_order = database.Order(
            customer_id=customer_id,
            total_amount=total_amount,
            delivery_address=order_data.delivery_address, # Assuming order_data is a Pydantic model
            payment_method=order_data.payment_method,
            status="pending"
        )
    db.add(db_order)
    db.commit() # Commit to get order ID
    db.refresh(db_order)

    # Create OrderItems and update shoe quantities
    for cart_item in cart_items:
        shoe = get_shoe(db, cart_item.shoe_id)
        if not shoe or shoe.quantity_available < cart_item.quantity:
            # This check is crucial to prevent overselling if stock changed since cart addition
            db.rollback() # Rollback order creation
            raise ValueError(f"Not enough stock for {shoe.name if shoe else 'Unknown Shoe'}. Order rolled back.")

        db_order_item = database.OrderItem(
            order_id=db_order.id,
            shoe_id=cart_item.shoe_id,
            quantity=cart_item.quantity,
            price_at_purchase=shoe.price # Store price at time of order
        )
        db.add(db_order_item)

        # Update shoe quantity_available
        shoe.quantity_available -= cart_item.quantity
        db.add(shoe) # Add updated shoe to session

    db.commit() # Commit OrderItems and shoe quantity updates
    db.refresh(db_order)
    return db_order

def clear_cart(db: Session, cart_id: int):
    db.query(database.CartItem).filter(database.CartItem.cart_id == cart_id).delete()
    # Also delete the cart itself, or just its items?
    # For now, let's just delete items. Cart can persist.
    # db_cart = db.query(models.Cart).filter(models.Cart.id == cart_id).first()
    # if db_cart:
    #    db.delete(db_cart)
    db.commit()

def search_shoes_by_criteria(db: Session, criteria: dict, skip: int = 0, limit: int = 100) -> list[database.Shoe]:
    """
    Searches for shoes based on a dictionary of criteria.
    Criteria keys can be 'category', 'color', 'brand', 'size'.
    Uses ILIKE for partial matches on string fields.
    """
    query = db.query(database.Shoe)

    if not criteria:
        # If no criteria, return all shoes (paginated) similar to get_shoes
        return query.offset(skip).limit(limit).all()

    if criteria.get("category"):
        query = query.filter(database.Shoe.category.ilike(f"%{criteria['category']}%"))
    if criteria.get("brand"):
        query = query.filter(database.Shoe.brand.ilike(f"%{criteria['brand']}%"))
    if criteria.get("color"):
        # Color might be stored more specifically, but ilike gives flexibility
        query = query.filter(database.Shoe.color.ilike(f"%{criteria['color']}%"))

    # Size is tricky: 'size_available' is a string, might contain multiple sizes or ranges.
    # A simple ILIKE for size might be too broad or too narrow depending on data format.
    # E.g., if size_available = "40, 41, 42" and user wants "41", ILIKE "%41%" works.
    # If size_available = "40-42", it also works.
    # If user wants size "40" and db has "taille 40", this requires more parsing on db side or specific data entry.
    # For now, using ILIKE on size_available.
    if criteria.get("size"):
        query = query.filter(database.Shoe.size_available.ilike(f"%{criteria['size']}%"))

    # Add other fields if necessary, e.g., price range

    return query.offset(skip).limit(limit).all()
