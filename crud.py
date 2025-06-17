import json
import logging
from typing import Optional # For Optional type hint (already present but good to confirm)

from sqlalchemy.orm import Session
from sqlalchemy import or_ # for search functionality

import database # models are accessed via database.ClassName
# Setup logger for this module - should be done once, typically at the start.
logger = logging.getLogger(__name__)
# Basic config if not configured globally, though FastAPI typically handles this.
# logging.basicConfig(level=logging.INFO) # Potentially redundant if FastAPI configures root logger.

from typing import List, Tuple # Moved here for proper organization

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
    customer_data = customer.model_dump() if PYDANTIC_V2 else customer.dict()
    # Ensure last_viewed_product_ids is stored as a JSON string if it's part of the input schema
    if 'last_viewed_product_ids' in customer_data and isinstance(customer_data['last_viewed_product_ids'], list):
        customer_data['last_viewed_product_ids'] = json.dumps(customer_data['last_viewed_product_ids'])
    else: # Ensure default is set correctly as string for DB
        customer_data['last_viewed_product_ids'] = json.dumps([])


    db_customer = database.Customer(**customer_data)
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    # For consistency, ensure the returned object's field is a list if Pydantic didn't auto-convert
    if isinstance(db_customer.last_viewed_product_ids, str):
        try:
            db_customer.last_viewed_product_ids_list = json.loads(db_customer.last_viewed_product_ids)
        except json.JSONDecodeError:
            db_customer.last_viewed_product_ids_list = []
    else: # Should already be a list if handled by Pydantic v2 schema on creation from request
        db_customer.last_viewed_product_ids_list = db_customer.last_viewed_product_ids if isinstance(db_customer.last_viewed_product_ids, list) else []
    return db_customer

def _ensure_customer_last_viewed_is_list(customer: Optional[database.Customer]):
    """Helper to convert last_viewed_product_ids from JSON string to list if needed."""
    if customer and isinstance(customer.last_viewed_product_ids, str):
        try:
            # This creates a temporary attribute, not changing the ORM model instance field type directly
            # The Pydantic schema validator is the primary place for this conversion for response models
            # This is more for internal CRUD logic if accessing the field before Pydantic validation
            customer.last_viewed_product_ids_list_internal = json.loads(customer.last_viewed_product_ids)
        except json.JSONDecodeError:
            customer.last_viewed_product_ids_list_internal = []
    elif customer and isinstance(customer.last_viewed_product_ids, list):
         customer.last_viewed_product_ids_list_internal = customer.last_viewed_product_ids
    elif customer:
        customer.last_viewed_product_ids_list_internal = []
    return customer

# Modify existing customer fetchers to use the helper, or rely on Pydantic schema validation
# For direct ORM object usage within other CRUDs, this helper might be useful.
# However, Pydantic schema on return should handle it for API responses.

def update_last_viewed_products(db: Session, customer_id: int, product_id: int, max_items: int = 5) -> Optional[database.Customer]:
    customer = get_customer(db, customer_id)
    if not customer:
        return None

    current_list = []
    if isinstance(customer.last_viewed_product_ids, str):
        try:
            current_list = json.loads(customer.last_viewed_product_ids)
        except json.JSONDecodeError:
            current_list = []
    elif isinstance(customer.last_viewed_product_ids, list): # Should not happen with Text field, but defensive
        current_list = customer.last_viewed_product_ids

    # Add product_id to the beginning, ensuring uniqueness and max_items
    if product_id in current_list:
        current_list.remove(product_id)
    current_list.insert(0, product_id)

    # Truncate
    customer.last_viewed_product_ids = json.dumps(current_list[:max_items])

    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


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
    if exclude_ids:
        query = query.filter(database.Shoe.id.notin_(exclude_ids))

    return query.offset(skip).limit(limit).all()

