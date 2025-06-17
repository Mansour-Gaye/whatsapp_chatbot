import random
from sqlalchemy.orm import Session
from typing import List, Dict, Any

# Assuming crud.py and database.py (for Shoe model) are accessible
# Adjust imports based on your project structure
# from .. import crud # If services is a package at the same level as crud
# from ..database import Shoe # If services is a package
# For now, using direct imports assuming PYTHONPATH is set up or they are in accessible locations.
import crud  # This provides search_shoes_by_criteria
from database import Shoe # For type hinting
import logging

logger = logging.getLogger(__name__)

def simulate_ai_image_analysis(image_identifier: str) -> Dict[str, Any]:
    """
    Simulates an AI image analysis service.
    Based on the image_identifier (or randomly), returns a dictionary of attributes.
    """
    logger.info(f"Simulating AI analysis for image_identifier: {image_identifier}")

    # Example specific simulations based on a mock media ID
    if "test_image_id_sandals_blue" in image_identifier:
        return {"category": "sandales", "color": "bleu", "attributes": ["sandales", "bleu", "cuir"]}
    elif "test_image_id_red_boots" in image_identifier:
        return {"category": "bottes", "color": "rouge", "attributes": ["bottes", "rouge", "talons hauts"]}
    elif "test_image_id_nike_sneakers" in image_identifier:
        return {"brand": "nike", "category": "baskets", "attributes": ["nike", "baskets", "sport", "logo"]}

    # Default simulation: randomly pick some common attributes
    simulated_categories = ["baskets", "sandales", "bottes", None] # None means category might not be clear
    simulated_colors = ["noir", "blanc", "rouge", "bleu", None] # None means color might not be clear
    simulated_brands = ["nike", "adidas", "puma", None] # None means brand might not be clear

    # Pick one dominant characteristic for category, color, brand if possible
    category = random.choice(simulated_categories)
    color = random.choice(simulated_colors)
    brand = random.choice(simulated_brands) # Less likely to be guessed by generic AI

    attributes = []
    if category:
        attributes.append(category)
    if color:
        attributes.append(color)
    # Brand is less likely to be a generic attribute unless it's very prominent like a logo
    # if brand:
    #     attributes.append(brand)

    # Add some generic style attributes
    style_keywords = ["cuir", "tissu", "sportif", "élégant", "décontracté", "motif"]
    if random.random() > 0.5: # 50% chance of adding a random style keyword
        attributes.append(random.choice(style_keywords))

    simulated_response = {"attributes": list(set(attributes)) } # Ensure unique attributes
    if category:
        simulated_response["category"] = category
    if color:
        simulated_response["color"] = color
    if brand and random.random() > 0.3: # 30% chance AI also suggests a brand
         simulated_response["brand"] = brand
         if brand not in simulated_response["attributes"]:
            simulated_response["attributes"].append(brand)


    logger.info(f"Simulated AI response: {simulated_response}")
    return simulated_response


def find_shoes_by_image_style(db: Session, image_identifier: str, limit: int = 3) -> List[Shoe]:
    """
    Finds shoes that match the style from an image (simulated AI analysis).
    """
    ai_output = simulate_ai_image_analysis(image_identifier)

    # Use the 'attributes' list to search broadly, or specific fields if AI provides them.
    # We can adapt search_shoes_by_criteria or create a more specialized query.
    # For now, let's use the specific criteria if available (category, color, brand)
    # and fall back to a broader search using all 'attributes' if specific ones are missing.

    search_criteria = {}
    if ai_output.get("category"):
        search_criteria["category"] = ai_output["category"]
    if ai_output.get("color"):
        search_criteria["color"] = ai_output["color"]
    if ai_output.get("brand"):
        search_criteria["brand"] = ai_output["brand"]

    if search_criteria: # If we have specific fields from AI
        logger.info(f"Searching shoes using AI-derived specific criteria: {search_criteria}")
        shoes = crud.search_shoes_by_criteria(db, criteria=search_criteria, limit=limit)
    else:
        # If AI didn't give specific category/color/brand, use the generic 'attributes' list
        # to search more broadly. This requires search_shoes_by_criteria to handle a list of keywords.
        # For now, let's assume search_shoes_by_criteria can take a general 'query' string.
        # We'll join the attributes.
        if ai_output.get("attributes"):
            query_string = " ".join(ai_output["attributes"])
            logger.info(f"Searching shoes using AI-derived attribute query string: '{query_string}'")
            # search_shoes_by_criteria expects a dict. We need to adapt or use a different function.
            # Let's use the existing search_shoes (general text search) for this fallback.
            shoes = crud.search_shoes(db, query=query_string, limit=limit)
        else:
            logger.info("AI simulation provided no usable attributes or criteria.")
            shoes = []

    return shoes

if __name__ == "__main__":
    # This test requires a database session and crud operations.
    # It's better to test this as part of an integration test or with mocks.
    print("Testing image matching service (simulation)...")

    # Simulate some image IDs
    test_ids = ["test_image_id_sandals_blue", "test_image_id_red_boots", "test_image_id_nike_sneakers", "random_image_id_123"]
    for img_id in test_ids:
        print(f"\n--- Testing with Image ID: {img_id} ---")
        sim_output = simulate_ai_image_analysis(img_id)
        print(f"Simulated AI Output: {sim_output}")
        # To test find_shoes_by_image_style, you'd need to set up a DB session:
        # from database import SessionLocal
        # db = SessionLocal()
        # try:
        #     recommended_shoes = find_shoes_by_image_style(db, img_id)
        #     if recommended_shoes:
        #         print(f"Found {len(recommended_shoes)} matching shoes:")
        #         for shoe in recommended_shoes:
        #             print(f"  - {shoe.name} (Brand: {shoe.brand}, Category: {shoe.category}, Color: {shoe.color})")
        #     else:
        #         print("No matching shoes found in DB for this simulation.")
        # finally:
        #     db.close()
    print("\nNote: Full test of find_shoes_by_image_style requires database connection and data.")
