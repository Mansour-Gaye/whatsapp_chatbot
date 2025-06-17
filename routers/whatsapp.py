import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, Depends, HTTPException, Response, Query, Header
from sqlalchemy.orm import Session

import json # Ensure json is imported if not already
import config
from utils.whatsapp_utils import send_whatsapp_message, send_interactive_message
import crud
import database
from schemas import customer as customer_schema
from schemas import cart as cart_schema

# NLP imports
from nlp.nlp_processor import extract_shoe_entities
# Image Matching Service import
from services import image_matching_service

logger = logging.getLogger(__name__)
logging.basicConfig(level=config.LOGGING_LEVEL)

router = APIRouter(
    prefix="/whatsapp", # Common prefix for WhatsApp related endpoints
    tags=["whatsapp"],
    responses={403: {"description": "Forbidden or Verification Failed"}},
)

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_challenge: int = Query(..., alias="hub.challenge"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
):
    """
    Handles webhook verification requests from Meta.
    Compares hub.verify_token with the app's WHATSAPP_VERIFY_TOKEN.
    """
    logger.info(f"GET /webhook verification request: mode='{hub_mode}', token='{hub_verify_token}', challenge='{hub_challenge}'")
    if hub_mode == "subscribe" and hub_verify_token == config.WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verification successful.")
        return Response(content=str(hub_challenge), media_type="text/plain", status_code=200)
    else:
        logger.warning("Webhook verification failed. Mode or token mismatch.")
        raise HTTPException(status_code=403, detail="Webhook verification failed: Mode or token mismatch.")