def get_popular_shoes(db: Session, limit: int = 5) -> list[database.Shoe]:
    """
    Gets the most popular shoes based on the quantity sold in OrderItems.
    """
    from sqlalchemy import func # Import func for SUM and COUNT

    # Subquery to get sum of quantities for each shoe_id from OrderItem
    # This gives higher weight to orders with multiple units of the same shoe.
    # Alternatively, one could use func.count(models.OrderItem.shoe_id) to count
    # how many times a shoe appears in orders, regardless of quantity per order.
    # Using SUM(quantity) seems more indicative of popularity/demand.

    popular_shoe_ids_subquery = (
        db.query(
            database.OrderItem.shoe_id,
            func.sum(database.OrderItem.quantity).label("total_sold")
        )
        .group_by(database.OrderItem.shoe_id)
        .subquery()
    )

    # Query to join with Shoe table and order by total_sold
    popular_shoes_query = (
        db.query(database.Shoe)
        .join(
            popular_shoe_ids_subquery,
            database.Shoe.id == popular_shoe_ids_subquery.c.shoe_id
        )
        .order_by(popular_shoe_ids_subquery.c.total_sold.desc())
        .limit(limit)
    )

    popular_shoes = popular_shoes_query.all()
    return popular_shoes

def get_recommendations_after_purchase(db: Session, order_id: int, limit: int = 3) -> dict:
    """
    Generates post-purchase recommendations based on items in the order.
    Returns a dict with keys like "based_on_category" and "based_on_brand".
    """
    order = db.query(database.Order).filter(database.Order.id == order_id).first()
    if not order or not order.items:
        return {}

    # Get IDs of items already in the current order to exclude them from recommendations
    ordered_shoe_ids = {item.shoe_id for item in order.items}

    # For simplicity, base recommendations on the first item in the order
    # More sophisticated logic could consider all items or the most expensive one, etc.
    first_ordered_item = order.items[0]
    reference_shoe = db.query(database.Shoe).filter(database.Shoe.id == first_ordered_item.shoe_id).first()

    if not reference_shoe:
        return {}

    recommendations = {}

    # 1. Category-based recommendations
    if reference_shoe.category:
        category_recommendations = (
            db.query(database.Shoe)
            .filter(
                database.Shoe.category.ilike(f"%{reference_shoe.category}%"),
                database.Shoe.id.notin_(ordered_shoe_ids), # Exclude already ordered items
                database.Shoe.id != reference_shoe.id      # Exclude the reference shoe itself
            )
            .limit(limit)
            .all()
        )
        if category_recommendations:
            recommendations["based_on_category"] = {
                "name": reference_shoe.category,
                "items": category_recommendations
            }

    # 2. Brand-based recommendations
    if reference_shoe.brand:
        brand_recommendations = (
            db.query(database.Shoe)
            .filter(
                database.Shoe.brand.ilike(f"%{reference_shoe.brand}%"),
                database.Shoe.id.notin_(ordered_shoe_ids), # Exclude already ordered items
                database.Shoe.id != reference_shoe.id      # Exclude the reference shoe itself
            )
            .limit(limit)
            .all()
        )
        # Avoid overlap with category recommendations if possible, or just present both
        # For simplicity, we'll allow overlap for now.
        if brand_recommendations:
            # Filter out items already recommended by category to reduce redundancy
            if "based_on_category" in recommendations:
                category_rec_ids = {shoe.id for shoe in recommendations["based_on_category"]["items"]}
                brand_recommendations = [shoe for shoe in brand_recommendations if shoe.id not in category_rec_ids]

            if brand_recommendations: # If any left after filtering
                recommendations["based_on_brand"] = {
                    "name": reference_shoe.brand,
                    "items": brand_recommendations[:limit] # Ensure limit is respected after filtering
                }

    return recommendations

