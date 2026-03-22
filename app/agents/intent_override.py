"""Resolve conflicts when the user's message clearly asks for food that contradicts saved profile defaults."""

from __future__ import annotations

import re

from app.models.domain import UserIntent

_SEAFOOD_PHRASES = (
    "seafood",
    "sea food",
    "sea-food",
    "shellfish",
    "sushi",
    "sashimi",
    "poke bowl",
    "poké",
    "raw bar",
    "oyster",
    "lobster",
    "crab",
    "shrimp",
    "prawn",
    "scallop",
    "mussel",
    "clam",
    "ceviche",
    "fish taco",
    "fish and chips",
    "grilled fish",
    "fried fish",
)
_FISH_WORD = re.compile(
    r"\b(fish|fishes|salmon|tuna|halibut|cod|snapper|bass|tilapia|mahi|swordfish|octopus|squid|eel)\b",
    re.I,
)
_POKE_WORD = re.compile(r"\bpoke\b", re.I)
_MEAT_PHRASES = (
    "steak",
    "beef",
    "pork",
    "lamb",
    "chicken",
    "turkey",
    "duck",
    "bacon",
    "burger",
    "hamburger",
    "ribs",
    "bbq",
    "barbecue",
    "wings",
    "carnivore",
    "with meat",
    "non-veg",
    "non veg",
    "nonveg",
)

_PLANT_ONLY_STYLES = frozenset({"vegan", "vegetarian"})

# If the match is negated (user doesn't want this food), do not treat as explicit seafood/meat ask.
_NEGATION_BEFORE_END_RE = re.compile(
    r"(?:"
    r"\bno$|"
    r"\bnot$|"
    r"\bnever$|"
    r"\bwithout$|"
    r"\bavoid(?:ing)?$|"
    r"\bskipp?(?:ing)?$|"
    r"\bdon'?t\s+want\b.*$|"
    r"\bdoesn'?t\s+want\b.*$|"
    r"\bdo\s+not\s+want\b.*$|"
    r"\bdon'?t\s+like\b.*$|"
    r"\bdo\s+not\s+like\b.*$|"
    r"\bdon'?t\s+eat\b.*$|"
    r"\bnot\s+interested\s+in$|"
    r"\bno\s+more$|"
    r"\bhate$|"
    r"\bdislikes?$|"
    r"\bnot\s+a\s+fan\s+of$|"
    r"\brather\s+not$|"
    r"\bwon'?t\s+eat$|"
    r"\bcan'?t\s+stand$|"
    r"\bcannot\s+stand$|"
    # e.g. before "chicken": "no fish or" — list ends with "or" before the next item
    r"\bno\s+[\w'-]+(?:\s+or\s+[\w'-]+)*\s+or\s*$"
    r")",
    re.I | re.S,
)


def _is_negated_food_match(low: str, start: int, end: int) -> bool:
    """True if this span for a seafood/meat cue is in a negated context."""
    if end < len(low):
        suffix = low[end : min(len(low), end + 14)]
        if re.match(r"-(?:free|less)\b", suffix):
            return True
    prefix = low[max(0, start - 8) : start]
    if re.search(r"\bnon\s*[-]?\s*$", prefix, re.I):
        return True
    before = low[max(0, start - 160) : start]
    tail = before.rstrip()
    if not tail:
        return False
    return bool(_NEGATION_BEFORE_END_RE.search(tail))


def _phrase_match_positive(low: str, phrase: str) -> bool:
    """First occurrence of phrase that is not locally negated."""
    if not phrase:
        return False
    start = 0
    plen = len(phrase)
    while True:
        i = low.find(phrase, start)
        if i == -1:
            return False
        # Word-boundary style guard for short tokens (e.g. avoid "crab" in "crabby" if phrase is "crab")
        if phrase[0].isalnum():
            if i > 0 and low[i - 1].isalnum():
                start = i + 1
                continue
            end = i + plen
            if end < len(low) and low[end].isalnum():
                start = i + 1
                continue
        else:
            end = i + plen
        if not _is_negated_food_match(low, i, end):
            return True
        start = i + 1


def _regex_match_positive(pattern: re.Pattern[str], low: str) -> bool:
    for m in pattern.finditer(low):
        if not _is_negated_food_match(low, m.start(), m.end()):
            return True
    return False


def _wants_seafood(low: str) -> bool:
    if any(_phrase_match_positive(low, p) for p in _SEAFOOD_PHRASES):
        return True
    if _regex_match_positive(_FISH_WORD, low):
        return True
    return _regex_match_positive(_POKE_WORD, low)


def _wants_land_meat(low: str) -> bool:
    return any(_phrase_match_positive(low, p) for p in _MEAT_PHRASES)


def _strip_plant_only_diet_tags(dietary: list[str]) -> list[str]:
    out: list[str] = []
    for x in dietary:
        xl = x.lower().strip()
        if xl in _PLANT_ONLY_STYLES:
            continue
        if xl in ("plant-based", "plant based") and "fish" not in xl:
            continue
        out.append(x)
    return out


def apply_explicit_meal_requests(message: str, intent: UserIntent) -> UserIntent:
    """
    If the user clearly asks for seafood or meat, do not keep profile-merged vegan/vegetarian
    constraints for this turn. Sets cuisine when missing and marks intent so we do not overwrite
    long-lived profile diet prefs on this request.
    """
    low = message.lower()
    wants_fish = _wants_seafood(low)
    wants_meat = _wants_land_meat(low)
    if not wants_fish and not wants_meat:
        return intent

    # Same message explicitly asks for plant-only — respect it (do not force pescatarian/omnivore).
    if re.search(r"\b(vegan|vegetarian|plant[- ]based)\b", low):
        return intent

    intent.ephemeral_diet_override = True
    intent.dietary = _strip_plant_only_diet_tags(list(intent.dietary))

    if wants_fish:
        intent.dietary_style = "pescatarian"
        bad_cuisine = {"vegan", "vegetarian"}
        cur = (intent.cuisine or "").strip().lower()
        if cur in bad_cuisine or not intent.cuisine:
            intent.cuisine = "Seafood"
        if "fish" not in low and "sushi" not in low and "sashimi" not in low:
            if not intent.dish_preferences:
                intent.dish_preferences = []
            for tag in ("seafood", "fish"):
                if tag not in [d.lower() for d in intent.dish_preferences]:
                    intent.dish_preferences.append(tag)
    else:
        intent.dietary_style = "omnivore"

    return intent
