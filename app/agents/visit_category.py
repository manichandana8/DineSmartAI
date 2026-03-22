"""
Visit intent → place type for Google Places (New) search and ranking tweaks.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.models.domain import UserIntent, VisitCategory

# Order matters: first match wins (more specific before general).
_CATEGORY_PATTERNS: List[Tuple[re.Pattern[str], VisitCategory]] = [
    (re.compile(r"\b(bubble\s*tea|boba|pearl\s*milk\s*tea|tapioca\s*drink)\b", re.I), "boba"),
    (re.compile(r"\b(ice\s*cream|gelato|frozen\s*yogurt|froyo|sorbet\s*shop)\b", re.I), "ice_cream"),
    (re.compile(r"\b(espresso|latte|cappuccino|coffee\s*shop|café|specialty\s*coffee)\b", re.I), "coffee"),
    (re.compile(r"\b(bakery|croissant|pastry\s*shop|bread\s*shop)\b", re.I), "bakery"),
    (re.compile(r"\b(fast\s*food|drive[\s-]*thru|quick\s*service\s*restaurant)\b", re.I), "fast_food"),
    (re.compile(r"\b(fine\s*dining|upscale\s*restaurant|tasting\s*menu|chef\s*table)\b", re.I), "fine_dining"),
    (re.compile(r"\b(dessert|pastries|pastry|cake\s*shop|sweet\s*shop|patisserie)\b", re.I), "dessert"),
    (re.compile(r"\b(juice\s*bar|smoothie|bubble\s*juice)\b", re.I), "beverages"),
    (re.compile(r"\b(snack|quick\s*bite|small\s*bite|grab\s*a\s*bite)\b", re.I), "snack"),
    (re.compile(r"\b(drinks?\s*only|just\s*drinks|cocktail|wine\s*bar|bar\s*hopping)\b", re.I), "beverages"),
]

_VALID: Tuple[VisitCategory, ...] = (
    "meal",
    "snack",
    "dessert",
    "ice_cream",
    "beverages",
    "coffee",
    "boba",
    "bakery",
    "fast_food",
    "fine_dining",
)


def normalize_visit_category(raw: Any) -> VisitCategory:
    if raw is None:
        return "meal"
    s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "icecream": "ice_cream",
        "bubble_tea": "boba",
        "bubbletea": "boba",
        "drink": "beverages",
        "drinks": "beverages",
        "juice": "beverages",
        "dine": "meal",
        "restaurant": "meal",
        "lunch": "meal",
        "dinner": "meal",
        "breakfast": "meal",
        "brunch": "meal",
    }
    s = aliases.get(s, s)
    if s in _VALID:
        return s  # type: ignore[return-value]
    return "meal"


_MEAL_CONTEXT = re.compile(
    r"\b(lunch|dinner|breakfast|brunch|full\s*meal|sit[-\s]?down|restaurant)\b",
    re.I,
)


def should_reset_refinement_context(prev_category: Any, message: str) -> bool:
    """
    When the user clearly changed place type, omit prior-turn summary so refine LLM
    is not anchored to the wrong category. Neutral tweaks (e.g. \"closer\") keep context.
    """
    old_vc = normalize_visit_category(prev_category)
    msg_vc = detect_visit_category_from_message(message)
    if msg_vc != "meal" and msg_vc != old_vc:
        return True
    if old_vc != "meal" and _MEAL_CONTEXT.search(message):
        return True
    return False


def detect_visit_category_from_message(message: str) -> VisitCategory:
    low = message.lower()
    for rx, cat in _CATEGORY_PATTERNS:
        if rx.search(low):
            return cat
    if re.search(r"\b(lunch|dinner|breakfast|brunch|cuisine|restaurant|food near)\b", low):
        return "meal"
    return "meal"


def ensure_visit_category(intent: UserIntent, message: str) -> UserIntent:
    """Message heuristics win when they imply a non-meal place; else trust normalized model field."""
    detected = detect_visit_category_from_message(message)
    llm_vc = normalize_visit_category(getattr(intent, "visit_category", None))
    if detected != "meal":
        intent.visit_category = detected
    else:
        intent.visit_category = llm_vc
    return intent


# Places API (New) searchText: includedType + textQuery. strictTypeFiltering False when type is broad.
_PLACES_SEARCH: Dict[VisitCategory, Dict[str, Any]] = {
    "meal": {
        "included_type": "restaurant",
        "strict": True,
        "text_template": "{kw} restaurant",
        "fallback_text": "restaurant",
    },
    "ice_cream": {
        "included_type": "ice_cream_shop",
        "strict": True,
        "text_template": "{kw}",
        "fallback_text": "ice cream gelato",
    },
    "coffee": {
        "included_type": "coffee_shop",
        "strict": True,
        "text_template": "{kw}",
        "fallback_text": "coffee cafe",
    },
    "boba": {
        "included_type": "cafe",
        "strict": False,
        "text_template": "{kw} bubble tea boba milk tea pearl tea",
        "fallback_text": "bubble tea boba milk tea pearl tea",
    },
    "bakery": {
        "included_type": "bakery",
        "strict": True,
        "text_template": "{kw}",
        "fallback_text": "bakery pastries",
    },
    "dessert": {
        "included_type": "bakery",
        "strict": False,
        "text_template": "{kw} dessert cake pastries sweet",
        "fallback_text": "dessert bakery pastries",
    },
    "snack": {
        "included_type": "cafe",
        "strict": False,
        "text_template": "{kw} cafe quick bite snack",
        "fallback_text": "cafe quick bite",
    },
    "beverages": {
        "included_type": "cafe",
        "strict": False,
        "text_template": "{kw} juice smoothie drinks",
        "fallback_text": "juice bar smoothie cafe",
    },
    "fast_food": {
        "included_type": "fast_food_restaurant",
        "strict": True,
        "text_template": "{kw}",
        "fallback_text": "fast food",
    },
    "fine_dining": {
        "included_type": "restaurant",
        "strict": False,
        "text_template": "{kw} fine dining upscale",
        "fallback_text": "fine dining restaurant",
    },
}


def places_search_params(visit_category: VisitCategory) -> Dict[str, Any]:
    return dict(_PLACES_SEARCH.get(visit_category, _PLACES_SEARCH["meal"]))


def category_keyword_prefix(visit_category: VisitCategory) -> str:
    """Extra tokens merged into Places text query (after user/build_keyword terms)."""
    p = places_search_params(visit_category)
    fb = str(p.get("fallback_text") or "")
    if visit_category == "meal":
        return ""
    return fb


def ranking_weight_deltas(visit_category: VisitCategory) -> Dict[str, float]:
    """Added to default_weights before renormalization."""
    d: Dict[str, float] = {
        "meal": {},
        "ice_cream": {"rating": 0.06, "distance": 0.06, "menu": 0.05, "price": 0.02},
        "boba": {"rating": 0.05, "menu": 0.06, "distance": 0.04},
        "coffee": {"rating": 0.04, "distance": 0.05, "ambience": 0.03},
        "dessert": {"rating": 0.05, "ambience": 0.06, "menu": 0.04},
        "bakery": {"rating": 0.04, "distance": 0.04, "menu": 0.05},
        "snack": {"distance": 0.08, "price": 0.04, "urgency": 0.04, "rating": 0.02},
        "beverages": {"rating": 0.04, "distance": 0.05},
        "fast_food": {"distance": 0.06, "urgency": 0.04, "price": 0.03},
        "fine_dining": {"ambience": 0.08, "rating": 0.05, "price": 0.04, "distance": -0.04},
    }
    return d.get(visit_category, {})


def structured_picks_category_note(visit_category: VisitCategory) -> str:
    notes = {
        "ice_cream": "Category: ice cream / frozen treats — mention flavors, dairy-free or vegan options if relevant.",
        "boba": "Category: bubble tea / boba — these are bubble tea cafés, tea shops, or restaurants that sell boba; mention milk tea vs fruit tea, toppings, sugar/ice if inferable from facts.",
        "coffee": "Category: coffee shop — mention roast style, espresso drinks, pastry pairings if relevant.",
        "dessert": "Category: desserts — pastries vs cakes vs lighter sweets; dietary notes.",
        "bakery": "Category: bakery — breads, viennoiserie, savories vs sweet.",
        "snack": "Category: snacks / quick bites — speed, portion, savory vs sweet.",
        "beverages": "Category: drinks — juice, smoothie, or other beverages.",
        "fast_food": "Category: quick service — speed and convenience.",
        "fine_dining": "Category: upscale dining — service, atmosphere, occasion fit.",
        "meal": "",
    }
    return notes.get(visit_category, "")


def visit_category_clarification_hint(intent: UserIntent, message: str) -> Optional[str]:
    """Optional one-line question when category is clear but details help."""
    if intent.needs_clarification and intent.clarifying_question:
        return None
    # Ice cream / boba / snack / dessert: do not block search — return picks first; users refine on follow-up.
    return None