def get_user_attribute_preferences(db: Session, customer_id: int) -> dict:
    """
    Aggregates attribute preferences (categories, brands, colors) based on a customer's
    purchase history and last viewed products.
    """
    from collections import Counter # For counting occurrences

    customer = db.query(database.Customer).filter(database.Customer.id == customer_id).first()
    if not customer:
        return {} # Or raise error

    # --- Aggregate Shoe IDs from purchase history and last viewed ---
    historic_shoe_ids = set()

    # 1. From purchase history (OrderItems)
    orders = db.query(database.Order).filter(database.Order.customer_id == customer_id).all()
    for order in orders:
        for item in order.items:
            historic_shoe_ids.add(item.shoe_id)

    # 2. From last_viewed_product_ids
    if customer.last_viewed_product_ids:
        try:
            viewed_ids = json.loads(customer.last_viewed_product_ids)
            if isinstance(viewed_ids, list):
                historic_shoe_ids.update(viewed_ids)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse last_viewed_product_ids for customer {customer_id}: {customer.last_viewed_product_ids}")

    if not historic_shoe_ids:
        return {"categories": {}, "brands": {}, "colors": {}, "preferred_shoe_ids": []}

    # --- Fetch corresponding Shoe objects ---
    historic_shoes = db.query(database.Shoe).filter(database.Shoe.id.in_(list(historic_shoe_ids))).all()

    if not historic_shoes:
        return {"categories": {}, "brands": {}, "colors": {}, "preferred_shoe_ids": list(historic_shoe_ids)}

    # --- Aggregate common attributes ---
    category_counts = Counter()
    brand_counts = Counter()
    color_counts = Counter()

    for shoe in historic_shoes:
        if shoe.category:
            category_counts[shoe.category.lower()] += 1 # Normalize to lower for consistent counting
        if shoe.brand:
            brand_counts[shoe.brand.lower()] += 1
        if shoe.color:
            color_counts[shoe.color.lower()] += 1

    return {
        "categories": dict(category_counts),
        "brands": dict(brand_counts),
        "colors": dict(color_counts),
        "preferred_shoe_ids": list(historic_shoe_ids) # IDs already seen/bought by user
    }

def get_content_based_recommendations(db: Session, preferences: dict, limit: int = 5) -> list[database.Shoe]:
    """
    Recommends shoes based on content similarity to user's attribute preferences.
    Excludes shoes already in the user's history (preferred_shoe_ids from preferences).
    """
    if not preferences or not any([preferences.get("categories"), preferences.get("brands"), preferences.get("colors")]):
        logger.info("Not enough preference data to generate content-based recommendations.")
        return []

    preferred_shoe_ids = set(preferences.get("preferred_shoe_ids", []))

    # Fetch all candidate shoes not in the user's history
    candidate_shoes = db.query(database.Shoe).filter(database.Shoe.id.notin_(preferred_shoe_ids)).all()

    scored_shoes = []

    for shoe in candidate_shoes:
        score = 0
        # Score based on category match (weighted by preference count)
        if shoe.category and preferences.get("categories", {}).get(shoe.category.lower()):
            score += preferences["categories"][shoe.category.lower()] * 2 # Higher weight for category

        # Score based on brand match
        if shoe.brand and preferences.get("brands", {}).get(shoe.brand.lower()):
            score += preferences["brands"][shoe.brand.lower()] * 1.5 # Medium weight for brand

        # Score based on color match
        if shoe.color and preferences.get("colors", {}).get(shoe.color.lower()):
            score += preferences["colors"][shoe.color.lower()] * 1 # Standard weight for color

        if score > 0:
            scored_shoes.append({"shoe": shoe, "score": score})

    # Sort shoes by score in descending order
    scored_shoes.sort(key=lambda x: x["score"], reverse=True)

    # Return the top 'limit' shoes
    recommended_shoes = [item["shoe"] for item in scored_shoes[:limit]]

    logger.info(f"Generated {len(recommended_shoes)} content-based recommendations. Top score: {scored_shoes[0]['score'] if scored_shoes else 0}")
    return recommended_shoes

def get_distinct_categories(db: Session) -> List[str]:
    """
    Fetches a list of distinct (non-null) categories from the Shoe table.
    """
    distinct_categories_query = db.query(database.Shoe.category).filter(database.Shoe.category.isnot(None)).distinct().all()
    categories = [category[0] for category in distinct_categories_query if category[0]] # Ensure category[0] is not None or empty
    logger.info(f"Found distinct categories: {categories}")
    return categories

