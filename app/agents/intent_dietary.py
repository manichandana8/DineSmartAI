"""Merge dietary_style into dietary[] for ranking penalties and search consistency."""

from __future__ import annotations

import re

from app.models.domain import UserIntent

# User must mention diet/health (or "as usual") this turn to keep saved vegan/keto defaults.
_EXPLICIT_DIET_OR_HEALTH_IN_MESSAGE = re.compile(
    r"\b("
    r"vegan|vegetarian|plant[- ]based|pescatarian|omnivore|non[- ]?veg|carnivore|"
    r"halal|kosher|gluten[- ]free|dairy[- ]free|egg[- ]free|nut[- ]free|lactose|"
    r"allerg(y|ic)|shellfish|peanut|tree\s*nut|"
    r"keto|low[- ]?carb|low[- ]?cal|high[- ]protein|paleo|whole\s*30|"
    r"healthy\s+eat|watching\s+(carbs|calories)|"
    r"as\s+usual|my\s+usual|same\s+(diet|restrictions)|use\s+my\s+saved|"
    r"remember\s+i'?m\s+(vegan|vegetarian|halal|kosher)"
    r")\b",
    re.I,
)


def relax_saved_diet_if_not_explicit_in_message(message: str, intent: UserIntent) -> UserIntent:
    """
    Saved profile (and over-eager LLM) can force vegan/keto on every turn. If the user did not
    explicitly state diet or health constraints in this message, search and rank as open scope
    (dietary_style any, no profile health_goals bleed). Allergies still belong in explicit wording.
    """
    msg = (message or "").strip()
    if not msg or _EXPLICIT_DIET_OR_HEALTH_IN_MESSAGE.search(msg):
        return intent
    intent.dietary_style = "any"
    drop = {"vegan", "vegetarian", "veg"}
    intent.dietary = [t for t in intent.dietary if str(t).strip().lower() not in drop]
    intent.health_goals = []
    if intent.meal_intent == "healthy":
        intent.meal_intent = "any"
    intent.ephemeral_diet_override = True
    return intent


def sync_dietary_style_into_dietary(intent: UserIntent) -> UserIntent:
    """Ensure dietary_style is reflected in the dietary list used for compatibility scoring."""
    tags = {x.lower().strip() for x in intent.dietary}
    style = intent.dietary_style
    if style == "vegan" and "vegan" not in tags:
        intent.dietary = intent.dietary + ["vegan"]
        tags.add("vegan")
    elif style == "vegetarian" and not tags.intersection({"vegetarian", "vegan"}):
        intent.dietary = intent.dietary + ["vegetarian"]
    elif style == "pescatarian" and "pescatarian" not in tags:
        intent.dietary = intent.dietary + ["pescatarian"]
    return intent


def has_strict_food_constraints(intent: UserIntent) -> bool:
    if intent.dietary or intent.disliked_ingredients:
        return True
    if intent.dietary_style not in ("any", "omnivore"):
        return True
    if intent.health_goals:
        return True
    if intent.meal_intent == "healthy":
        return True
    return False
