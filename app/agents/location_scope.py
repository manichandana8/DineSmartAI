"""
Location specificity: broad named areas vs precise "near me", and best-in-area ranking hints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.agents.intent import detect_cuisine_from_message
from app.models.domain import UserIntent

# User is anchored to their device / tight radius — do not ask vague food clarification.
_PRECISE_LOCATION = re.compile(
    r"\b("
    r"near\s+me|around\s+me|close\s+to\s+me|nearby|walking\s+distance|"
    r"right\s+here|from\s+here|my\s+location|current\s+location|this\s+pin|map\s+pin|"
    r"within\s+\d+\s*(mi|mile|miles|km|block|blocks|min|minutes)\b"
    r")\b",
    re.I,
)

# Stronger "use map pin" signals only (excludes bare "nearby" so "in San Jose nearby" still geocodes San Jose).
_ANCHOR_SEARCH_TO_MAP_PIN = re.compile(
    r"\b("
    r"near\s+me|around\s+me|close\s+to\s+me|"
    r"right\s+here|from\s+here|my\s+location|current\s+location|this\s+pin|map\s+pin|"
    r"within\s+\d+\s*(mi|mile|miles|km|block|blocks|min|minutes)\b"
    r")\b",
    re.I,
)


@dataclass(frozen=True)
class NamedSearchArea:
    """When the user names an area, geocode this query and center search there."""

    geocode_query: str
    display_label: str


# First match wins — put longer / more specific phrases before shorter ones.
_NAMED_AREA_GEO_SPECS: List[Tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bdowntown\s+san\s+jose\b", re.I), "Downtown San Jose, CA, USA", "downtown San Jose"),
    (re.compile(r"\bdowntown\s+san\s+francisco\b", re.I), "Downtown San Francisco, CA, USA", "downtown San Francisco"),
    (re.compile(r"\bdowntown\s+oakland\b", re.I), "Downtown Oakland, CA, USA", "downtown Oakland"),
    (re.compile(r"\bdowntown\s+berkeley\b", re.I), "Downtown Berkeley, CA, USA", "downtown Berkeley"),
    (re.compile(r"\bdowntown\s+hayward\b", re.I), "Downtown Hayward, CA, USA", "downtown Hayward"),
    (re.compile(r"\bmountain\s+view\b", re.I), "Mountain View, CA, USA", "Mountain View"),
    (re.compile(r"\bredwood\s+city\b", re.I), "Redwood City, CA, USA", "Redwood City"),
    (re.compile(r"\bunion\s+city\b", re.I), "Union City, CA, USA", "Union City"),
    (re.compile(r"\bdaly\s+city\b", re.I), "Daly City, CA, USA", "Daly City"),
    (re.compile(r"\bwalnut\s+creek\b", re.I), "Walnut Creek, CA, USA", "Walnut Creek"),
    (re.compile(r"\bsanta\s+clara\b", re.I), "Santa Clara, CA, USA", "Santa Clara"),
    (re.compile(r"\bpalo\s+alto\b", re.I), "Palo Alto, CA, USA", "Palo Alto"),
    (re.compile(r"\bpleasanton\b", re.I), "Pleasanton, CA, USA", "Pleasanton"),
    (re.compile(r"\bconcord\b", re.I), "Concord, CA, USA", "Concord"),
    (re.compile(r"\bsunnyvale\b", re.I), "Sunnyvale, CA, USA", "Sunnyvale"),
    (re.compile(r"\bfremont\b", re.I), "Fremont, CA, USA", "Fremont"),
    (re.compile(r"\bhayward\b", re.I), "Hayward, CA, USA", "Hayward"),
    (re.compile(r"\bberkeley\b", re.I), "Berkeley, CA, USA", "Berkeley"),
    (re.compile(r"\boakland\b", re.I), "Oakland, CA, USA", "Oakland"),
    (re.compile(r"\bsan\s+jose\b", re.I), "San Jose, CA, USA", "San Jose"),
    (re.compile(r"\bsan\s+francisco\b", re.I), "San Francisco, CA, USA", "San Francisco"),
    (re.compile(r"\bs\.f\.|\bsf\b", re.I), "San Francisco, CA, USA", "San Francisco"),
    (re.compile(r"\beast\s+bay\b", re.I), "Oakland, CA, USA", "the East Bay"),
    (re.compile(r"\bsouth\s+bay\b", re.I), "San Jose, CA, USA", "the South Bay"),
    (re.compile(r"\bnorth\s+bay\b", re.I), "Santa Rosa, CA, USA", "the North Bay"),
    (re.compile(r"\bpeninsula\b", re.I), "Palo Alto, CA, USA", "the Peninsula"),
    (re.compile(r"\bbay\s+area\b", re.I), "San Francisco Bay Area, California, USA", "the Bay Area"),
]


def resolve_named_search_area(message: str) -> Optional[NamedSearchArea]:
    """
    If the user named a region/city (and did not anchor to device/pin), return what to geocode.
    Skips when they said near me / this pin / etc.
    """
    msg = message or ""
    if _ANCHOR_SEARCH_TO_MAP_PIN.search(msg):
        return None
    for pat, q, label in _NAMED_AREA_GEO_SPECS:
        if pat.search(msg):
            return NamedSearchArea(geocode_query=q, display_label=label)
    return None


# Named regions / cities → large search intent (when food goal is missing).
_BROAD_NAMED_PLACE = re.compile(
    r"\b("
    r"san\s+francisco|\bsf\b|s\.f\.|oakland|berkeley|san\s+jose|"
    r"santa\s+clara|palo\s+alto|mountain\s+view|sunnyvale|fremont|hayward|union\s+city|"
    r"redwood\s+city|daly\s+city|walnut\s+creek|concord|pleasanton|"
    r"bay\s+area|east\s+bay|south\s+bay|north\s+bay|peninsula|"
    r"in\s+downtown|downtown\s+\w+|uptown\s+\w+"
    r")\b",
    re.I,
)

_STREET_ADDRESS = re.compile(r"\b\d{3,5}\s+[\w\s]{2,40}\b(st|street|ave|avenue|rd|road|blvd|dr)\b", re.I)

# Enough food / experience signal to search without extra clarification.
_FOOD_OR_EXPERIENCE_SIGNAL = re.compile(
    r"\b("
    r"italian|thai|mexican|chinese|japanese|indian|korean|vietnamese|french|greek|turkish|"
    r"mediterranean|spanish|ethiopian|peruvian|caribbean|"
    r"burgers?|pizza|sushi|seafood|steak|bbq|barbecue|ramen|pho|tacos?|wings?|"
    r"boba|bubble\s+tea|ice\s+cream|gelato|coffee|bakery|dessert|"
    r"brunch|breakfast|lunch|dinner|supper|"
    r"pancakes?|waffles?|french\s+toast|crepes?|"
    r"vegan|vegetarian|halal|kosher|gluten|"
    r"healthy|organic|salad|bowl|keto|"
    r"quick\s+bite|fast\s+food|fine\s+dining|fancy|upscale|casual|romantic|date\s+night|"
    r"cheap|budget|affordable|expensive|splurge|mid[- ]range|under\s+\$|"
    r"unique|hidden\s+gem|trendy|popular|best|top\s+rated|highest\s+rated|good\s+places?|great\s+spots?|"
    r"restaurant|food|cuisine|eat|drinks?|cocktails?|wine\s+bar|brewery"
    r")\b",
    re.I,
)

_BEST_IN_AREA = re.compile(
    r"\b(best|top\s+rated|highest\s+rated|must-?try|"
    r"good\s+places?\s+in|great\s+spots?\s+in|where\s+to\s+eat\s+in)\b",
    re.I,
)


def location_search_moved_enough_to_reset(
    prev_intent_dict: Dict[str, Any],
    lat: float,
    lng: float,
    threshold_m: float = 2500.0,
) -> bool:
    """Fresh shortlist when the user's map pin moved significantly vs last recommendation."""
    try:
        olat = float(prev_intent_dict.get("_search_latitude"))
        olng = float(prev_intent_dict.get("_search_longitude"))
    except (TypeError, ValueError):
        return False
    from app.services.location import haversine_m

    return haversine_m(float(lat), float(lng), olat, olng) >= threshold_m