@router.post("/webhook")
async def receive_whatsapp_message(
    request: Request,
    db: Session = Depends(database.get_db),
    x_hub_signature_256: Optional[str] = Header(None) # For signature validation (placeholder)
):
    """
    Handles incoming message notifications from WhatsApp.
    Parses the message, interacts with customer data, and sends a response.
    """
    payload_bytes = await request.body()
    payload_str = payload_bytes.decode("utf-8")
    logger.info(f"POST /webhook received payload: {payload_str}")

    # TODO: Implement X-Hub-Signature-256 validation if required by WhatsApp Cloud API settings
    # For now, we rely on the verify token for the GET request and assume payload is authentic if it reaches POST.
    # if x_hub_signature_256:
    #     if not verify_signature(payload_bytes, x_hub_signature_256):
    #         logger.warning("Signature validation failed.")
    #         raise HTTPException(status_code=403, detail="Signature validation failed.")
    # else:
    #     logger.warning("X-Hub-Signature-256 header missing. Potential security risk if validation is enforced.")
        # Depending on strictness, could raise HTTPException here.

    try:
        data = json.loads(payload_str)
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON payload.")
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    # Process WhatsApp message (simplified example)
    # WhatsApp Cloud API payload structure can be complex.
    # This example focuses on a simple text message.
    # {
    #   "object": "whatsapp_business_account",
    #   "entry": [{
    #     "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
    #     "changes": [{
    #       "field": "messages",
    #       "value": {
    #         "messaging_product": "whatsapp",
    #         "metadata": {
    #           "display_phone_number": "PHONE_NUMBER",
    #           "phone_number_id": "PHONE_NUMBER_ID"
    #         },
    #         "contacts": [{ "profile": { "name": "NAME" }, "wa_id": "USER_WHATSAPP_ID" }],
    #         "messages": [{
    #           "from": "USER_WHATSAPP_ID",
    #           "id": "MESSAGE_ID",
    #           "timestamp": "TIMESTAMP",
    #           "text": { "body": "MESSAGE_BODY" },
    #           "type": "text"
    #         }]
    #       }
    #     }]
    #   }]
    # }

    if data.get("object") == "whatsapp_business_account":
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") == "messages":
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    contacts = value.get("contacts", []) # Get contact info (name, wa_id)

                    for message in messages:
                        if message.get("type") == "text":
                            sender_wa_id = message.get("from")
                            message_text = message.get("text", {}).get("body", "").strip().lower() # For text messages
                            interactive_reply = message.get("interactive", {}).get("button_reply", {})
                            button_id = interactive_reply.get("id") if interactive_reply else None

                            sender_name = "Customer" # Default name
                            if contacts:
                                sender_name = contacts[0].get("profile",{}).get("name", sender_name)

                            logger.info(f"Received text message from {sender_name} ({sender_wa_id}): '{message_text}'")

                            # Customer Handling
                            customer = crud.get_customer_by_whatsapp_id(db, whatsapp_id=sender_wa_id)
                            if not customer:
                                logger.info(f"Customer with WA ID {sender_wa_id} not found. Creating new customer.")
                                customer = crud.create_customer(db, customer=customer_schema.CustomerCreate(whatsapp_id=sender_wa_id, name=sender_name))
                                await send_whatsapp_message(sender_wa_id, f"Welcome to our store, {sender_name}! Thanks for your first message.")
                            else:
                                logger.info(f"Existing customer {customer.name} ({customer.whatsapp_id}) found.")

                            # --- Text Message Handling ---
                            if message.get("type") == "text" and message_text:
                                logger.info(f"Processing text message: '{message_text}' from {sender_wa_id}")

                                # 1. Try NLP entity extraction
                                extracted_criteria = extract_shoe_entities(message_text)
                                logger.info(f"NLP extracted criteria: {extracted_criteria}")

                                if extracted_criteria: # If NLP found something relevant
                                    await handle_products_command(db, sender_wa_id, offset=0, limit=3, search_criteria=extracted_criteria, customer_id=customer.id)
                                else:
                                    # 2. Fallback to basic command parsing
                                    response_text = f"Je n'ai pas bien compris. Pouvez-vous reformuler ou essayer des commandes comme '/products'?" # Default if no NLP and no command
                                    if message_text in ["hi", "hello", "hey", "salut", "bonjour"]:
                                        response_text = f"Bonjour {customer.name}! Comment puis-je vous aider? Essayez de me décrire la chaussure que vous cherchez (ex: 'baskets noires taille 42') ou tapez '/products' pour voir notre catalogue."
                                        await send_whatsapp_message(sender_wa_id, response_text)
                                    elif message_text == "/products":
                                        # General product listing without specific NLP criteria
                                        await handle_products_command(db, sender_wa_id, offset=0, limit=3, search_criteria=None, customer_id=customer.id)
                                    elif message_text == "/popular" or message_text == "tendances":
                                        popular_shoes = crud.get_popular_shoes(db, limit=5)
                                        if popular_shoes:
                                            response_lines = ["Voici nos articles les plus populaires en ce moment :"]
                                            for shoe in popular_shoes:
                                                response_lines.append(f"- {shoe.name} ({shoe.brand}): {shoe.price} XOF")
                                            await send_whatsapp_message(sender_wa_id, "\n".join(response_lines))
                                        else:
                                            await send_whatsapp_message(sender_wa_id, "Je n'ai pas pu déterminer les articles populaires pour le moment. Essayez plus tard !")
                                    elif message_text in ["/foryou", "/recommendations", "suggestions", "pour vous"]:
                                        preferences = crud.get_user_attribute_preferences(db, customer_id=customer.id)
                                        if not preferences or not any([preferences.get("categories"), preferences.get("brands"), preferences.get("colors")]):
                                            await send_whatsapp_message(sender_wa_id, "Je n'ai pas encore assez d'informations sur vos goûts pour des suggestions très personnalisées. Parcourez nos produits avec '/products' ou essayez '/popular' pour voir les tendances !")
                                        else:
                                            recommendations = crud.get_content_based_recommendations(db, preferences=preferences, limit=3)
                                            if recommendations:
                                                response_lines = ["Voici quelques suggestions basées sur vos goûts :"]
                                                feedback_buttons = []
                                                for i, shoe in enumerate(recommendations):
                                                    response_lines.append(f"{i+1}. {shoe.name} ({shoe.brand}, {shoe.color}) - {shoe.price} XOF")
                                                    # For Pydantic v2, model_config = {"from_attributes": True} is needed for Shoe model if not already there for this to work seamlessly
                                                    if len(feedback_buttons) < 2: # Max 3 buttons, leave one for "Pas pour moi"
                                                        feedback_buttons.append({"id": f"refine_more_{shoe.id}", "title": f"Plus comme #{i+1}"})

                                                await send_whatsapp_message(sender_wa_id, "\n".join(response_lines))

                                                if feedback_buttons: # Only send feedback buttons if there were recommendations
                                                    feedback_buttons.append({"id": "refine_less_all", "title": "Pas pour moi"})
                                                    await send_interactive_message(
                                                        recipient_id=sender_wa_id,
                                                        body_text="Ces suggestions vous plaisent-elles ou souhaitez-vous affiner ?",
                                                        buttons=feedback_buttons
                                                    )
                                            else:
                                                await send_whatsapp_message(sender_wa_id, "Je n'ai pas trouvé de nouvelles recommandations pour vous pour le moment. Découvrez nos nouveautés avec '/products' !")
                                    else: # Default non-understanding message
                                        await send_whatsapp_message(sender_wa_id, response_text)

                            # --- Interactive Message (Button Reply) Handling ---
                            elif message.get("type") == "interactive" and button_id:
                                logger.info(f"Processing button reply with ID: '{button_id}' from {sender_wa_id}")

                                if button_id.startswith("add_cart_"):
                                    shoe_id_str = button_id.replace("add_cart_", "")
                                    try:
                                        shoe_id = int(shoe_id_str)
                                        cart = crud.get_or_create_cart(db, customer_id=customer.id)
                                        # Assume quantity 1 for button click
                                        cart_item_schema = cart_schema.CartItemCreate(shoe_id=shoe_id, quantity=1)

                                        db_cart_item = crud.add_item_to_cart(db, cart_id=cart.id, shoe_id=cart_item_schema.shoe_id, quantity=cart_item_schema.quantity)
                                        shoe = crud.get_shoe(db, shoe_id)
                                        await send_whatsapp_message(sender_wa_id, f"'{shoe.name if shoe else 'Product'}' added to your cart!")
                                    except ValueError as e: # Handles non-integer shoe_id or stock issues from crud
                                        logger.error(f"Error adding to cart via button: {e}")
                                        await send_whatsapp_message(sender_wa_id, f"Sorry, there was an issue adding that item to your cart: {e}")
                                    except Exception as e:
                                        logger.error(f"Unexpected error adding to cart via button: {e}")
                                        await send_whatsapp_message(sender_wa_id, "An unexpected error occurred. Please try again.")

                                elif button_id.startswith("view_more_"): # Example: "view_more_offset_3_limit_3_criteria_{json_criteria_base64}"
                                    parts = button_id.split("_")
                                    try:
                                        offset = int(parts[2])
                                        limit = int(parts[4])
                                        criteria_json_str = None
                                        if len(parts) > 6 and parts[5] == "criteria":
                                            # This part needs robust parsing and error handling if criteria are complex
                                            # For now, assuming simple criteria or no criteria in button for simplicity as per subtask instructions
                                            # criteria_json_str = parts[6]
                                            # criteria = json.loads(base64.urlsafe_b64decode(criteria_json_str).decode())
                                            pass # Keeping pagination simple for now for generic /products view

                                        # For this iteration, view_more and prev_page will only work for general browsing,
                                        # not for paginating NLP search results, as per subtask note.
                                        # Pass customer.id if these buttons should also potentially trigger updates or personalized content
                                        await handle_products_command(db, sender_wa_id, offset=offset, limit=limit, search_criteria=None, customer_id=customer.id)
                                    except Exception as e:
                                        logger.error(f"Error parsing view_more button ID '{button_id}': {e}")
                                        await send_whatsapp_message(sender_wa_id, "Sorry, I couldn't process that 'View More' request.")

                                elif button_id.startswith("prev_page_"):
                                    parts = button_id.split("_")
                                    try:
                                        offset = int(parts[2])
                                        limit = int(parts[4])
                                        await handle_products_command(db, sender_wa_id, offset=max(0, offset), limit=limit, search_criteria=None, customer_id=customer.id)
                                    except Exception as e:
                                        logger.error(f"Error parsing prev_page button ID '{button_id}': {e}")
                                        await send_whatsapp_message(sender_wa_id, "Sorry, I couldn't process that 'Previous Page' request.")
                                else:
                                    logger.warning(f"Unhandled button ID: {button_id}")
                                    await send_whatsapp_message(sender_wa_id, "Sorry, I didn't understand that button click.")

                            # --- Image Message Handling ---
                            elif message.get("type") == "image":
                                image_id = message.get("image", {}).get("id")
                                if image_id:
                                    logger.info(f"Received image message from {sender_wa_id} with media ID: {image_id}")
                                    await send_whatsapp_message(sender_wa_id, "J'analyse votre image, un instant... 🖼️")

                                    try:
                                        matching_shoes = image_matching_service.find_shoes_by_image_style(db, image_identifier=image_id, limit=3)
                                        if matching_shoes:
                                            response_lines = ["Voici des chaussures qui pourraient correspondre au style de votre image :"]
                                            for shoe in matching_shoes:
                                                response_lines.append(f"- {shoe.name} ({shoe.brand}, {shoe.color}): {shoe.price} XOF")
                                            # TODO: Potentially use handle_products_command for richer display and actions
                                            await send_whatsapp_message(sender_wa_id, "\n".join(response_lines))

                                            # Update last viewed for the first recommended item from image search
                                            if customer and matching_shoes:
                                                crud.update_last_viewed_products(db, customer_id=customer.id, product_id=matching_shoes[0].id)
                                        else:
                                            await send_whatsapp_message(sender_wa_id, "Je n'ai pas trouvé de chaussures correspondantes dans notre catalogue pour le moment. Essayez une autre image ou une recherche par texte.")
                                    except Exception as e:
                                        logger.error(f"Error during image style matching for image ID {image_id}: {e}")
                                        await send_whatsapp_message(sender_wa_id, "Désolé, une erreur s'est produite lors de l'analyse de votre image.")
                                else:
                                    logger.warning(f"Received image message from {sender_wa_id} but no image ID found.")
                                    await send_whatsapp_message(sender_wa_id, "J'ai reçu une image, mais je n'ai pas pu l'analyser. Veuillez réessayer.")
                            else:
                                logger.info(f"Received unhandled message type: {message.get('type')}")
                                await send_whatsapp_message(sender_wa_id, "Désolé, je ne peux traiter que les messages texte, les images et les clics sur les boutons pour le moment.")

    return Response(status_code=200, content="EVENT_RECEIVED") # Acknowledge receipt to WhatsApp


