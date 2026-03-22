from __future__ import annotations

import json
from typing import Any

from app.models.db import UserProfile
from app.models.domain import UserIntent


def profile_to_dict(p: UserProfile) -> dict[str, Any]:
    def loads(s: str) -> Any:
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return []

    return {
        "favorite_cuisines": loads(p.favorite_cuisines),
        "budget_tier": p.budget_tier,
        "spice_tolerance": getattr(p, "spice_tolerance", "any"),
        "disliked_ingredients": loads(p.disliked_ingredients),
        "dietary_restrictions": loads(p.dietary_restrictions),
        "ambience_prefs": loads(p.ambience_prefs),
        "default_mode": p.default_mode,
        "dietary_style": getattr(p, "dietary_style", None) or "any",
        "meal_intent": getattr(p, "meal_intent", None) or "any",
        "health_goals": loads(getattr(p, "health_goals", None) or "[]"),
        "dish_preferences": loads(getattr(p, "dish_preferences", None) or "[]"),
    }


def merge_intent_with_profile(intent: UserIntent, profile: UserProfile) -> UserIntent:
    d = profile_to_dict(profile)
    bt = d.get("budget_tier")
    if intent.budget == "any" and bt in ("low", "medium", "high"):
        intent.budget = bt
    if intent.mode == "either" and d.get("default_mode") in ("dine_in", "delivery", "pickup"):
        intent.mode = d["default_mode"]
    if not intent.dietary and d.get("dietary_restrictions"):
        intent.dietary = list(d["dietary_restrictions"])
    if not intent.disliked_ingredients and d.get("disliked_ingredients"):
        intent.disliked_ingredients = list(d["disliked_ingredients"])
    if intent.dietary_style == "any" and d.get("dietary_style") not in (None, "any"):
        intent.dietary_style = d["dietary_style"]
    if intent.meal_intent == "any" and d.get("meal_intent") not in (None, "any"):
        intent.meal_intent = d["meal_intent"]
    if not intent.health_goals and d.get("health_goals"):
        intent.health_goals = list(d["health_goals"])
    if not intent.dish_preferences and d.get("dish_preferences"):
        intent.dish_preferences = list(d["dish_preferences"])
    if intent.spice_tolerance == "any" and d.get("spice_tolerance") not in (None, "any"):
        intent.spice_tolerance = d["spice_tolerance"]
    return intent


def personalization_vector(profile: UserProfile) -> dict[str, float]:
    try:
        w = json.loads(profile.personalization_weights or "{}")
    except json.JSONDecodeError:
        w = {}
    out: dict[str, float] = {}
    for k, v in w.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def place_boost_from_feedback(
    place_id: str,
    recent_feedback: list[tuple[str, str]],
) -> float:
    """recent_feedback: (place_id, action)."""
    boost = 0.75
    for pid, action in recent_feedback[-30:]:
        if pid != place_id:
            continue
        if action == "accepted":
            boost += 0.06
        elif action == "visited":
            boost += 0.08
        elif action == "ordered":
            boost += 0.07
        elif action == "rejected":
            boost -= 0.12
    return max(0.15, min(1.0, boost))