def apply_location_query_heuristics(message: str, intent: UserIntent) -> UserIntent:
    """Set ranking flags from raw message (not persisted as user-facing preferences)."""
    msg = message or ""
    intent.best_in_area_query = bool(_BEST_IN_AREA.search(msg))
    return intent


def is_location_scoping_followup(message: str) -> bool:
    """
    True when the message mainly recenters search on a named area without a new food/cuisine ask.
    Used to carry dish_preferences from the previous recommendation turn.
    """
    msg = (message or "").strip()
    if not msg or not resolve_named_search_area(msg):
        return False
    if detect_cuisine_from_message(msg):
        return False
    if _FOOD_OR_EXPERIENCE_SIGNAL.search(msg.lower()):
        return False
    return True


def merge_food_intent_for_location_followup(
    prev_intent_dict: Dict[str, Any],
    intent: UserIntent,
    message: str,
) -> UserIntent:
    """
    Preserve food signals from the last turn when the user only adds or changes geography
    (e.g. "in Fremont" after "I want pancakes").
    """
    if not prev_intent_dict or not is_location_scoping_followup(message):
        return intent
    d = intent.model_dump()
    prev_dp = prev_intent_dict.get("dish_preferences") or []
    if isinstance(prev_dp, list) and prev_dp:
        cur = list(d.get("dish_preferences") or [])
        if not cur:
            d["dish_preferences"] = [str(x) for x in prev_dp if str(x).strip()]
    pie = str(prev_intent_dict.get("meal_intent") or "any").lower()
    cie = str(d.get("meal_intent") or "any").lower()
    if cie == "any" and pie in ("quick", "relaxed", "indulgent", "healthy"):
        d["meal_intent"] = pie
    return UserIntent.model_validate(d)


