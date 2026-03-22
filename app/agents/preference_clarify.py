"""
One short follow-up when cuisine/health intent is underspecified and profile does not already hold it.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.models.domain import UserIntent


def _low(msg: str) -> str:
    return msg.lower()


def preference_clarification_question(
    intent: UserIntent,
    message: str,
    profile_hint_json: str,
) -> Optional[str]:
    """
    Returns a single concise question, or None if we should proceed without asking.
    """
    if intent.needs_clarification and intent.clarifying_question:
        return None
    low = _low(message)
    prof: Dict[str, Any] = {}
    try:
        prof = json.loads(profile_hint_json) if profile_hint_json else {}
    except json.JSONDecodeError:
        pass

    stored_style = (prof.get("dietary_style") or "any") if isinstance(prof, dict) else "any"
    stored_health = prof.get("health_goals") or []
    if not isinstance(stored_health, list):
        stored_health = []

    veg_signals = (
        "vegetarian",
        "vegan",
        "pescatarian",
        "non-veg",
        "non veg",
        "nonveg",
        "meat",
        "chicken",
        "fish",
        "seafood",
        "omnivore",
    )
    user_named_style = any(s in low for s in veg_signals) or intent.dietary_style != "any"

    # Cuisine-specific diet question (only if style still unknown and user did not say)
    if intent.cuisine and stored_style == "any" and not user_named_style:
        c = intent.cuisine.lower()
        if c == "chinese":
            return (
                "For Chinese food, should I focus on vegetarian, vegan, or non-veg options? "
                "And noodles, rice, or something lighter?"
            )
        if c == "italian":
            return (
                "For Italian, do you want vegetarian or non-veg? "
                "Prefer pasta, pizza, or a lighter option like salad or soup? Any gluten-free or dairy-free needs?"
            )
        if c == "indian":
            return (
                "For Indian food, veg or non-veg? How spicy should it be — mild, medium, or hot? "
                "Rich curry or a lighter meal?"
            )

    # Vague healthy / light
    health_words = ("healthy", "clean eating", "nutritious", "light meal", "something light", "not greasy")
    if any(w in low for w in health_words) or intent.meal_intent == "healthy":
        if not intent.health_goals and not stored_health:
            return (
                "Got it — healthier direction. Should I lean toward high-protein, lower-calorie, "
                "low-oil / less fried, or just balanced lighter plates?"
            )

    if intent.meal_intent == "any" and any(w in low for w in ("quick", "fast", "grab")):
        if "relaxed" not in low and "sit" not in low:
            return None  # urgency often covers quick; optional skip

    return None
