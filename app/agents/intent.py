from __future__ import annotations

import json
import re
from typing import Optional

from app.integrations.llm import parse_intent_llm
from app.models.domain import UserIntent


def normalize_cuisine_typos(text: str) -> str:
    """Fix common misspellings before cuisine keyword matching."""
    low = text.lower()
    for wrong, right in (
        ("meditarrean", "mediterranean"),
        ("mediteranean", "mediterranean"),
        ("mediterranian", "mediterranean"),
        ("mediterrean", "mediterranean"),
        ("mediterrnean", "mediterranean"),
    ):
        low = low.replace(wrong, right)
    return low


_CUISINES = [
    ("italian", "Italian"),
    ("sushi", "Japanese"),
    ("japanese", "Japanese"),
    ("mexican", "Mexican"),
    ("indian", "Indian"),
    ("thai", "Thai"),
    ("chinese", "Chinese"),
    ("vietnamese", "Vietnamese"),
    ("korean", "Korean"),
    ("pizza", "Italian"),
    ("burger", "American"),
    ("american", "American"),
    ("seafood", "Seafood"),
    ("vegetarian", "Vegetarian"),
    ("vegan", "Vegan"),
    ("mediterranean", "Mediterranean"),
    ("french", "French"),
]


def detect_cuisine_from_message(message: str) -> Optional[str]:
    """Return canonical cuisine label if the message names a cuisine (after typo normalization)."""
    low = normalize_cuisine_typos(message.lower()).replace("sea food", "seafood").replace("sea-food", "seafood")
    for key, label in _CUISINES:
        if key in low:
            return label
    return None


def apply_message_cuisine(intent: UserIntent, message: str) -> UserIntent:
    """Message-named cuisine wins (fixes LLM omissions and typos like 'meditarrean')."""
    detected = detect_cuisine_from_message(message)
    if detected:
        intent.cuisine = detected
    return intent


def user_message_signals_spicy_food(message: str) -> bool:
    """True when the user is asking for spicy / heat-forward food (not 'not spicy')."""
    low = normalize_cuisine_typos(message.lower())
    if re.search(r"\b(not\s+spicy|non-?spicy|no\s+spice|mild\s+only)\b", low):
        return False
    if re.search(
        r"\b(spicy\s+food|spicy\s+dishes?|something\s+spicy|eat\s+spicy|love\s+spice|extra\s+spicy|very\s+spicy)\b",
        low,
    ):
        return True
    if "spicy" in low and re.search(
        r"\b(want|wanna|need|crave|eat|get|try|prefer|feeling|i\s+want)\b",
        low,
    ):
        return True
    return False


def apply_message_mood(intent: UserIntent, message: str) -> UserIntent:
    """Infer mood from the latest message when the user names a vibe (romantic, quiet, lively)."""
    low = normalize_cuisine_typos(message.lower())
    if re.search(
        r"\b(romantic\s+dinner|romantic\s+meal|romantic\s+night|romantic\s+date|date\s+night|"
        r"anniversary|valentine|candlelit|candle\s+lit|special\s+night)\b",
        low,
    ):
        intent.mood = "romantic"
    elif re.search(r"\b(quiet\s+dinner|intimate\s+dinner|low\s*key\s+dinner)\b", low):
        intent.mood = "quiet"
    elif re.search(r"\b(loud\s+spot|party\s+vibe|energetic|lively\s+atmosphere)\b", low):
        intent.mood = "loud"
    elif re.search(r"\b(casual\s+dinner|casual\s+spot)\b", low):
        intent.mood = "casual"
    return intent


def apply_message_flavor_preferences(intent: UserIntent, message: str) -> UserIntent:
    """
    Map plain-language flavor asks (spicy, sour, sweet, juicy, …) into dish_preferences
    and spice_tolerance so search, rank, and copy can respond.
    """
    low = normalize_cuisine_typos(message.lower())
    dp = [str(x) for x in intent.dish_preferences]
    dpl = {x.lower() for x in dp}

    if user_message_signals_spicy_food(message):
        if "spicy" not in dpl:
            dp.append("spicy")
            dpl.add("spicy")
        if intent.spice_tolerance == "any":
            if re.search(r"\b(very|extra|super|extremely)\s+spicy\b", low) or "spicy af" in low:
                intent.spice_tolerance = "hot"
            else:
                intent.spice_tolerance = "medium"

    flavor_tokens = (
        ("sour", "sour", ("sour", "tangy", "tart")),
        ("tangy", "tangy", ("tangy", "tamarind", "vinegar")),
        ("sweet", "sweet", ("sweet", "dessert", "coconut", "mango")),
        ("juicy", "juicy", ("juicy", "soup", "broth", "dumpling")),
        ("savory", "savory", ("savory", "umami", "rich")),
        ("umami", "umami", ("umami", "miso", "mushroom")),
    )
    for needle, label, _hints in flavor_tokens:
        if needle in low and label not in dpl:
            dp.append(label)
            dpl.add(label)

    intent.dish_preferences = dp
    return intent