# --- Loyalty Points CRUD ---
def add_loyalty_points(db: Session, customer_id: int, points_to_add: int) -> Optional[database.Customer]:
    """Adds loyalty points to a customer's balance."""
    if points_to_add <= 0: # Usually points are positive, but good to handle
        logger.info(f"No points to add for customer {customer_id} (points_to_add: {points_to_add}).")
        # return get_customer(db, customer_id) # Return customer without change if 0 or negative points
        # Or better, just don't proceed if points are not positive.
        # For now, let's assume points_to_add will be > 0 from business logic.
        pass

    customer = get_customer(db, customer_id=customer_id)
    if customer:
        customer.loyalty_points = (customer.loyalty_points or 0) + points_to_add # Ensure current points are not None
        db.add(customer)
        db.commit()
        db.refresh(customer)
        logger.info(f"Added {points_to_add} loyalty points to customer {customer_id}. New balance: {customer.loyalty_points}")
        return customer
    logger.warning(f"Customer {customer_id} not found. Could not add loyalty points.")
    return None

def get_customer_loyalty_points(db: Session, customer_id: int) -> Optional[int]:
    """Fetches the loyalty points for a specific customer."""
    customer = get_customer(db, customer_id=customer_id)
    if customer:
        return customer.loyalty_points
    logger.warning(f"Customer {customer_id} not found when trying to fetch loyalty points.")
    return None # Or 0 if preferred when customer not found, but None indicates absence

def update_customer_language(db: Session, customer_id: int, lang_code: str) -> Optional[database.Customer]:
    """
    Updates the preferred_language for a customer.
    Validates lang_code against allowed languages ('fr', 'en').
    """
    if lang_code not in ['fr', 'en']:
        logger.warning(f"Invalid language code '{lang_code}' provided for customer {customer_id}.")
        return None # Or raise ValueError

    customer = get_customer(db, customer_id=customer_id)
    if customer:
        customer.preferred_language = lang_code
        db.add(customer)
        db.commit()
        db.refresh(customer)
        logger.info(f"Customer {customer_id} preferred language updated to '{lang_code}'.")
        return customer
    logger.warning(f"Customer {customer_id} not found, could not update language preference.")
    return None

def update_order_status(db: Session, order_id: int, new_status: str) -> Optional[database.Order]:
    """
    Updates the status of an order.
    Returns the updated Order object or None if the order is not found.
    """
    order = db.query(database.Order).filter(database.Order.id == order_id).first()
    if order:
        order.status = new_status
        db.add(order) # Add to session to mark as dirty
        db.commit()
        db.refresh(order)
        logger.info(f"Order {order_id} status updated to {new_status}.")
        return order
    else:
        logger.warning(f"Attempted to update status for non-existent order {order_id}.")
        return None

def get_last_completed_order_for_customer(db: Session, customer_id: int) -> Optional[database.Order]:
    """
    Fetches the most recent 'completed' order for a customer.
    If no 'completed' order, falls back to the most recent order regardless of status.
    Eagerly loads OrderItems and their associated Shoe details.
    """
    from sqlalchemy.orm import joinedload

    # Try to get the last 'completed' order first
    last_order = (
        db.query(database.Order)
        .filter(database.Order.customer_id == customer_id, database.Order.status == "completed")
        .order_by(database.Order.created_at.desc())
        .options(
            joinedload(database.Order.items).joinedload(database.OrderItem.shoe)
        )
        .first()
    )

    if not last_order:
        # If no 'completed' order, get the most recent order by date, regardless of status
        logger.info(f"No 'completed' order found for customer {customer_id}. Fetching most recent order by date.")
        last_order = (
            db.query(database.Order)
            .filter(database.Order.customer_id == customer_id)
            .order_by(database.Order.created_at.desc())
            .options(
                joinedload(database.Order.items).joinedload(database.OrderItem.shoe)
            )
            .first()
        )

    if last_order:
        logger.info(f"Last order for customer {customer_id} (Order ID: {last_order.id}, Status: {last_order.status}) found with {len(last_order.items)} items.")
    else:
        logger.info(f"No orders found for customer {customer_id}.")

    return last_order

