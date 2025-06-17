import json
import logging
from typing import Any, Dict, Optional, List # Added List for type hint

from fastapi import APIRouter, Request, Depends, HTTPException, Response, Query, Header
from sqlalchemy.orm import Session

import config # Assuming config.py is at root or in PYTHONPATH
from utils.whatsapp_utils import send_whatsapp_message, send_interactive_message, send_order_status_update_notification
import crud
import database # Assuming database.py is at root or in PYTHONPATH
from schemas import customer as customer_schema
from schemas import cart as cart_schema
from schemas import order as order_schema

# NLP imports
from nlp.nlp_processor import extract_shoe_entities
# Image Matching Service import
from services import image_matching_service
from utils.localization import get_localized_string, DEFAULT_LANGUAGE

logger = logging.getLogger(__name__)
# logging.basicConfig(level=config.LOGGING_LEVEL) # Usually configured by FastAPI itself or main.py

router = APIRouter(
    prefix="/whatsapp",
    tags=["whatsapp"],
    responses={403: {"description": "Forbidden or Verification Failed"}},
)

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_challenge: int = Query(..., alias="hub.challenge"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
):
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
    x_hub_signature_256: Optional[str] = Header(None)
):
    payload_bytes = await request.body()
    payload_str = payload_bytes.decode("utf-8")
    logger.info(f"POST /webhook received payload: {payload_str}")

    try:
        data = json.loads(payload_str)
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON payload.")
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    if data.get("object") == "whatsapp_business_account":
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") == "messages":
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    contacts = value.get("contacts", [])

                    for message in messages:
                        sender_wa_id = message.get("from")
                        message_type = message.get("type")

                        sender_name = "Customer"
                        if contacts:
                            sender_name = contacts[0].get("profile",{}).get("name", sender_name)

                        # Customer Handling & Language Setup
                        lang = DEFAULT_LANGUAGE
                        customer = crud.get_customer_by_whatsapp_id(db, whatsapp_id=sender_wa_id)
                        if not customer:
                            logger.info(f"Customer with WA ID {sender_wa_id} not found. Creating new customer with default lang '{DEFAULT_LANGUAGE}'.")
                            customer = crud.create_customer(db, customer=customer_schema.CustomerCreate(whatsapp_id=sender_wa_id, name=sender_name, preferred_language=DEFAULT_LANGUAGE))
                            lang = customer.preferred_language
                            await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "greeting_new_customer", name=sender_name))
                        else:
                            lang = customer.preferred_language if customer.preferred_language else DEFAULT_LANGUAGE
                            logger.info(f"Existing customer {customer.name} ({customer.whatsapp_id}, lang: {lang}) found.")

                        # --- Text Message Handling ---
                        if message_type == "text":
                            message_text = message.get("text", {}).get("body", "").strip().lower()
                            logger.info(f"Processing text message: '{message_text}' from {sender_wa_id} (lang: {lang})")
                            default_response_text = get_localized_string(lang, "default_command_fallback", name=customer.name)

                            extracted_criteria = {}
                            if lang == 'fr': # Assuming NLP is French-optimized
                                extracted_criteria = extract_shoe_entities(message_text)
                                logger.info(f"NLP (fr) extracted criteria: {extracted_criteria}")

                            if extracted_criteria:
                                await handle_products_command(db, sender_wa_id, offset=0, limit=3, lang=lang, search_criteria=extracted_criteria, customer_id=customer.id)
                            else: # Fallback to command parsing
                                if message_text in ["hi", "hello", "hey", "salut", "bonjour"]:
                                    await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "greeting_existing_customer", name=customer.name))
                                elif message_text == "/products":
                                    await handle_products_command(db, sender_wa_id, offset=0, limit=3, lang=lang, search_criteria=None, customer_id=customer.id)
                                elif message_text == "/popular" or message_text == get_localized_string(lang, "menu_button_popular", default_lang='fr').lower():
                                    popular_shoes = crud.get_popular_shoes(db, limit=5)
                                    if popular_shoes:
                                        response_lines = [get_localized_string(lang, "popular_products_header")]
                                        for shoe in popular_shoes:
                                            response_lines.append(f"- {shoe.name} ({shoe.brand}): {shoe.price:.0f} XOF")
                                        await send_whatsapp_message(sender_wa_id, "\n".join(response_lines))
                                    else:
                                        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "popular_products_unavailable"))
                                elif message_text in ["/foryou", "/recommendations", "suggestions", "pour vous"]:
                                    await handle_foryou_command(db, sender_wa_id, customer, lang)
                                elif message_text in ["/repeatorder", "/lastorder", "répéter ma dernière commande", "derniere commande"]:
                                    await handle_repeat_order_command(db, sender_wa_id, customer, lang=lang)
                                elif message_text in ["/menu", "/aide", "menu principal"]:
                                    await send_main_menu(sender_wa_id, lang=lang)
                                elif message_text.startswith("/setlang"):
                                    parts = message_text.split()
                                    if len(parts) == 2 and parts[1] in ['fr', 'en']:
                                        new_lang_code = parts[1]
                                        updated_customer = crud.update_customer_language(db, customer_id=customer.id, lang_code=new_lang_code)
                                        if updated_customer:
                                            await send_whatsapp_message(sender_wa_id, get_localized_string(new_lang_code, "language_set_confirmation"))
                                        else:
                                            await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "generic_error_message", default_lang='en')) # Fallback
                                    else:
                                        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "invalid_language_code"))
                                elif message_text.startswith("/admin_update_order"):
                                    await handle_admin_update_order_command(db, sender_wa_id, message_text, lang) # lang for admin's confirmation
                                else:
                                    await send_whatsapp_message(sender_wa_id, default_response_text)

                        # --- Interactive Message (Button Reply) Handling ---
                        elif message_type == "interactive":
                            interactive_reply = message.get("interactive", {}).get("button_reply", {})
                            button_id = interactive_reply.get("id") if interactive_reply else None
                            if button_id:
                                logger.info(f"Processing button reply with ID: '{button_id}' from {sender_wa_id} (lang: {lang})")
                                # Menu and category buttons
                                if button_id == "menu_new_arrivals":
                                    await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "product_list_header_general"))
                                    await handle_products_command(db, sender_wa_id, offset=0, limit=5, lang=lang, customer_id=customer.id)
                                elif button_id == "menu_categories":
                                    await send_category_menu(db, sender_wa_id, lang=lang)
                                elif button_id == "menu_popular":
                                    popular_shoes = crud.get_popular_shoes(db, limit=5)
                                    if popular_shoes:
                                        response_lines = [get_localized_string(lang, "popular_products_header")]
                                        for shoe in popular_shoes: response_lines.append(f"- {shoe.name} ({shoe.brand}): {shoe.price:.0f} XOF")
                                        await send_whatsapp_message(sender_wa_id, "\n".join(response_lines))
                                    else: await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "popular_products_unavailable"))
                                elif button_id == "menu_last_order":
                                    await handle_repeat_order_command(db, sender_wa_id, customer, lang=lang)
                                elif button_id == "menu_smart_search_prompt":
                                    search_prompt_text = get_localized_string(lang, "smart_search_prompt_example", example_query="'baskets noires taille 42'")
                                    if lang == 'en': search_prompt_text += "\n" + get_localized_string(lang, "nlp_english_limitation_note")
                                    await send_whatsapp_message(sender_wa_id, search_prompt_text)
                                elif button_id == "menu_help":
                                    await send_main_menu(sender_wa_id, lang=lang)
                                elif button_id.startswith("category_"):
                                    category_name_from_id = button_id.replace("category_", "").replace("_", " ")
                                    await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "displaying_products_for_category", category_name=category_name_from_id.title()))
                                    await handle_products_command(db, sender_wa_id, offset=0, limit=5, lang=lang, search_criteria={"category": category_name_from_id}, customer_id=customer.id)
                                # Recommendation feedback buttons
                                elif button_id.startswith("refine_more_"):
                                    await handle_refine_more_command(db, sender_wa_id, customer, button_id, lang)
                                elif button_id == "refine_less_all":
                                    await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "recommendations_feedback_thanks"))
                                # Repeat order buttons
                                elif button_id.startswith("confirm_repeat_verified_"):
                                    original_order_id_str = button_id.replace("confirm_repeat_verified_", "")
                                    try:
                                        original_order_id = int(original_order_id_str)
                                        await handle_confirm_repeat_order(db, sender_wa_id, customer, original_order_id, lang=lang)
                                    except ValueError:
                                        logger.error(f"Could not parse order_id from button_id for repeat order: {button_id}")
                                        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "generic_error_message", default_lang='en'))
                                elif button_id == "cancel_repeat":
                                    await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "repeat_order_cancelled"))
                                # Add to cart (simple version, might need more context if ambiguous)
                                elif button_id.startswith("add_cart_"):
                                    await handle_add_to_cart_button(db, sender_wa_id, customer, button_id, lang)
                                else:
                                    logger.warning(f"Unhandled button ID: {button_id}")
                                    await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "unhandled_button_click_default"))

                        # --- Image Message Handling ---
                        elif message_type == "image":
                            image_id = message.get("image", {}).get("id")
                            if image_id:
                                logger.info(f"Received image message from {sender_wa_id} with media ID: {image_id}")
                                await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "image_analysis_ack"))
                                try:
                                    matching_shoes = image_matching_service.find_shoes_by_image_style(db, image_identifier=image_id, limit=3)
                                    if matching_shoes:
                                        response_lines = [get_localized_string(lang, "image_match_header")]
                                        for shoe in matching_shoes: response_lines.append(f"- {shoe.name} ({shoe.brand}, {shoe.color}): {shoe.price:.0f} XOF")
                                        await send_whatsapp_message(sender_wa_id, "\n".join(response_lines))
                                        if customer and matching_shoes:
                                            crud.update_last_viewed_products(db, customer_id=customer.id, product_id=matching_shoes[0].id)
                                    else:
                                        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "image_match_none"))
                                except Exception as e:
                                    logger.error(f"Error during image style matching for image ID {image_id}: {e}")
                                    await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "image_match_error_generic"))
                            else:
                                logger.warning(f"Received image message from {sender_wa_id} but no image ID found.")
                                await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "image_no_id_error"))
                        else: # Other message types
                            logger.info(f"Received unhandled message type: {message_type}")
                            await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "unhandled_message_type_default"))

    return Response(status_code=200, content="EVENT_RECEIVED")

