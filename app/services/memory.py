from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, List, Optional, Tuple

from sqlmodel import Session, select

from app.models.db import FeedbackEvent, PendingAutomation, RecommendationEvent, UserProfile
from app.models.domain import UserIntent


def get_or_create_profile(session: Session, user_id: str) -> UserProfile:
    p = session.get(UserProfile, user_id)
    if p:
        return p
    p = UserProfile(id=user_id)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def profile_hint_json(session: Session, user_id: str) -> str:
    p = get_or_create_profile(session, user_id)
    d = {
        "favorite_cuisines": json.loads(p.favorite_cuisines or "[]"),
        "budget_tier": p.budget_tier,
        "spice_tolerance": getattr(p, "spice_tolerance", "any"),
        "dietary_restrictions": json.loads(p.dietary_restrictions or "[]"),
        "disliked_ingredients": json.loads(p.disliked_ingredients or "[]"),
        "ambience_prefs": json.loads(p.ambience_prefs or "[]"),
        "default_mode": p.default_mode,
        "dietary_style": getattr(p, "dietary_style", None) or "any",
        "meal_intent": getattr(p, "meal_intent", None) or "any",
        "health_goals": json.loads(getattr(p, "health_goals", None) or "[]"),
        "dish_preferences": json.loads(getattr(p, "dish_preferences", None) or "[]"),
    }
    return json.dumps(d)


def persist_preferences_from_intent(session: Session, profile: UserProfile, intent: UserIntent) -> None:
    """Remember resolved food preferences for future turns (only overwrite when intent states a value)."""
    changed = False
    skip_saved_diet = getattr(intent, "ephemeral_diet_override", False)
    if intent.dietary_style != "any" and not skip_saved_diet:
        profile.dietary_style = intent.dietary_style
        changed = True
    if intent.meal_intent != "any":
        profile.meal_intent = intent.meal_intent
        changed = True
    if intent.spice_tolerance != "any":
        profile.spice_tolerance = intent.spice_tolerance
        changed = True
    if intent.health_goals:
        profile.health_goals = json.dumps(intent.health_goals)
        changed = True
    if intent.dish_preferences:
        profile.dish_preferences = json.dumps(intent.dish_preferences)
        changed = True
    if intent.dietary and not skip_saved_diet:
        profile.dietary_restrictions = json.dumps(intent.dietary)
        changed = True
    if intent.disliked_ingredients:
        profile.disliked_ingredients = json.dumps(intent.disliked_ingredients)
        changed = True
    if changed:
        profile.updated_at = datetime.utcnow()
        session.add(profile)
        session.commit()


def get_recommendation_for_user(
    session: Session, user_id: str, recommendation_id: str
) -> Optional[Tuple[List[str], str, dict[str, Any]]]:
    """
    Returns (place_ids_suggested, summary_for_llm, intent_dict) if the row exists
    and belongs to this user. Used for refinement / exclusion on follow-up turns.
    """
    ev = session.get(RecommendationEvent, recommendation_id)
    if not ev or ev.user_id != user_id:
        return None
    ids: List[str] = []
    if ev.primary_place_id:
        ids.append(ev.primary_place_id)
    try:
        backups = json.loads(ev.backup_place_ids or "[]")
        if isinstance(backups, list):
            for pid in backups:
                if pid:
                    ids.append(str(pid))
    except json.JSONDecodeError:
        pass
    try:
        intent_d = json.loads(ev.intent_json or "{}")
    except json.JSONDecodeError:
        intent_d = {}
    summary = (
        f'Earlier user message: "{ev.query_text[:400]}". '
        f"Parsed intent snapshot: {json.dumps(intent_d, ensure_ascii=False)[:600]}"
    )
    return ids, summary, intent_d


def recently_recommended_place_ids(
    session: Session, user_id: str, max_events: int = 15
) -> set[str]:
    """Place IDs from recent recommendation rows (primary + backups), for de-dupe / rotation."""
    stmt = (
        select(RecommendationEvent)
        .where(RecommendationEvent.user_id == user_id)
        .order_by(RecommendationEvent.created_at.desc())
        .limit(max_events)
    )
    rows = session.exec(stmt).all()
    out: set[str] = set()
    for ev in rows:
        if ev.primary_place_id:
            out.add(ev.primary_place_id)
        try:
            backups = json.loads(ev.backup_place_ids or "[]")
            if isinstance(backups, list):
                for pid in backups:
                    if pid:
                        out.add(str(pid))
        except json.JSONDecodeError:
            continue
    return out


