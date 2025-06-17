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
                                    # Using a default limit for NLP results display
                                    await handle_products_command(db, sender_wa_id, offset=0, limit=3, search_criteria=extracted_criteria)
                                else:
                                    # 2. Fallback to basic command parsing
                                    response_text = f"Je n'ai pas bien compris. Pouvez-vous reformuler ou essayer des commandes comme '/products'?" # Default if no NLP and no command
                                    if message_text in ["hi", "hello", "hey", "salut", "bonjour"]:
                                        response_text = f"Bonjour {customer.name}! Comment puis-je vous aider? Essayez de me décrire la chaussure que vous cherchez (ex: 'baskets noires taille 42') ou tapez '/products' pour voir notre catalogue."
                                        await send_whatsapp_message(sender_wa_id, response_text)
                                    elif message_text == "/products":
                                        # General product listing without specific NLP criteria
                                        await handle_products_command(db, sender_wa_id, offset=0, limit=3, search_criteria=None)
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
                                        await handle_products_command(db, sender_wa_id, offset=offset, limit=limit, search_criteria=None)
                                    except Exception as e:
                                        logger.error(f"Error parsing view_more button ID '{button_id}': {e}")
                                        await send_whatsapp_message(sender_wa_id, "Sorry, I couldn't process that 'View More' request.")

                                elif button_id.startswith("prev_page_"):
                                    parts = button_id.split("_")
                                    try:
                                        offset = int(parts[2])
                                        limit = int(parts[4])
                                        # Similar to view_more, keeping pagination for generic browsing for now
                                        await handle_products_command(db, sender_wa_id, offset=max(0, offset), limit=limit, search_criteria=None)
                                    except Exception as e:
                                        logger.error(f"Error parsing prev_page button ID '{button_id}': {e}")
                                        await send_whatsapp_message(sender_wa_id, "Sorry, I couldn't process that 'Previous Page' request.")
                                else:
                                    logger.warning(f"Unhandled button ID: {button_id}")
                                    await send_whatsapp_message(sender_wa_id, "Sorry, I didn't understand that button click.")
                            else:
                                logger.info(f"Received non-text, non-interactive_button_reply message type: {message.get('type')}")
                                await send_whatsapp_message(sender_wa_id, "Sorry, I can only process text messages and button clicks for now.")

    return Response(status_code=200, content="EVENT_RECEIVED") # Acknowledge receipt to WhatsApp


async def handle_products_command(db: Session, recipient_wa_id: str, offset: int, limit: int, search_criteria: Optional[dict] = None):
    """
    Fetches products (either general or based on search_criteria) and sends them.
    For NLP search results (if search_criteria is provided), pagination is currently simplified:
    it shows the first page and does not include "View More" / "Previous" buttons for that specific search.
    """
    logger.info(f"Handling products display for {recipient_wa_id}, offset={offset}, limit={limit}, criteria={search_criteria}")

    if search_criteria:
        shoes = crud.search_shoes_by_criteria(db, criteria=search_criteria, skip=offset, limit=limit)
        # For NLP results, we currently don't implement pagination via buttons to keep it simple.
        # So, total_shoes_count and pagination buttons are only for general browsing.
        total_shoes_count = len(shoes) # Or, count all matching criteria if we were to paginate NLP
        is_nlp_search = True
        if not shoes:
            await send_whatsapp_message(recipient_wa_id, "Désolé, je n'ai rien trouvé pour ces critères. Essayez autre chose ?")
            return
        product_message_body = "Voici les résultats pour votre recherche :\n"

    else: # General browsing
        shoes = crud.get_shoes(db, skip=offset, limit=limit)
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