# Helper command handlers, refactored for clarity and localization
async def handle_foryou_command(db: Session, sender_wa_id: str, customer: database.Customer, lang: str):
    preferences = crud.get_user_attribute_preferences(db, customer_id=customer.id)
    if not preferences or not any([preferences.get("categories"), preferences.get("brands"), preferences.get("colors")]):
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "recommendations_foryou_insufficient_data"))
    else:
        recommendations = crud.get_content_based_recommendations(db, preferences=preferences, limit=3)
        if recommendations:
            response_lines = [get_localized_string(lang, "recommendations_foryou_header")]
            feedback_buttons = []
            for i, shoe in enumerate(recommendations):
                response_lines.append(f"{i+1}. {shoe.name} ({shoe.brand}, {shoe.color}) - {shoe.price:.0f} XOF")
                if len(feedback_buttons) < 2: # Max 2 item-specific feedback buttons
                    feedback_buttons.append({"id": f"refine_more_{shoe.id}", "title": get_localized_string(lang, "recommendations_button_more_like", num=i+1)[:20]})

            await send_whatsapp_message(sender_wa_id, "\n".join(response_lines))

            if feedback_buttons:
                feedback_buttons.append({"id": "refine_less_all", "title": get_localized_string(lang, "recommendations_button_less_like_all")[:20]})
                await send_interactive_message(
                    recipient_id=sender_wa_id,
                    body_text=get_localized_string(lang, "recommendations_feedback_prompt"),
                    buttons=feedback_buttons
                )
        else:
            await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "recommendations_foryou_none_found"))

