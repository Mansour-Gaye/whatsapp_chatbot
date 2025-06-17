import httpx
import json
import logging

# Config.py is in the parent directory
from .. import config

# Configure logger for this module
logger = logging.getLogger(__name__)
logging.basicConfig(level=config.LOGGING_LEVEL) # Basic config, can be more sophisticated

async def send_whatsapp_message(recipient_id: str, message_text: str) -> bool:
    """
    Sends a text message to a WhatsApp recipient using the Graph API.

    Args:
        recipient_id: The WhatsApp ID of the recipient.
        message_text: The text message to send.

    Returns:
        True if the message was sent successfully (or simulated successfully), False otherwise.
    """
    if not all([config.WHATSAPP_ACCESS_TOKEN, config.WHATSAPP_PHONE_NUMBER_ID, config.WHATSAPP_API_VERSION]):
        logger.error("WhatsApp API credentials (token, phone ID, version) are not fully configured.")
        if config.WHATSAPP_ACCESS_TOKEN == "your_whatsapp_access_token" or \
           config.WHATSAPP_PHONE_NUMBER_ID == "your_phone_number_id":
            logger.warning("Using placeholder tokens/IDs. Actual sending will fail or is disabled.")
            # For this subtask, we might simulate success if placeholders are used.
            # However, it's better to clearly indicate failure or no-op.
            # Let's assume for now if tokens are placeholders, we don't try to send.
            return False

    api_url = f"{config.WHATSAPP_GRAPH_API_URL}/{config.WHATSAPP_API_VERSION}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "text",
        "text": {"body": message_text},
    }

    logger.info(f"Attempting to send message to {recipient_id} via {api_url}")
    logger.debug(f"Payload: {json.dumps(payload, indent=2)}")
    logger.debug(f"Headers: {headers}")

    # --- Mocking/Actual Send Control ---
    # For this subtask, if external calls are restricted or tokens are placeholders,
    # we might not want to make a real HTTP call.
    # A more robust solution would use a proper mocking library for tests.
    # Here, we can add a simple flag or check placeholder tokens.

    if "your_whatsapp_access_token" in config.WHATSAPP_ACCESS_TOKEN or \
       "your_phone_number_id" in config.WHATSAPP_PHONE_NUMBER_ID:
        logger.warning(f"SIMULATED SEND: Message to {recipient_id}: '{message_text}' (using placeholder tokens).")
        # To simulate a successful API call without actually sending:
        # print(f"--- SIMULATED WHATSAPP SEND ---")
        # print(f"To: {recipient_id}")
        # print(f"Message: {message_text}")
        # print(f"URL: {api_url}")
        # print(f"Payload: {json.dumps(payload, indent=2)}")
        # print(f"--- END SIMULATED SEND ---")
        return True # Simulate success for now if using placeholders

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, headers=headers, json=payload)

        logger.info(f"Response Status Code: {response.status_code}")
        logger.debug(f"Response Content: {response.text}")

        if response.status_code >= 200 and response.status_code < 300:
            logger.info(f"Message sent successfully to {recipient_id}.")
            return True
        else:
            logger.error(f"Failed to send message. Status: {response.status_code}, Response: {response.text}")
            # You might want to parse the error response for more details
            # e.g., response.json().get("error", {}).get("message")
            return False
    except httpx.RequestError as e:
        logger.error(f"HTTPX RequestError while sending message: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred in send_whatsapp_message: {e}")
        return False

if __name__ == "__main__":
    # Example usage (requires asyncio to run if called directly)
    import asyncio
    async def main_test():
        print("Testing send_whatsapp_message utility...")
        # Replace with a test WhatsApp ID if you have one and valid tokens
        test_recipient_id = "1234567890" # Placeholder

        # Test with placeholder tokens (should simulate)
        print("\n--- Test Case 1: Placeholder Tokens (Simulated Send) ---")
        # Temporarily ensure placeholder values for this test if not already set
        original_token = config.WHATSAPP_ACCESS_TOKEN
        original_phone_id = config.WHATSAPP_PHONE_NUMBER_ID
        config.WHATSAPP_ACCESS_TOKEN = "your_whatsapp_access_token_test"
        config.WHATSAPP_PHONE_NUMBER_ID = "your_phone_number_id_test"

        success_simulated = await send_whatsapp_message(test_recipient_id, "Hello from the API! (Simulated)")
        print(f"Simulated send successful: {success_simulated}")

        config.WHATSAPP_ACCESS_TOKEN = original_token
        config.WHATSAPP_PHONE_NUMBER_ID = original_phone_id

        # To test actual sending, you would need valid tokens and a recipient ID.
        # Ensure your config.py has actual values or .env loads them.
        # print("\n--- Test Case 2: Actual Tokens (Real Send - CAUTION!) ---")
        # if config.WHATSAPP_ACCESS_TOKEN != "your_whatsapp_access_token" and \
        #    config.WHATSAPP_PHONE_NUMBER_ID != "your_phone_number_id":
        #    print("Attempting real send. Ensure recipient ID is valid and testable.")
        #    # success_real = await send_whatsapp_message("REPLACE_WITH_REAL_RECIPIENT_WA_ID", "Test message from API.")
        #    # print(f"Real send successful: {success_real}")
        # else:
        #    print("Skipping real send test as tokens are placeholders.")

    if config.LOGGING_LEVEL == "DEBUG": # Only run test if logging is verbose
        asyncio.run(main_test())