def _heuristic_intent(message: str, profile_json: dict) -> UserIntent:
    low = normalize_cuisine_typos(message).replace("sea food", "seafood").replace("sea-food", "seafood")
    cuisine = None
    for key, label in _CUISINES:
        if key in low:
            cuisine = label
            break

    budget = "any"
    if any(w in low for w in ("cheap", "budget", "under", "$", "affordable")):
        budget = "low"
    elif any(w in low for w in ("fancy", "splurge", "special occasion", "upscale")):
        budget = "high"
    elif "medium" in low or "moderate" in low:
        budget = "medium"

    dietary: list[str] = []
    dietary_style: str = "any"
    if "vegan" in low:
        dietary.append("vegan")
        dietary_style = "vegan"
    elif "vegetarian" in low or "veggie" in low:
        dietary.append("vegetarian")
        dietary_style = "vegetarian"
    if "pescatarian" in low or "pescetarian" in low:
        dietary.append("pescatarian")
        if dietary_style == "any":
            dietary_style = "pescatarian"
    if any(w in low for w in ("non-veg", "non veg", "nonveg", "with meat")):
        dietary_style = "omnivore"
    if "halal" in low:
        dietary.append("halal")
    if "kosher" in low:
        dietary.append("kosher")
    if "gluten" in low or "celiac" in low:
        dietary.append("gluten-free")
    if "dairy-free" in low or "dairy free" in low or "no dairy" in low:
        dietary.append("dairy-free")
    if "egg-free" in low or "no egg" in low or "without egg" in low:
        dietary.append("egg-free")

    health_goals: list[str] = []
    meal_intent: str = "any"
    if any(w in low for w in ("healthy", "clean eating", "nutritious", "not greasy", "not oily")):
        meal_intent = "healthy"
        health_goals.append("nutritious")
    if "high protein" in low or "high-protein" in low or "protein" in low:
        health_goals.append("high_protein")
    if "low carb" in low or "low-carb" in low or "keto" in low:
        health_goals.append("low_carb" if "keto" not in low else "keto_friendly")
    if "low cal" in low or "low-cal" in low or "low calorie" in low:
        health_goals.append("low_calorie")
    if "light meal" in low or "something light" in low or "lighter" in low:
        health_goals.append("light_meal")
    if "low oil" in low or "less oil" in low or "not fried" in low or "avoid fried" in low:
        health_goals.append("low_oil")

    dish_preferences: list[str] = []
    for token, label in (
        ("noodle", "noodles"),
        ("rice", "rice"),
        ("pizza", "pizza"),
        ("pasta", "pasta"),
        ("soup", "soup"),
        ("salad", "salad"),
        ("curry", "curry"),
        ("bowl", "bowl"),
        ("dumpling", "dumplings"),
    ):
        if token in low:
            dish_preferences.append(label)
    if user_message_signals_spicy_food(message) and "spicy" not in [d.lower() for d in dish_preferences]:
        dish_preferences.append("spicy")

    spice_tolerance: str = "any"
    if any(w in low for w in ("mild spice", "not spicy", "no spice", "mild")):
        spice_tolerance = "mild"
    elif any(w in low for w in ("very spicy", "extra spicy", "spicy af")):
        spice_tolerance = "hot"
    elif user_message_signals_spicy_food(message) or "heat" in low:
        spice_tolerance = "medium"

    urgency = "flexible"
    if any(w in low for w in ("now", "right now", "asap", "hungry", "quick lunch", "quick bite")):
        urgency = "now"
    elif any(w in low for w in ("soon", "in an hour", "later today")):
        urgency = "soon"

    if meal_intent == "any" and any(w in low for w in ("quick", "fast", "grab and go", "in a hurry")):
        meal_intent = "quick"
        if urgency == "flexible":
            urgency = "now"
    if any(w in low for w in ("date night", "slow dinner", "leisurely")):
        meal_intent = "relaxed"
    mood = None
    if re.search(
        r"\b(romantic\s+dinner|romantic\s+meal|romantic\s+night|date\s+night|anniversary|candlelit)\b",
        low,
    ):
        mood = "romantic"
        if meal_intent == "any":
            meal_intent = "relaxed"
    elif re.search(r"\b(quiet\s+dinner|intimate)\b", low):
        mood = "quiet"
    elif re.search(r"\b(loud|party\s+vibe|energetic\s+spot)\b", low):
        mood = "loud"
    if any(w in low for w in ("splurge", "indulge", "treat myself", "cheat meal")):
        meal_intent = "indulgent"

    mode = "either"
    if any(w in low for w in ("deliver", "delivery", "uber eats", "doordash")):
        mode = "delivery"
    elif any(w in low for w in ("pickup", "takeout", "take out", "to go", "grab to go")):
        mode = "pickup"
    elif any(w in low for w in ("dine in", "sit down", "restaurant", "date night")):
        mode = "dine_in"

    disliked: list[str] = []
    m = re.findall(r"no\s+([\w\s]+?)(?:\.|,|$)", low)
    for g in m:
        disliked.append(g.strip())

    prof_diet = list(profile_json.get("dietary_restrictions") or [])
    prof_dis = list(profile_json.get("disliked_ingredients") or [])
    if not dietary and prof_diet:
        dietary = prof_diet
    if not disliked and prof_dis:
        disliked = prof_dis

    if dietary_style == "any" and profile_json.get("dietary_style") not in (None, "any"):
        dietary_style = profile_json["dietary_style"]

    return UserIntent(
        cuisine=cuisine,
        mood=mood,
        budget=budget,
        dietary=dietary,
        disliked_ingredients=disliked,
        urgency=urgency,
        mode=mode,
        party_size=None,
        needs_clarification=False,
        clarifying_question=None,
        raw_text=message,
        dietary_style=dietary_style if isinstance(dietary_style, str) else "any",
        health_goals=health_goals,
        meal_intent=meal_intent if meal_intent in ("quick", "relaxed", "indulgent", "healthy", "any") else "any",
        dish_preferences=dish_preferences,
        spice_tolerance=spice_tolerance
        if spice_tolerance in ("mild", "medium", "hot", "any")
        else "any",
    )


async def parse_intent(message: str, profile_hint: str) -> UserIntent:
    try:
        profile_json = json.loads(profile_hint) if profile_hint else {}
    except json.JSONDecodeError:
        profile_json = {}
    llm = await parse_intent_llm(message, profile_hint)
    if llm:
        llm.raw_text = message
        return llm
    return _heuristic_intent(message, profile_json)