async def handle_refine_more_command(db: Session, sender_wa_id: str, customer: database.Customer, button_id: str, lang: str):
    shoe_id_str = button_id.replace("refine_more_", "")
    try:
        original_shoe_id = int(shoe_id_str)
        original_shoe = crud.get_shoe(db, shoe_id=original_shoe_id)
        if original_shoe:
            search_criteria = {}
            if original_shoe.category: search_criteria["category"] = original_shoe.category
            if original_shoe.brand: search_criteria["brand"] = original_shoe.brand
            if original_shoe.color: search_criteria["color"] = original_shoe.color

            if not search_criteria:
                await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "recommendations_refining_no_details"))
            else:
                await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "recommendations_refining_more_like", item_name=original_shoe.name))
                await handle_products_command(db, sender_wa_id, offset=0, limit=3, lang=lang,
                                              search_criteria=search_criteria,
                                              customer_id=customer.id,
                                              exclude_shoe_ids=[original_shoe_id])
        else:
            await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "refine_no_shoe_details_error"))
    except ValueError:
        logger.error(f"Could not parse shoe_id from button_id for refine_more: {button_id}")
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "refine_error_processing"))

async def handle_add_to_cart_button(db: Session, sender_wa_id: str, customer: database.Customer, button_id: str, lang: str):
    shoe_id_str = button_id.replace("add_cart_", "")
    try:
        shoe_id = int(shoe_id_str)
        cart = crud.get_or_create_cart(db, customer_id=customer.id)
        cart_item_pydantic = cart_schema.CartItemCreate(shoe_id=shoe_id, quantity=1) # Assume quantity 1 for button

        db_cart_item = crud.add_item_to_cart(db, cart_id=cart.id, shoe_id=cart_item_pydantic.shoe_id, quantity=cart_item_pydantic.quantity)
        shoe = crud.get_shoe(db, shoe_id) # Fetch shoe for its name
        item_name = shoe.name if shoe else get_localized_string(lang, "unknown_product_name_fallback", default_lang='en')
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "cart_add_success", item_name=item_name))
    except ValueError as e:
        shoe_name_for_error = crud.get_shoe(db, int(shoe_id_str)).name if shoe_id_str.isdigit() else "this item"
        logger.error(f"Error adding to cart (shoe_id: {shoe_id_str}) via button: {e}")
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "cart_add_value_error", item_name=shoe_name_for_error, error=str(e)))
    except Exception as e:
        shoe_name_for_error = crud.get_shoe(db, int(shoe_id_str)).name if shoe_id_str.isdigit() else "this item"
        logger.error(f"Unexpected error adding to cart (shoe_id: {shoe_id_str}) via button: {e}")
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "cart_add_generic_error", item_name=shoe_name_for_error))

