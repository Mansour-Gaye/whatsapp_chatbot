import spacy
from spacy.matcher import Matcher
import re

# Load French spaCy model
try:
    nlp = spacy.load("fr_core_news_sm")
except OSError:
    # This can happen if the model is not downloaded/installed correctly.
    # The previous step should handle the download.
    print("Error: spaCy French model 'fr_core_news_sm' not found.")
    print("Please run: python -m spacy download fr_core_news_sm")
    # Fallback to a blank French model to allow basic tokenization if needed,
    # but matching and NER will be limited.
    nlp = spacy.blank("fr")


# Define keywords and patterns
# These could be expanded or loaded from a configuration file/database
KNOWN_CATEGORIES = {
    "baskets": ["basket", "baskets", "sneaker", "sneakers", "chaussure de sport"],
    "sandales": ["sandale", "sandales", "nu-pied", "nu-pieds"],
    "bottes": ["botte", "bottes", "bottine", "bottines"],
    "mocassins": ["mocassin", "mocassins"],
    "escarpins": ["escarpin", "escarpins", "talon", "talons"],
    "derbies": ["derby", "derbies", "chaussure de ville"],
}
KNOWN_COLORS = {
    "noir": ["noir", "noire", "noirs", "noires", "foncé", "foncée"],
    "blanc": ["blanc", "blanche", "blancs", "blanches", "clair", "claire"],
    "rouge": ["rouge", "rouges"],
    "bleu": ["bleu", "bleue", "bleus", "bleues", "bleu marine"],
    "vert": ["vert", "verte", "verts", "vertes"],
    "marron": ["marron", "marrons", "brun", "brune"],
    "gris": ["gris", "grise"],
    "rose": ["rose", "roses"],
    "jaune": ["jaune", "jaunes"],
    "orange": ["orange"],
    "violet": ["violet", "violette", "violets", "violettes"],
    "beige": ["beige"],
}
KNOWN_BRANDS = { # Top brands, can be expanded
    "nike": ["nike"],
    "adidas": ["adidas", "adidace"], # Common typo
    "puma": ["puma"],
    "new balance": ["new balance", "nb"],
    "converse": ["converse", "converce"],
    "vans": ["vans"],
    "timberland": ["timberland", "timbs"],
    "dr. martens": ["dr. martens", "doc martens", "docs"],
    "geox": ["geox"],
    "clarks": ["clarks"]
}

# Initialize Matcher
matcher = Matcher(nlp.vocab)

# Add patterns for size
# "taille 42", "pointure 38", "en 40", "43" (if surrounded by relevant context or as a fallback)
size_patterns = [
    [{"LOWER": {"IN": ["taille", "pointure"]}}, {"IS_DIGIT": True}],
    [{"LOWER": "en"}, {"IS_DIGIT": True}],
    # A single number could be a size, but needs careful handling to avoid false positives.
    # Example: "je cherche des baskets taille 42" - doc[4].text == "42"
    # For now, being more explicit. Can add more complex logic later.
    # [{"IS_DIGIT": True, "LENGTH": 2}] # Matches any two-digit number
]
matcher.add("SHOE_SIZE", size_patterns)

# Add patterns for colors (more contextual than just keywords)
# "couleur rouge", "en bleu", "basket noire"
color_patterns = [
    [{"LOWER": "couleur"}, {"LOWER": {"IN": [color for sublist in KNOWN_COLORS.values() for color in sublist]}}],
    [{"LOWER": "en"}, {"LOWER": {"IN": [color for sublist in KNOWN_COLORS.values() for color in sublist]}}],
]
# Add individual color keywords as lower priority patterns if needed, or rely on keyword check
matcher.add("SHOE_COLOR_CTX", color_patterns)


def find_keyword_match(text_lower, keywords_dict):
    """Helper to find the first matching keyword key from a dictionary of keyword lists."""
    for key, terms in keywords_dict.items():
        for term in terms:
            if term in text_lower: # Simple substring check
                return key
    return None

def extract_shoe_entities(text: str) -> dict:
    if not text:
        return {}

    doc = nlp(text)
    text_lower = text.lower() # For keyword matching
    entities = {}

    # 1. Use spaCy Matcher for contextual patterns (size, color context)
    matches = matcher(doc)
    for match_id, start, end in matches:
        span = doc[start:end]
        label = nlp.vocab.strings[match_id]

        if label == "SHOE_SIZE" and "size" not in entities:
            # Extract the number from the matched span
            for token in span:
                if token.is_digit:
                    entities["size"] = token.text
                    break
        elif label == "SHOE_COLOR_CTX" and "color" not in entities:
            # Extract the color term from the span
            # The pattern ensures the last token is likely the color
            color_term = span[-1].text.lower()
            # Normalize to the known color key
            for color_key, color_list in KNOWN_COLORS.items():
                if color_term in color_list:
                    entities["color"] = color_key
                    break

    # 2. Keyword-based extraction for categories, brands, and colors (if not found by matcher)
    if "category" not in entities:
        category = find_keyword_match(text_lower, KNOWN_CATEGORIES)
        if category:
            entities["category"] = category

    if "color" not in entities: # If Matcher didn't find a contextual color
        color = find_keyword_match(text_lower, KNOWN_COLORS)
        if color:
            entities["color"] = color

    if "brand" not in entities:
        brand = find_keyword_match(text_lower, KNOWN_BRANDS)
        if brand:
            entities["brand"] = brand

    # 3. Fallback for size: look for standalone two-digit numbers if no size entity found yet
    if "size" not in entities:
        # Regex for standalone 2-digit numbers (common shoe sizes)
        # This is a bit broad, might need refinement or context checks
        size_match = re.search(r"\b(3[5-9]|4[0-7])\b", text) # Common European shoe sizes 35-47
        if size_match:
            entities["size"] = size_match.group(1)

    # Lemmatization can be helpful for categories/colors but adds complexity.
    # Example: "chaussures sportives" -> category "baskets"
    # For now, direct keyword matching on lowercased text and some patterns.

    return entities

if __name__ == "__main__":
    # Test cases
    test_phrases = [
        "Je cherche des baskets Nike taille 42 de couleur noire.",
        "As-tu des sandales rouges en pointure 38?",
        "Je veux des bottes marron.",
        "Des sneakers Adidas blanches.",
        "Chaussure de sport bleue taille 40.",
        "Mocassins en cuir taille 43.",
        "Je voudrais des New Balance grises.",
        "Une chaussure de ville.",
        "montre moi les baskets puma en 45",
        "des talons aiguilles violets",
        "des chaussures nike air max blanches taille 41",
        "je cherche des adidas taille 44 couleur vert"
    ]

    for phrase in test_phrases:
        extracted = extract_shoe_entities(phrase)
        print(f"Phrase: '{phrase}'")
        print(f"Extracted Entities: {extracted}\n")

    # Test a phrase where size is just a number
    print(f"Phrase: 'Baskets Nike 43'")
    print(f"Extracted Entities: {extract_shoe_entities('Baskets Nike 43')}\n")

    print(f"Phrase: 'Des chaussures en 39'")
    print(f"Extracted Entities: {extract_shoe_entities('Des chaussures en 39')}\n")

    print(f"Phrase: 'sandale jaune'")
    print(f"Extracted Entities: {extract_shoe_entities('sandale jaune')}\n")
