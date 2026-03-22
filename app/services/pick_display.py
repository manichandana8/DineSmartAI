"""Derived display strings for recommendation cards (distance vs delivery, diet, cuisine)."""

from __future__ import annotations

import re
from typing import Optional

from app.models.domain import RestaurantCandidate, UserIntent

# Common neighborhood tokens if they appear in formatted addresses (expand over time).
_NEIGHBORHOOD_TOKENS = (
    "mission",
    "soma",
    "financial district",
    "downtown",
    "hayward",
    "fremont",
    "berkeley",
    "oakland",
    "palo alto",
    "mountain view",
    "castro",
    "noe valley",
    "inner sunset",
    "outer sunset",
    "chinatown",
    "japantown",
    "embarcadero",
    "dogpatch",
    "potrero",
    "tenderloin",
    "north beach",
)


def format_full_address(address: Optional[str]) -> str:
    """Always show something; Maps is the fallback when Places omits the line."""
    s = (address or "").strip()
    if s:
        return s
    return "Full street address not in listing — open Navigate or Maps for exact location."


def neighborhood_from_address(address: Optional[str]) -> str:
    """
    Best-effort area / sublocality from Google's comma-separated formattedAddress.
    US examples often: street, city, ST zip — sometimes: street, neighborhood, city, ...
    """
    s = (address or "").strip()
    if not s:
        return ""
    low = s.lower()
    for tok in _NEIGHBORHOOD_TOKENS:
        if tok in low:
            return tok.title()
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) >= 4:
        mid = parts[1]
        if len(mid) <= 48 and not re.match(r"^[A-Z]{2}\s+\d{5}", mid):
            return mid
    return ""


def format_price_display(price_level: Optional[int]) -> str:
    if price_level is None:
        return "Not listed by maps data"
    n = min(max(price_level, 1), 4)
    return "$" * n


def cuisine_line(restaurant: RestaurantCandidate, intent: UserIntent) -> str:
    tags = [t for t in restaurant.cuisine_tags[:5] if t]
    if intent.cuisine:
        ic = intent.cuisine.strip()
        if not tags:
            return ic
        low = ic.lower()
        if any(low in t.lower() for t in tags):
            return ", ".join(tags)
        return f"{ic} · " + ", ".join(tags)
    if tags:
        return ", ".join(tags)
    return "General dining"


def format_opening_hours_card(restaurant: RestaurantCandidate) -> str:
    """Multiline text for UI: open-now hint plus weekday hours from Places."""
    lines_out: list[str] = []
    if restaurant.open_now is True:
        lines_out.append("Open now (per Google)")
    elif restaurant.open_now is False:
        lines_out.append("Likely closed now (per Google)")
    for line in restaurant.opening_hours_lines[:6]:
        lines_out.append(line)
    if len(restaurant.opening_hours_lines) > 6:
        lines_out.append("…")
    if not lines_out:
        return "Hours not in listing — check Maps or call ahead"
    return "\n".join(lines_out)


def distance_or_time_line(intent: UserIntent, distance_m: float) -> str:
    mi = distance_m / 1609.344
    mi_s = f"{mi:.1f} mi" if mi < 10 else f"{round(mi)} mi"
    if intent.mode == "delivery":
        low = max(18, int(15 + (mi * 5)))
        high = max(low + 8, int(25 + (mi * 7)))
        return (
            f"~{mi_s} from you; typical delivery often ~{low}–{high} min "
            "(varies by platform, traffic, and prep)"
        )
    if intent.mode == "pickup":
        lo = max(12, int(8 + mi * 3))
        hi = max(lo + 5, int(15 + mi * 4))
        return f"~{mi_s} away; pickup often ~{lo}–{hi} min with order-ahead (estimate)"
    if intent.mode == "dine_in":
        if intent.urgency == "now":
            return f"~{mi_s} away — dine-in; good when you want a table soon"
        return f"~{mi_s} away — suited for dine-in"
    return f"~{mi_s} away"


def dietary_compatibility_line(intent: UserIntent, restaurant: RestaurantCandidate) -> str:
    bits: list[str] = []
    style = intent.dietary_style
    if style == "vegan":
        bits.append(
            "Vegan: prioritize clearly labeled plant-based items; confirm sauces, dairy, and fryer cross-contact with staff."
        )
    elif style == "vegetarian":
        bits.append(
            "Vegetarian: cheese/broth/fish sauce can hide in soups and sauces—ask if you are strict."
        )
    elif style == "pescatarian":
        bits.append("Pescatarian: seafood and vegetable-forward plates are usually the safest lane.")
    elif style == "eggtarian":
        bits.append("Eggs allowed, no meat/fish—verify broth bases and hidden meats in sauces.")

    if intent.dietary:
        bits.append("Restrictions to double-check when ordering: " + ", ".join(intent.dietary) + ".")

    if intent.health_goals:
        bits.append(
            "For your health focus ("
            + ", ".join(intent.health_goals)
            + "), favor grilled, steamed, or vegetable-forward plates and ask for sauces on the side."
        )

    if intent.meal_intent == "healthy":
        bits.append("Healthy tilt: look for salads, bowls, grilled proteins, and lighter preparations.")

    if intent.spice_tolerance in ("mild", "medium", "hot") and intent.spice_tolerance != "any":
        bits.append(f"Spice preference: {intent.spice_tolerance}—request heat level when ordering.")

    menu_hint = ", ".join(m.name for m in restaurant.menu_items[:4])
    if menu_hint:
        bits.append("Menu signals from listings: " + menu_hint[:180] + ("…" if len(menu_hint) > 180 else ""))

    if not bits:
        return "Standard menu—state allergies and dietary needs clearly when you order."
    return " ".join(bits)


def base_ambience(restaurant: RestaurantCandidate) -> str:
    if restaurant.ambience_hints:
        return ", ".join(restaurant.ambience_hints[:4])
    # Light signal from Google-style types
    chill = [t.replace("_", " ") for t in restaurant.types if t not in ("restaurant", "food", "point_of_interest", "establishment")]
    if chill[:3]:
        return ", ".join(chill[:3])
    return ""