async def handle_admin_update_order_command(db: Session, sender_wa_id: str, message_text: str, lang: str): # lang for admin's confirmation
    parts = message_text.split()
    if len(parts) == 3:
        try:
            order_id_to_update = int(parts[1])
            new_status_for_order = parts[2].lower()
            allowed_statuses = ["pending", "processing", "shipped", "completed", "cancelled", "payment_pending", "ready_for_pickup"]
            if new_status_for_order not in allowed_statuses:
                # Admin messages can be simpler / less verbose or stay in default lang
                await send_whatsapp_message(sender_wa_id, get_localized_string(DEFAULT_LANGUAGE, "order_update_admin_invalid_status_format", status=new_status_for_order, allowed_statuses=", ".join(allowed_statuses)))
            else:
                updated_order = crud.update_order_status(db, order_id=order_id_to_update, new_status=new_status_for_order)
                if updated_order:
                    order_customer = crud.get_customer(db, customer_id=updated_order.customer_id)
                    if order_customer and order_customer.whatsapp_id:
                        customer_lang_for_notification = order_customer.preferred_language
                        await send_order_status_update_notification(
                            recipient_wa_id=order_customer.whatsapp_id,
                            order_id=updated_order.id,
                            new_status=updated_order.status,
                            lang=customer_lang_for_notification
                        )
                        await send_whatsapp_message(sender_wa_id, get_localized_string(DEFAULT_LANGUAGE, "order_update_admin_success_customer_notified", order_id=order_id_to_update, status=new_status_for_order, whatsapp_id=order_customer.whatsapp_id))
                    else:
                        await send_whatsapp_message(sender_wa_id, get_localized_string(DEFAULT_LANGUAGE, "order_update_admin_success_customer_not_found", order_id=order_id_to_update))
                else:
                    await send_whatsapp_message(sender_wa_id, get_localized_string(DEFAULT_LANGUAGE, "order_update_admin_order_not_found", order_id=order_id_to_update))
        except ValueError:
            await send_whatsapp_message(sender_wa_id, get_localized_string(DEFAULT_LANGUAGE, "order_update_admin_value_error"))
        except Exception as e:
            logger.error(f"Error processing /admin_update_order: {e}")
            await send_whatsapp_message(sender_wa_id, get_localized_string(DEFAULT_LANGUAGE, "order_update_admin_unknown_error"))
    else:
        await send_whatsapp_message(sender_wa_id, get_localized_string(DEFAULT_LANGUAGE, "order_update_admin_value_error")) # Re-use value error for incorrect parts length
                                elif message_text in ["/points", "/solde_points", "mes points"]:
                                    points = customer.loyalty_points # Already fetched customer object
                                    if points > 0:
                                        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "points_balance_message", points=points))
                                    else:
                                        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "no_points_yet"))
                                else:
                                    await send_whatsapp_message(sender_wa_id, default_response_text) # Use the default fallback