async def send_interactive_message(
    recipient_id: str,
    body_text: str,
    buttons: list[dict], # Each dict: {"id": "unique_id", "title": "Button Title"}
    header_text: str = None, # Optional header
    footer_text: str = None  # Optional footer
) -> bool:
    """
    Sends an interactive message with buttons to a WhatsApp recipient using the Graph API.

    Args:
        recipient_id: The WhatsApp ID of the recipient.
        body_text: The main text of the message.
        buttons: A list of button dictionaries. Max 3 buttons.
                 Each button: {"id": "unique_button_id", "title": "Button Title"}
        header_text: Optional text for the header of the interactive message.
        footer_text: Optional text for the footer of the interactive message.


    Returns:
        True if the message was sent successfully (or simulated successfully), False otherwise.
    """
    if not all([config.WHATSAPP_ACCESS_TOKEN, config.WHATSAPP_PHONE_NUMBER_ID, config.WHATSAPP_API_VERSION]):
        logger.error("WhatsApp API credentials (token, phone ID, version) are not fully configured for interactive message.")
        if config.WHATSAPP_ACCESS_TOKEN == "your_whatsapp_access_token" or \
           config.WHATSAPP_PHONE_NUMBER_ID == "your_phone_number_id":
            logger.warning("Using placeholder tokens/IDs for interactive message. Actual sending will fail or is disabled.")
            return False

    api_url = f"{config.WHATSAPP_GRAPH_API_URL}/{config.WHATSAPP_API_VERSION}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    # Construct action.buttons for the payload
    action_buttons = []
    if len(buttons) > 3:
        logger.warning("Maximum of 3 buttons allowed for interactive messages. Truncating.")
        buttons = buttons[:3]

    for btn in buttons:
        action_buttons.append({
            "type": "reply",
            "reply": {
                "id": btn["id"],
                "title": btn["title"]
            }
        })

    interactive_payload = {
        "type": "button",
        "body": {"text": body_text},
        "action": {"buttons": action_buttons}
    }

    if header_text:
        interactive_payload["header"] = {
            "type": "text",
            "text": header_text
        }
    if footer_text:
        interactive_payload["footer"] = {
            "text": footer_text
        }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual", # Can be parameterized if group messaging is ever needed
        "to": recipient_id,
        "type": "interactive",
        "interactive": interactive_payload,
    }

    logger.info(f"Attempting to send interactive message to {recipient_id} via {api_url}")
    logger.debug(f"Interactive Payload: {json.dumps(payload, indent=2)}")
    logger.debug(f"Headers: {headers}")

    if "your_whatsapp_access_token" in config.WHATSAPP_ACCESS_TOKEN or \
       "your_phone_number_id" in config.WHATSAPP_PHONE_NUMBER_ID:
        logger.warning(f"SIMULATED INTERACTIVE SEND: Message to {recipient_id}: Body='{body_text}', Buttons='{[b['title'] for b in buttons]}' (using placeholder tokens).")
        return True # Simulate success for now if using placeholders

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, headers=headers, json=payload)

        logger.info(f"Interactive Response Status Code: {response.status_code}")
        logger.debug(f"Interactive Response Content: {response.text}")

        if response.status_code >= 200 and response.status_code < 300:
            logger.info(f"Interactive message sent successfully to {recipient_id}.")
            return True
        else:
            logger.error(f"Failed to send interactive message. Status: {response.status_code}, Response: {response.text}")
            return False
    except httpx.RequestError as e:
        logger.error(f"HTTPX RequestError while sending interactive message: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred in send_interactive_message: {e}")
        return False

async def send_order_status_update_notification(
    recipient_wa_id: str,
    order_id: int,
    new_status: str,
    lang: str, # Added lang parameter
    order_details: Optional[Any] = None
) -> bool:
    """
    Sends a localized order status update notification to the customer.
    """
    # Key for the main subject/title part of the message
    subject_key = "order_status_notification_subject"
    subject_text = get_localized_string(lang, subject_key, order_id=order_id)

    # Key for the specific status message
    status_message_key = f"order_status_{new_status}"
    message_text = get_localized_string(lang, status_message_key, order_id=order_id, status=new_status) # status for unknown

    # If the specific key for a status (e.g. order_status_shipped) is not found,
    # get_localized_string will fall back to default lang, then to the key itself.
    # If the key itself is returned, it means we don't have a specific translation for that status.
    # In such a case, we use the "order_status_unknown" as a template.
    if message_text == status_message_key: # Key was not found in translations
        logger.warning(f"Specific status key '{status_message_key}' not found for lang '{lang}'. Using generic status update.")
        message_text = get_localized_string(lang, "order_status_unknown", order_id=order_id, status=new_status)

    full_message = f"{subject_text}\n\n{message_text}"

    logger.info(f"Sending order status update for order {order_id} (status: {new_status}, lang: {lang}) to {recipient_wa_id}: {full_message}")
    return await send_whatsapp_message(recipient_wa_id, full_message)
