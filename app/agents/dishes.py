from __future__ import annotations

from app.integrations.llm import suggest_dishes_llm
from app.models.domain import DishSuggestion, RestaurantCandidate, UserIntent
from app.models.db import UserProfile


def _obvious_diet_conflict(dish_name: str, intent: UserIntent) -> bool:
    n = dish_name.lower()
    diets = {x.lower() for x in intent.dietary}
    vegan = intent.dietary_style == "vegan" or "vegan" in diets
    vegetarian = intent.dietary_style == "vegetarian" or "vegetarian" in diets or vegan
    if vegan:
        if any(
            w in n
            for w in (
                "chicken",
                "beef",
                "pork",
                "lamb",
                "fish",
                "salmon",
                "tuna",
                "shrimp",
                "crab",
                "egg",
                "cheese",
                "cream",
                "butter",
                "honey",
            )
        ):
            return True
    elif vegetarian:
        if any(w in n for w in ("chicken", "beef", "pork", "lamb", "fish", "salmon", "shrimp", "bacon")):
            return True
    if "halal" in diets:
        if any(w in n for w in ("pork", "bacon", "ham", "chorizo", "wine", "beer", "vodka", "rum")):
            return True
    if "gluten-free" in diets or "gluten free" in diets:
        risky = ("pasta", "bread", "bun", "dumpling", "noodle", "cake", "croissant")
        if any(w in n for w in risky) and "gluten" not in n and " gf" not in n and not n.startswith("gf "):
            return True
    for ing in intent.disliked_ingredients:
        il = ing.lower().strip()
        if len(il) >= 3 and il in n:
            return True
    return False


async def recommend_dishes(
    intent: UserIntent,
    restaurant: RestaurantCandidate,
    profile: UserProfile,
) -> list[DishSuggestion]:
    spice = intent.spice_tolerance if intent.spice_tolerance != "any" else (profile.spice_tolerance or "any")
    menu_names = [m.name for m in restaurant.menu_items]
    cuisine_for_llm = intent.cuisine or (
        ", ".join(restaurant.cuisine_tags[:4]) if restaurant.cuisine_tags else None
    )
    raw = await suggest_dishes_llm(
        restaurant.name,
        cuisine_for_llm,
        menu_names,
        intent.dietary,
        spice,
        intent.dietary_style,
        intent.health_goals,
        intent.meal_intent,
        intent.dish_preferences,
        intent.disliked_ingredients,
    )
    out: list[DishSuggestion] = []
    for it in raw:
        name = str(it.get("name") or "")
        if _obvious_diet_conflict(name, intent):
            continue
        c = it.get("caution") or None
        if c == "":
            c = None
        if not c and (intent.dietary or intent.dietary_style not in ("any", "omnivore")):
            c = "Confirm ingredients with the restaurant if you have strict allergies or religious dietary rules."
        out.append(
            DishSuggestion(
                name=name,
                why=it.get("why") or "Matches what you asked for.",
                caution=c,
            )
        )
    if out:
        return out[:3]

    for m in restaurant.menu_items[:5]:
        if _obvious_diet_conflict(m.name, intent):
            continue
        out.append(
            DishSuggestion(
                name=m.name,
                why=(m.description or "Popular at this spot.")[:120],
                caution="Confirm allergens with the restaurant when ordering.",
            )
        )
        if len(out) >= 3:
            break
    if not out and intent.cuisine:
        out.append(
            DishSuggestion(
                name=f"Chef's {intent.cuisine} special",
                why="Ask for the daily special aligned with your cuisine preference.",
                caution="Confirm dietary needs with the restaurant.",
            )
        )
    return out[:3]