# --- Main Helper Functions for Commands/Messages ---
async def send_main_menu(recipient_wa_id: str, lang: str):
    primary_buttons = [
        {"id": "menu_new_arrivals", "title": get_localized_string(lang, "menu_button_new_arrivals")[:20]},
        {"id": "menu_categories", "title": get_localized_string(lang, "menu_button_categories")[:20]},
        {"id": "menu_popular", "title": get_localized_string(lang, "menu_button_popular")[:20]},
    ]
    await send_interactive_message(recipient_id=recipient_wa_id, body_text=get_localized_string(lang, "menu_main_header_1"), buttons=primary_buttons)
    secondary_buttons = [
        {"id": "menu_last_order", "title": get_localized_string(lang, "menu_button_last_order")[:20]},
        {"id": "menu_smart_search_prompt", "title": get_localized_string(lang, "menu_button_smart_search_prompt")[:20]},
        {"id": "menu_help", "title": get_localized_string(lang, "menu_button_help")[:20]}
    ]
    await send_interactive_message(recipient_id=recipient_wa_id, body_text=get_localized_string(lang, "menu_main_header_2"), buttons=secondary_buttons)

async def send_category_menu(db: Session, recipient_wa_id: str, lang: str):
    categories = crud.get_distinct_categories(db)
    if not categories:
        await send_whatsapp_message(recipient_wa_id, get_localized_string(lang, "menu_category_none_available"))
        return
    chunk_size = 3
    for i in range(0, len(categories), chunk_size):
        chunk = categories[i:i + chunk_size]
        buttons_for_chunk = [{"id": f"category_{cat.lower().replace(' ', '_')[:15]}", "title": cat[:20]} for cat in chunk]
        body_text_key = "menu_category_header" if i == 0 else "menu_category_header_more"
        await send_interactive_message(recipient_id=recipient_wa_id, body_text=get_localized_string(lang, body_text_key), buttons=buttons_for_chunk)
        if i + chunk_size >= len(categories):
             await send_whatsapp_message(recipient_wa_id, get_localized_string(lang, "menu_category_back_to_main"))