# Define simple data structures for check_items_availability_and_price (conceptually)
# For actual implementation, we'll use dicts, but these define the expected keys.
# class OrderItemData(TypedDict):
#     shoe_id: int
#     quantity: int
#     original_price: float
#     original_name: str # For reference if item changed
#     original_brand: str # For reference

# class VerifiedItemData(TypedDict):
#     shoe_id: int
#     quantity: int
#     current_price: float
#     current_name: str
#     current_brand: str
#     available_stock: int # Current available stock of the shoe

# class IssueItemData(TypedDict):
#     shoe_id: int
#     original_name: str
#     original_brand: str
#     quantity: int # Quantity from the original order
#     reason: str # e.g., "out_of_stock", "price_changed_significantly", "item_not_found", "insufficient_stock"
#     details: Optional[dict] # e.g., {"old_price": X, "new_price": Y} or {"available": X}

def check_items_availability_and_price(
    db: Session,
    order_items_data: List[dict] # Expects list of dicts matching OrderItemData concept
) -> tuple[List[dict], List[dict], float]:
    """
    Checks availability and current price of items from a previous order.
    order_items_data: List of dicts, each with 'shoe_id', 'quantity', 'original_price', 'original_name', 'original_brand'.
    Returns: (verified_items, issue_items, new_total_price_for_verified)
    """
    verified_items: List[dict] = []
    issue_items: List[dict] = []
    new_total_price_for_verified: float = 0.0

    # Define a threshold for significant price change, e.g., 20% increase
    PRICE_CHANGE_SIGNIFICANT_THRESHOLD_PERCENT = 20.0

    for item_data in order_items_data:
        shoe = get_shoe(db, shoe_id=item_data["shoe_id"])

        if not shoe:
            issue_items.append({
                "shoe_id": item_data["shoe_id"],
                "original_name": item_data["original_name"],
                "original_brand": item_data["original_brand"],
                "quantity": item_data["quantity"],
                "reason": "item_not_found",
                "details": None
            })
            continue

        # Check stock
        if shoe.quantity_available == 0:
            issue_items.append({
                "shoe_id": shoe.id,
                "original_name": item_data["original_name"],
                "original_brand": item_data["original_brand"],
                "quantity": item_data["quantity"],
                "reason": "out_of_stock",
                "details": {"available": 0}
            })
            continue
        elif shoe.quantity_available < item_data["quantity"]:
            issue_items.append({
                "shoe_id": shoe.id,
                "original_name": item_data["original_name"],
                "original_brand": item_data["original_brand"],
                "quantity": item_data["quantity"],
                "reason": "insufficient_stock",
                "details": {"available": shoe.quantity_available, "requested": item_data["quantity"]}
            })
            # Option: could add the available quantity to verified_items if partial fulfillment is allowed
            # For now, marking the whole original quantity as an issue if not fully available.
            continue

        # Check price change
        price_change_percent = 0
        if item_data["original_price"] > 0: # Avoid division by zero if original price was 0
            price_change_percent = ((shoe.price - item_data["original_price"]) / item_data["original_price"]) * 100
        elif shoe.price > 0: # Original price was 0, new price is not
            price_change_percent = float('inf') # Effectively a significant change

        if price_change_percent > PRICE_CHANGE_SIGNIFICANT_THRESHOLD_PERCENT:
            issue_items.append({
                "shoe_id": shoe.id,
                "original_name": item_data["original_name"],
                "original_brand": item_data["original_brand"],
                "quantity": item_data["quantity"],
                "reason": "price_changed_significantly",
                "details": {"old_price": item_data["original_price"], "new_price": shoe.price, "percent_change": price_change_percent}
            })
            # Depending on policy, this could still be a verified item if user accepts.
            # For now, marking as an issue for user review.
            continue

        # If all checks pass, it's a verified item for reorder
        verified_items.append({
            "shoe_id": shoe.id,
            "quantity": item_data["quantity"], # Use original quantity for reorder
            "current_price": shoe.price,
            "current_name": shoe.name,
            "current_brand": shoe.brand,
            "available_stock": shoe.quantity_available,
            "original_price": item_data["original_price"], # Keep for reference
            "price_change_percent": price_change_percent # Can be slightly negative (cheaper) or small positive
        })
        new_total_price_for_verified += shoe.price * item_data["quantity"]

    return verified_items, issue_items, new_total_price_for_verified


