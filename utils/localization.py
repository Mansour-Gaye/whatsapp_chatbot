import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

translations: Dict[str, Dict[str, str]] = {}
DEFAULT_LANGUAGE = 'fr' # Fallback language

def load_translations(locales_dir: str = "locales"):
    """
    Loads all *.json translation files from the specified directory.
    Each file should be named with the language code (e.g., fr.json, en.json).
    """
    global translations
    if translations: # Avoid reloading if already loaded, useful for some app structures
        # logger.debug("Translations already loaded.")
        # return

    current_script_path = os.path.dirname(os.path.abspath(__file__))
    # Go up one level from utils to the project root where locales/ should be
    project_root = os.path.dirname(current_script_path)
    actual_locales_dir = os.path.join(project_root, locales_dir)

    logger.info(f"Attempting to load translations from: {actual_locales_dir}")

    if not os.path.isdir(actual_locales_dir):
        logger.error(f"Locales directory not found: {actual_locales_dir}. Ensure it exists at the project root.")
        return

    for filename in os.listdir(actual_locales_dir):
        if filename.endswith(".json"):
            lang_code = filename.split(".")[0]
            filepath = os.path.join(actual_locales_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    translations[lang_code] = json.load(f)
                logger.info(f"Successfully loaded translations for language: {lang_code} from {filename}")
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from {filepath}: {e}")
            except Exception as e:
                logger.error(f"Error loading translation file {filepath}: {e}")

    if not translations:
        logger.warning("No translations were loaded. Localization will not function correctly.")
    # else:
        # logger.debug(f"Loaded languages: {list(translations.keys())}")


def get_localized_string(lang: str, key: str, **kwargs: Any) -> str:
    """
    Fetches a localized string for the given language and key.
    Falls back to DEFAULT_LANGUAGE if the key is not found in the specified language.
    If the key is not found in DEFAULT_LANGUAGE either, returns the key itself.
    Formats the string with **kwargs if provided.
    """
    if not lang: # Safety net if lang is None or empty
        lang = DEFAULT_LANGUAGE

    # Ensure translations are loaded if they are empty (e.g., on first call or if app reloads)
    # This is a simple way to ensure loading without explicit app startup hooks in this context.
    if not translations:
        logger.warning("Translations not loaded. Attempting to load now for get_localized_string.")
        load_translations() # Attempt to load if not already

    lang_dict = translations.get(lang)

    message = None
    if lang_dict and key in lang_dict:
        message = lang_dict[key]
    else:
        # Fallback to default language
        logger.warning(f"Key '{key}' not found for language '{lang}'. Falling back to default '{DEFAULT_LANGUAGE}'.")
        default_lang_dict = translations.get(DEFAULT_LANGUAGE)
        if default_lang_dict and key in default_lang_dict:
            message = default_lang_dict[key]
        else:
            logger.error(f"Key '{key}' not found in default language '{DEFAULT_LANGUAGE}' either. Returning key itself.")
            message = key # Return the key itself as a last resort

    if kwargs:
        try:
            return message.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing keyword argument for formatting string with key '{key}' (lang: {lang}): {e}")
            return message # Return unformatted message on error
        except Exception as e:
            logger.error(f"Error formatting string with key '{key}' (lang: {lang}): {e}")
            return message

    return message

# Load translations when this module is imported or app starts.
# For a FastAPI app, this might be better placed in main.py on startup.
# For this script-based environment, loading here is okay.
load_translations()

if __name__ == "__main__":
    # Test the localization utility
    print("--- Testing Localization Utility ---")

    # Ensure translations are loaded for test
    if not translations:
        print("CRITICAL: Translations did not load for test. Check paths and files.")
    else:
        print(f"Loaded languages: {list(translations.keys())}")

        print("\n--- French Tests ---")
        print(f"greeting_new_customer (fr, name=Jean): {get_localized_string('fr', 'greeting_new_customer', name='Jean')}")
        print(f"menu_button_categories (fr): {get_localized_string('fr', 'menu_button_categories')}")
        print(f"non_existent_key (fr): {get_localized_string('fr', 'non_existent_key_test')}")

        print("\n--- English Tests ---")
        print(f"greeting_new_customer (en, name=John): {get_localized_string('en', 'greeting_new_customer', name='John')}")
        print(f"menu_button_categories (en): {get_localized_string('en', 'menu_button_categories')}")
        print(f"non_existent_key (en, fallback to fr): {get_localized_string('en', 'product_list_header_general')}") # Key exists in fr
        print(f"non_existent_key_anywhere (en): {get_localized_string('en', 'really_non_existent_key_test')}")


        print("\n--- Fallback Tests ---")
        # Assuming 'es' (Spanish) is not loaded, should fallback to 'fr' then to key
        print(f"greeting_new_customer (es, name=Juan, fallback to fr): {get_localized_string('es', 'greeting_new_customer', name='Juan')}")
        print(f"non_existent_key (es, fallback to key): {get_localized_string('es', 'non_existent_key_test_es')}")

        print("\n--- Formatting Test ---")
        print(f"repeat_order_price_current (fr, price=15000): {get_localized_string('fr', 'repeat_order_price_current', price=15000)}")
        # Test missing kwarg
        print(f"repeat_order_price_current (fr, no price): {get_localized_string('fr', 'repeat_order_price_current')}")

        print("\n--- Test Loading with custom path (conceptual) ---")
        # To test this properly, you'd need to create a dummy locales_test dir
        # translations.clear() # Clear existing
        # load_translations(locales_dir="locales_test")
        # print(f"Loaded after custom path attempt: {list(translations.keys())}")
        # translations.clear() # Clear again
        # load_translations() # Reload default for other potential tests
        print("Conceptual test for custom path loading noted.")