async def handle_products_command(db: Session, recipient_wa_id: str, offset: int, limit: int, lang: str, search_criteria: Optional[dict] = None, customer_id: Optional[int] = None, exclude_shoe_ids: Optional[List[int]] = None):
    logger.info(f"Handling products display for {recipient_wa_id} (lang: {lang}, customer_id: {customer_id}), offset={offset}, limit={limit}, criteria={search_criteria}, exclude_ids={exclude_shoe_ids}")
    if search_criteria:
        shoes = crud.search_shoes_by_criteria(db, criteria=search_criteria, skip=offset, limit=limit, exclude_ids=exclude_shoe_ids)
        total_shoes_count = len(shoes)
        is_nlp_search = True
        if not shoes:
            await send_whatsapp_message(recipient_wa_id, get_localized_string(lang, "product_search_no_results_nlp"))
            return
        product_message_body = get_localized_string(lang, "product_list_header_nlp") + "\n"
        if customer_id and shoes:
            try:
                crud.update_last_viewed_products(db, customer_id=customer_id, product_id=shoes[0].id)
                logger.info(f"Updated last viewed products for customer {customer_id} with shoe {shoes[0].id}")
            except Exception as e:
                logger.error(f"Error updating last_viewed_products for customer {customer_id}: {e}")
    else:
        shoes = crud.get_shoes(db, skip=offset, limit=limit)
        total_shoes_count = db.query(database.Shoe).count()
        is_nlp_search = False
        if not shoes:
            await send_whatsapp_message(recipient_wa_id, get_localized_string(lang, "product_general_browsing_no_more"))
            return
        product_message_body = get_localized_string(lang, "product_list_header_general") + "\n"

    for shoe in shoes:
        product_message_body += f"\n👟 *{shoe.name}* ({shoe.brand})\n"
        product_message_body += get_localized_string(lang, "product_details_line_1", price=f"{shoe.price:.0f}", color=shoe.color) + "\n"
        product_message_body += get_localized_string(lang, "product_details_line_2", sizes=shoe.size_available, stock=shoe.quantity_available) + "\n"

    interactive_buttons = []
    if is_nlp_search and shoes and len(interactive_buttons) < 1:
         add_to_cart_title = get_localized_string(lang, "add_to_cart_button_nlp_prefix", item_name=shoes[0].name[:10])
         interactive_buttons.append({"id": f"add_cart_{shoes[0].id}", "title": add_to_cart_title[:20]})

    if not is_nlp_search:
        current_page_end_index = offset + len(shoes)
        if current_page_end_index < total_shoes_count:
            interactive_buttons.append({"id": f"view_more_offset_{current_page_end_index}_limit_{limit}", "title": get_localized_string(lang, "view_more_button_title")[:20]})
        if offset > 0:
            prev_offset = max(0, offset - limit)
            interactive_buttons.append({"id": f"prev_page_offset_{prev_offset}_limit_{limit}", "title": get_localized_string(lang, "previous_page_button_title")[:20]})

    if is_nlp_search and not any(btn["id"].startswith("add_cart_") for btn in interactive_buttons) and shoes:
        product_message_body += "\n\n" + get_localized_string(lang, "product_list_add_to_cart_instruction_nlp")
    elif not is_nlp_search and shoes:
        product_message_body += "\n\n" + get_localized_string(lang, "product_list_add_to_cart_instruction_general")

    if interactive_buttons:
        await send_interactive_message(recipient_id=recipient_wa_id, body_text=product_message_body.strip(), buttons=interactive_buttons)
    else:
        final_message = product_message_body.strip()
        if is_nlp_search: final_message += "\n\n" + get_localized_string(lang, "product_list_end_nlp")
        elif not shoes: final_message = get_localized_string(lang, "product_search_no_results_nlp")
        else: final_message += "\n\n" + get_localized_string(lang, "product_list_end_general")
        await send_whatsapp_message(recipient_wa_id, final_message)

async def handle_repeat_order_command(db: Session, sender_wa_id: str, customer: database.Customer, lang: str):
    last_order = crud.get_last_completed_order_for_customer(db, customer_id=customer.id)
    if not last_order or not last_order.items:
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "repeat_order_unavailable"))
        return
    original_order_items_data = [{"shoe_id": item.shoe_id, "quantity": item.quantity, "original_price": item.price_at_purchase,
         "original_name": item.shoe.name if item.shoe else get_localized_string(lang, "unknown_product_name_fallback", default_lang='en'),
         "original_brand": item.shoe.brand if item.shoe else get_localized_string(lang, "unknown_brand_name_fallback", default_lang='en')}
        for item in last_order.items if item.shoe]
    if not original_order_items_data:
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "repeat_order_no_valid_items"))
        return
    verified_items, issue_items, new_total_for_verified = crud.check_items_availability_and_price(db, original_order_items_data)
    response_msg_parts = [get_localized_string(lang, "repeat_order_status_header")]
    if verified_items:
        response_msg_parts.append(get_localized_string(lang, "repeat_order_available_items_header"))
        for v_item in verified_items:
            price_info = get_localized_string(lang, "repeat_order_price_current", price=f"{v_item['current_price']:.0f}")
            if abs(v_item['price_change_percent']) > 1:
                price_info += get_localized_string(lang, "repeat_order_price_change_info", old_price=f"{v_item['original_price']:.0f}", change=f"{v_item['price_change_percent']:.0f}")
            response_msg_parts.append(get_localized_string(lang, "repeat_order_item_format", quantity=v_item['quantity'], name=v_item['current_name'], brand=v_item['current_brand'], price_info=price_info))
    if issue_items:
        response_msg_parts.append(get_localized_string(lang, "repeat_order_issue_items_header"))
        for i_item in issue_items:
            reason_key = f"repeat_order_issue_reason_{i_item['reason']}"
            reason_details = i_item.get('details', {})
            formatted_details = {k: str(v) for k, v in reason_details.items()}
            reason_text = get_localized_string(lang, reason_key, **formatted_details)
            if reason_text == reason_key:
                generic_reason_key = f"repeat_order_issue_reason_{i_item['reason'].split('_details')[0]}"
                reason_text = get_localized_string(lang, generic_reason_key, default_lang='en')
                if reason_text == generic_reason_key: reason_text = i_item['reason']
            response_msg_parts.append(get_localized_string(lang, "repeat_order_item_issue_format", quantity=i_item['quantity'], original_name=i_item['original_name'], reason_text=reason_text))
    await send_whatsapp_message(sender_wa_id, "\n".join(response_msg_parts))
    buttons = []
    if verified_items:
        buttons.append({"id": f"confirm_repeat_verified_{last_order.id}", "title": get_localized_string(lang, "repeat_order_button_confirm", total_price=f"{new_total_for_verified:.0f}")[:20]})
    buttons.append({"id": "cancel_repeat", "title": get_localized_string(lang, "repeat_order_button_cancel")[:20]})
    if not verified_items:
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "repeat_order_no_items_to_reorder"))
    else:
        await send_interactive_message(recipient_id=sender_wa_id, body_text=get_localized_string(lang, "repeat_order_prompt_confirm"), buttons=buttons)