# Modify search_shoes_by_criteria to accept exclude_ids
def search_shoes_by_criteria(db: Session, criteria: dict, skip: int = 0, limit: int = 100, exclude_ids: Optional[list[int]] = None) -> list[database.Shoe]:
    """
    Searches for shoes based on a dictionary of criteria.
    Criteria keys can be 'category', 'color', 'brand', 'size'.
    Uses ILIKE for partial matches on string fields.
    Can exclude a list of shoe IDs.
    """
    query = db.query(database.Shoe)

    if not criteria:
        if exclude_ids: # If no criteria but IDs to exclude
            query = query.filter(database.Shoe.id.notin_(exclude_ids))
        return query.offset(skip).limit(limit).all()

    if criteria.get("category"):
        query = query.filter(database.Shoe.category.ilike(f"%{criteria['category']}%"))
    if criteria.get("brand"):
        query = query.filter(database.Shoe.brand.ilike(f"%{criteria['brand']}%"))
    if criteria.get("color"):
        query = query.filter(database.Shoe.color.ilike(f"%{criteria['color']}%"))
    if criteria.get("size"):
        query = query.filter(database.Shoe.size_available.ilike(f"%{criteria['size']}%"))

    if exclude_ids:
        query = query.filter(database.Shoe.id.notin_(exclude_ids))

    return query.offset(skip).limit(limit).all()

# Modify get_content_based_recommendations to use exclude_ids when fetching candidates
def get_content_based_recommendations(db: Session, preferences: dict, limit: int = 5, exclude_ids: Optional[list[int]] = None) -> list[database.Shoe]:
    """
    Recommends shoes based on content similarity to user's attribute preferences.
    Excludes shoes already in the user's history (preferred_shoe_ids from preferences)
    and any additional exclude_ids provided.
    """
    if not preferences or not any([preferences.get("categories"), preferences.get("brands"), preferences.get("colors")]):
        logger.info("Not enough preference data to generate content-based recommendations.")
        return []

    # Combine user's history with dynamically excluded IDs
    all_excluded_ids = set(preferences.get("preferred_shoe_ids", []))
    if exclude_ids:
        all_excluded_ids.update(exclude_ids)

    # Fetch all candidate shoes not in the combined exclusion list
    candidate_shoes = db.query(database.Shoe).filter(database.Shoe.id.notin_(list(all_excluded_ids))).all()

    scored_shoes = []

    for shoe in candidate_shoes:
        score = 0
        if shoe.category and preferences.get("categories", {}).get(shoe.category.lower()):
            score += preferences["categories"][shoe.category.lower()] * 2
        if shoe.brand and preferences.get("brands", {}).get(shoe.brand.lower()):
            score += preferences["brands"][shoe.brand.lower()] * 1.5
        if shoe.color and preferences.get("colors", {}).get(shoe.color.lower()):
            score += preferences["colors"][shoe.color.lower()] * 1

        if score > 0:
            scored_shoes.append({"shoe": shoe, "score": score})

    scored_shoes.sort(key=lambda x: x["score"], reverse=True)
    recommended_shoes = [item["shoe"] for item in scored_shoes[:limit]]

    logger.info(f"Generated {len(recommended_shoes)} content-based recommendations. Top score: {scored_shoes[0]['score'] if scored_shoes else 0}")
    return recommended_shoes