async def handle_products_command(db: Session, recipient_wa_id: str, offset: int, limit: int, search_criteria: Optional[dict] = None, customer_id: Optional[int] = None, exclude_shoe_ids: Optional[List[int]] = None):
    """
    Fetches products (either general or based on search_criteria) and sends them.
    Can exclude specific shoe_ids from results.
    For NLP search results, pagination is simplified.
    If customer_id and search_criteria are provided and shoes are found, updates last_viewed_products.
    """
    logger.info(f"Handling products display for {recipient_wa_id} (customer_id: {customer_id}), offset={offset}, limit={limit}, criteria={search_criteria}, exclude_ids={exclude_shoe_ids}")

    if search_criteria:
        shoes = crud.search_shoes_by_criteria(db, criteria=search_criteria, skip=offset, limit=limit, exclude_ids=exclude_shoe_ids)
        total_shoes_count = len(shoes) # This count is only for the current filtered list if not paginating NLP fully
        is_nlp_search = True
        if not shoes:
            await send_whatsapp_message(recipient_wa_id, "Désolé, je n'ai rien trouvé pour ces critères. Essayez autre chose ?")
            return
        product_message_body = "Voici les résultats pour votre recherche :\n"

        # Update last viewed products if this is an NLP search and we have a customer ID and products
        if customer_id and shoes:
            try:
                # Log the first product as viewed for this search
                crud.update_last_viewed_products(db, customer_id=customer_id, product_id=shoes[0].id)
                logger.info(f"Updated last viewed products for customer {customer_id} with shoe {shoes[0].id}")
            except Exception as e:
                logger.error(f"Error updating last_viewed_products for customer {customer_id}: {e}")

    else: # General browsing
        shoes = crud.get_shoes(db, skip=offset, limit=limit) # get_shoes doesn't currently support exclude_ids, would need update if generic product view needs it.
        total_shoes_count = db.query(database.Shoe).count() # Total for general browsing
        is_nlp_search = False
        if not shoes:
            await send_whatsapp_message(recipient_wa_id, "Il n'y a plus de produits à afficher ou notre stock est vide pour le moment.")
            return
        product_message_body = "Voici quelques-uns de nos produits :\n"
    interactive_buttons = []

    for shoe in shoes:
        product_message_body += f"\n👟 *{shoe.name}* ({shoe.brand})\n"
        product_message_body += f"   Price: {shoe.price} XOF\n"
        product_message_body += f"   Available: {shoe.quantity_available}\n"
        # Each product can have an "Add to Cart" button, max 3 buttons total for the message.
        # So, if we list 1 product, it can have Add to Cart + View More + Prev Page.
        # If we list 2 products, each can have Add to Cart, that's 2 buttons. Then 1 for View More/Prev.
        # Let's simplify: show products, then common navigation buttons. Add to cart can be by typing name later.
        # For now, let's try one "Add to cart" button per message for the first product if space allows, or a generic message.


    interactive_buttons = []
    for shoe in shoes:
        product_message_body += f"\n👟 *{shoe.name}* ({shoe.brand})\n"
        product_message_body += f"   Prix: {shoe.price} XOF | Couleur: {shoe.color}\n"
        product_message_body += f"   Tailles: {shoe.size_available} | Stock: {shoe.quantity_available}\n"
        # Add to cart button for each product (if not too many buttons already)
        # Max 3 buttons. If we have "View More" and "Previous", only one "Add to Cart" can be shown.
        # For NLP results, we might want to show an "Add to Cart" for the top item if space.
        if len(interactive_buttons) < 1 and is_nlp_search: # Only add one "Add to cart" for NLP results for now
             interactive_buttons.append({"id": f"add_cart_{shoe.id}", "title": f"Ajouter {shoe.name[:10]}..."})


    # Pagination Buttons - Only for general browsing, not for NLP search results in this iteration
    if not is_nlp_search:
        current_page_end_index = offset + len(shoes)
        if current_page_end_index < total_shoes_count:
            interactive_buttons.append({
                "id": f"view_more_offset_{current_page_end_index}_limit_{limit}", # No criteria needed for general browsing
                "title": "➡️ Voir plus"
            })

        if offset > 0:
            prev_offset = max(0, offset - limit)
            interactive_buttons.append({
                "id": f"prev_page_offset_{prev_offset}_limit_{limit}", # No criteria
                "title": "⬅️ Précédent"
            })

    if not any(btn["id"].startswith("add_cart_") for btn in interactive_buttons) and shoes and not is_nlp_search:
         product_message_body += "\n\nℹ️ Tapez le nom du produit pour l'ajouter au panier ou pour plus de détails."
    elif is_nlp_search and not any(btn["id"].startswith("add_cart_") for btn in interactive_buttons) and shoes:
        product_message_body += "\n\nℹ️ Pour ajouter un article, essayez 'ajouter [nom du produit] au panier'."


    if interactive_buttons:
        await send_interactive_message(
            recipient_id=recipient_wa_id,
            body_text=product_message_body.strip(),
            buttons=interactive_buttons
        )
    else:
        # If no buttons (e.g., NLP search result with no "Add to cart" space, or end of general list)
        final_message = product_message_body.strip()
        if is_nlp_search:
            final_message += "\n\nPour une autre recherche, décrivez simplement ce que vous voulez."
        elif not shoes : #This case should be handled earlier
             final_message = "Désolé, aucun produit ne correspond à ces critères pour le moment."
        else: # End of general product list
            final_message += "\n\nC'est tout pour le moment !"
        await send_whatsapp_message(recipient_wa_id, final_message)
