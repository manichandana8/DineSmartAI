from __future__ import annotations

import json

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.models.domain import UserProfileOut, UserProfilePatch
from app.services.memory import get_or_create_profile

router = APIRouter(prefix="/v1", tags=["profile"])


def _out(p) -> UserProfileOut:
    return UserProfileOut(
        user_id=p.id,
        contact_email=getattr(p, "contact_email", None),
        favorite_cuisines=json.loads(p.favorite_cuisines or "[]"),
        budget_tier=p.budget_tier,
        spice_tolerance=getattr(p, "spice_tolerance", "any"),
        disliked_ingredients=json.loads(p.disliked_ingredients or "[]"),
        dietary_restrictions=json.loads(p.dietary_restrictions or "[]"),
        ambience_prefs=json.loads(p.ambience_prefs or "[]"),
        default_mode=p.default_mode,
        dietary_style=getattr(p, "dietary_style", None) or "any",
        meal_intent=getattr(p, "meal_intent", None) or "any",
        health_goals=json.loads(getattr(p, "health_goals", None) or "[]"),
        dish_preferences=json.loads(getattr(p, "dish_preferences", None) or "[]"),
    )


@router.get("/profile/{user_id}", response_model=UserProfileOut)
def get_profile(user_id: str, session: SessionDep) -> UserProfileOut:
    p = get_or_create_profile(session, user_id)
    return _out(p)


@router.patch("/profile/{user_id}", response_model=UserProfileOut)
def patch_profile(user_id: str, body: UserProfilePatch, session: SessionDep) -> UserProfileOut:
    p = get_or_create_profile(session, user_id)
    if body.contact_email is not None:
        em = (body.contact_email or "").strip()
        p.contact_email = em or None
    if body.favorite_cuisines is not None:
        p.favorite_cuisines = json.dumps(body.favorite_cuisines)
    if body.budget_tier is not None:
        p.budget_tier = body.budget_tier
    if body.spice_tolerance is not None:
        p.spice_tolerance = body.spice_tolerance
    if body.disliked_ingredients is not None:
        p.disliked_ingredients = json.dumps(body.disliked_ingredients)
    if body.dietary_restrictions is not None:
        p.dietary_restrictions = json.dumps(body.dietary_restrictions)
    if body.ambience_prefs is not None:
        p.ambience_prefs = json.dumps(body.ambience_prefs)
    if body.default_mode is not None:
        p.default_mode = body.default_mode
    if body.dietary_style is not None:
        p.dietary_style = body.dietary_style
    if body.meal_intent is not None:
        p.meal_intent = body.meal_intent
    if body.health_goals is not None:
        p.health_goals = json.dumps(body.health_goals)
    if body.dish_preferences is not None:
        p.dish_preferences = json.dumps(body.dish_preferences)
    session.add(p)
    session.commit()
    session.refresh(p)
    return _out(p)