async def handle_confirm_repeat_order(db: Session, sender_wa_id: str, customer: database.Customer, original_order_id: int, lang: str):
    last_order_to_repeat = crud.get_last_completed_order_for_customer(db, customer_id=customer.id)
    if not last_order_to_repeat or last_order_to_repeat.id != original_order_id:
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "repeat_order_error_original_not_found"))
        return
    original_order_items_data = [{"shoe_id": item.shoe_id, "quantity": item.quantity, "original_price": item.price_at_purchase,
         "original_name": item.shoe.name if item.shoe else get_localized_string(lang, "unknown_product_name_fallback", default_lang='en'),
         "original_brand": item.shoe.brand if item.shoe else get_localized_string(lang, "unknown_brand_name_fallback", default_lang='en')}
        for item in last_order_to_repeat.items if item.shoe]
    verified_items, _, _ = crud.check_items_availability_and_price(db, original_order_items_data)
    if not verified_items:
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "repeat_order_error_none_available_on_confirm"))
        return
    delivery_address = last_order_to_repeat.delivery_address or get_localized_string(lang, "delivery_address_to_be_confirmed")
    payment_method = last_order_to_repeat.payment_method or get_localized_string(lang, "payment_method_to_be_confirmed")
    items_for_new_order = []
    for v_item in verified_items:
        shoe_orm = crud.get_shoe(db, v_item['shoe_id'])
        if shoe_orm: items_for_new_order.append(database.CartItem(shoe_id=v_item['shoe_id'], quantity=v_item['quantity'], shoe=shoe_orm))
    if not items_for_new_order:
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "repeat_order_error_prepare_items"))
        return
    try:
        order_payload = order_schema.OrderCreate(customer_id=customer.id, delivery_address=delivery_address, payment_method=payment_method)
        new_order = crud.create_order(db, customer_id=customer.id, order_data=order_payload, cart_items=items_for_new_order)
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "repeat_order_success_confirmation", new_order_id=new_order.id, original_order_id=original_order_id, total_amount=f"{new_order.total_amount:.0f}"))
    except ValueError as e:
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "repeat_order_error_value", error=str(e)))
    except Exception as e:
        logger.error(f"Error creating repeat order for original order {original_order_id}: {e}")
        await send_whatsapp_message(sender_wa_id, get_localized_string(lang, "repeat_order_error_unknown"))

# Note: `utils.whatsapp_utils.send_order_status_update_notification` also needs `lang` param and localization.
# This will be handled in a separate step if not already done.
# For now, assuming it's either handled or admin messages are default lang.
# The /admin_update_order already passes customer_lang to it.
