import os
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file if it exists

# WhatsApp Configuration - Replace with your actual values or use environment variables
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "your_very_secret_verify_token")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "your_whatsapp_access_token")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "your_phone_number_id")
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v19.0") # Example, use current
WHATSAPP_GRAPH_API_URL = os.getenv("WHATSAPP_GRAPH_API_URL", "https://graph.facebook.com")

# Optional: Business Account ID if needed for some API calls
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "your_business_account_id")

# Application settings
APP_NAME = "WhatsApp Business API Assistant"
API_V1_STR = "/api/v1" # From main.py, useful for constructing URLs if needed

# Logging configuration (basic example)
LOGGING_LEVEL = "INFO"

# Database URL (already defined in database.py, but can be centralized here if preferred)
# SQLALCHEMY_DATABASE_URL = "sqlite:///./whatsapp_assistant.db"

# You can add other configurations here as your app grows
# For example, rate limiting, external API keys, etc.

# Simple check to see if essential tokens are placeholders (for demonstration)
if WHATSAPP_VERIFY_TOKEN == "your_very_secret_verify_token":
    print("Warning: WHATSAPP_VERIFY_TOKEN is using a placeholder value from config.py.")
if WHATSAPP_ACCESS_TOKEN == "your_whatsapp_access_token":
    print("Warning: WHATSAPP_ACCESS_TOKEN is using a placeholder value from config.py.")
if WHATSAPP_PHONE_NUMBER_ID == "your_phone_number_id":
    print("Warning: WHATSAPP_PHONE_NUMBER_ID is using a placeholder value from config.py.")