def recent_feedback_pairs(session: Session, user_id: str, limit: int = 40) -> list[tuple[str, str]]:
    stmt = (
        select(FeedbackEvent)
        .where(FeedbackEvent.user_id == user_id)
        .order_by(FeedbackEvent.created_at.desc())
        .limit(limit)
    )
    rows = session.exec(stmt).all()
    return [(f.place_id, f.action) for f in rows]


def record_recommendation(
    session: Session,
    user_id: str,
    query_text: str,
    intent_dict: dict[str, Any],
    primary_id: Optional[str],
    backup_ids: list[str],
    scores: dict[str, Any],
    venues_snapshot: Optional[list[dict[str, str]]] = None,
) -> str:
    rid = str(uuid.uuid4())
    snap = venues_snapshot or []
    ev = RecommendationEvent(
        id=rid,
        user_id=user_id,
        query_text=query_text,
        intent_json=json.dumps(intent_dict),
        primary_place_id=primary_id,
        backup_place_ids=json.dumps(backup_ids),
        scores_json=json.dumps(scores),
        venues_snapshot_json=json.dumps(snap),
    )
    session.add(ev)
    session.commit()
    return rid


def get_venues_snapshot(session: Session, user_id: str, recommendation_id: str) -> list[dict[str, str]]:
    ev = session.get(RecommendationEvent, recommendation_id)
    if not ev or ev.user_id != user_id:
        return []
    raw = getattr(ev, "venues_snapshot_json", None) or "[]"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict) and x.get("place_id") and x.get("name")]


def get_pending_automation(session: Session, user_id: str) -> Optional[PendingAutomation]:
    stmt = select(PendingAutomation).where(PendingAutomation.user_id == user_id)
    rows = list(session.exec(stmt).all())
    if not rows:
        return None
    return max(rows, key=lambda p: p.created_at)


def clear_pending_automation(session: Session, user_id: str) -> None:
    rows = list(session.exec(select(PendingAutomation).where(PendingAutomation.user_id == user_id)))
    for p in rows:
        session.delete(p)
    if rows:
        session.commit()


def save_pending_automation(
    session: Session,
    user_id: str,
    recommendation_id: Optional[str],
    phase: str,
    action_kind: str,
    confirmation_prompt: str,
    payload: dict[str, Any],
) -> str:
    clear_pending_automation(session, user_id)
    pid = str(uuid.uuid4())
    pa = PendingAutomation(
        id=pid,
        user_id=user_id,
        recommendation_id=recommendation_id,
        phase=phase,
        action_kind=action_kind,
        confirmation_prompt=confirmation_prompt,
        payload_json=json.dumps(payload),
    )
    session.add(pa)
    session.commit()
    return pid


def apply_feedback_nudge(profile: UserProfile, reason_tags: list[str]) -> None:
    try:
        w = json.loads(profile.personalization_weights or "{}")
    except json.JSONDecodeError:
        w = {}
    tags = {t.lower() for t in reason_tags}
    if "too_far" in tags or "distance" in tags:
        w["distance"] = float(w.get("distance", 0)) + 0.03
    if "too_expensive" in tags or "price" in tags:
        w["price"] = float(w.get("price", 0)) + 0.03
    if "not_my_cuisine" in tags or "cuisine" in tags:
        w["cuisine"] = float(w.get("cuisine", 0)) + 0.02
    if "too_heavy" in tags or "too_greasy" in tags or "fried" in tags:
        w["diet_health"] = float(w.get("diet_health", 0)) + 0.04
    if "great_vegan" in tags or "vegan_friendly" in tags:
        w["diet_health"] = float(w.get("diet_health", 0)) + 0.03
    # clamp contributions
    for k in list(w.keys()):
        w[k] = max(-0.08, min(0.08, float(w[k])))
    profile.personalization_weights = json.dumps(w)
    profile.updated_at = datetime.utcnow()


def add_feedback(
    session: Session,
    user_id: str,
    place_id: str,
    action: str,
    reason_tags: list[str],
    free_text: Optional[str],
    recommendation_id: Optional[str],
) -> None:
    fb = FeedbackEvent(
        user_id=user_id,
        recommendation_id=recommendation_id,
        place_id=place_id,
        action=action,
        reason_tags=json.dumps(reason_tags),
        free_text=free_text,
    )
    session.add(fb)
    p = get_or_create_profile(session, user_id)
    if action == "rejected" and reason_tags:
        apply_feedback_nudge(p, reason_tags)
    session.add(p)
    session.commit()