def broad_area_needs_food_clarification(message: str, intent: UserIntent) -> bool:
    """
    User named a broad area (e.g. city) without enough food/experience intent — ask before searching.
    """
    msg = (message or "").strip()
    if not msg:
        return False
    if _PRECISE_LOCATION.search(msg) or _STREET_ADDRESS.search(msg):
        return False
    if not _BROAD_NAMED_PLACE.search(msg):
        return False
    if _FOOD_OR_EXPERIENCE_SIGNAL.search(msg):
        return False
    if detect_cuisine_from_message(msg):
        return False
    if intent.visit_category != "meal":
        return False
    if intent.cuisine:
        return False
    if intent.dish_preferences:
        return False
    return True


def broad_location_prompt() -> str:
    return (
        "You mentioned a whole city or region — that’s a big area to cover. "
        "What kind of food or experience are you in the mood for (quick bite, casual dinner, date night, "
        "a specific cuisine, or something unique)? Pick a few options below or type your own.\n\n"
        "If you name a city or neighborhood in your next message, we’ll center search there automatically; "
        "otherwise results use your map pin."
    )


def broad_location_chip_groups() -> List[Dict[str, Any]]:
    return [
        {
            "title": "Experience",
            "chips": [
                {"label": "Highly rated mix — surprise me", "value": "mix of highly rated popular restaurants varied cuisines"},
                {"label": "Casual neighborhood dinner", "value": "casual neighborhood restaurant dinner"},
                {"label": "Date night / romantic", "value": "romantic date night dinner restaurant"},
                {"label": "Quick affordable bite", "value": "quick tasty affordable bite"},
                {"label": "Unique / hidden gem vibe", "value": "unique lesser known restaurant great reviews"},
                {"label": "Fine dining / splurge", "value": "fine dining upscale special occasion"},
            ],
        },
        {
            "title": "Cuisine (optional)",
            "chips": [
                {"label": "Italian", "value": "Italian food"},
                {"label": "Mexican", "value": "Mexican food"},
                {"label": "Japanese / sushi", "value": "Japanese sushi restaurant"},
                {"label": "Indian", "value": "Indian restaurant"},
                {"label": "Thai", "value": "Thai restaurant"},
                {"label": "American / burgers", "value": "American burgers casual"},
            ],
        },
    ]
