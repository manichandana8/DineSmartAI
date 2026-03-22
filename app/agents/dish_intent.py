"""
Dish-level intent: map user phrases to expected cuisines, require menu/review/cuisine evidence,
and avoid naive single-token matches (e.g. \"chicken\" alone for biryani).
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

from app.agents.dish_knowledge import load_dish_pattern_specs
from app.agents.dish_types import DishRequest
from app.models.domain import RestaurantCandidate, UserIntent



def _hay_cuisine(r: RestaurantCandidate) -> str:
    tags = " ".join(r.cuisine_tags or [])
    types = " ".join((t or "").replace("_", " ") for t in (r.types or []))
    return f"{tags} {types} {(r.name or '')} {(r.editorial_summary or '')}".lower()


def _hay_evidence(r: RestaurantCandidate) -> str:
    menu = " ".join((m.name or "") + " " + (m.description or "") for m in (r.menu_items or []))
    rev = " ".join(r.review_snippets or [])
    ed = r.editorial_summary or ""
    nm = r.name or ""
    return f"{menu} {rev} {ed} {nm}".lower()


def _has_any_term(hay: str, terms: Sequence[str]) -> bool:
    return any(t.lower() in hay for t in terms if t)


def cuisine_aligned_with_dish(r: RestaurantCandidate, dish: DishRequest) -> bool:
    h = _hay_cuisine(r)
    return _has_any_term(h, dish.cuisine_markers)


def dish_evidence_strict(r: RestaurantCandidate, dish: DishRequest) -> bool:
    ev = _hay_evidence(r)
    return _has_any_term(ev, dish.evidence_terms)


def dish_evidence_relaxed(r: RestaurantCandidate, dish: DishRequest) -> bool:
    ev = _hay_evidence(r)
    if dish_evidence_strict(r, dish):
        return True
    if dish.relaxed_evidence_terms and _has_any_term(ev, dish.relaxed_evidence_terms):
        return True
    return False


def contradicted_by_primary_type(r: RestaurantCandidate, dish: DishRequest) -> bool:
    """e.g. Mexican taqueria with no ramen on menu → ramen request fails."""
    types_l = " ".join(r.types or []).lower()
    if dish_evidence_strict(r, dish):
        return False
    for ct in dish.conflicting_types_if_no_evidence:
        if ct.lower() in types_l:
            return True
    return False


def passes_strict_dish_gate(r: RestaurantCandidate, dish: DishRequest) -> bool:
    if not cuisine_aligned_with_dish(r, dish):
        return False
    if not dish_evidence_strict(r, dish):
        return False
    if contradicted_by_primary_type(r, dish):
        return False
    return True


def passes_relaxed_dish_gate(r: RestaurantCandidate, dish: DishRequest) -> bool:
    if not cuisine_aligned_with_dish(r, dish):
        return False
    if not dish_evidence_relaxed(r, dish):
        return False
    if contradicted_by_primary_type(r, dish):
        return False
    return True


def dish_evidence_tier(r: RestaurantCandidate, dish: DishRequest) -> int:
    """3 = menu hit, 2 = reviews only, 1 = name/editorial only, 0 = none."""
    menu = " ".join((m.name or "") + " " + (m.description or "") for m in (r.menu_items or [])).lower()
    rev = " ".join(r.review_snippets or []).lower()
    mild = f"{(r.editorial_summary or '').lower()} {(r.name or '').lower()}"
    terms = [t.lower() for t in dish.evidence_terms]
    for t in terms:
        if t and t in menu:
            return 3
    for t in terms:
        if t and t in rev:
            return 2
    for t in terms:
        if t and t in mild:
            return 1
    if dish.relaxed_evidence_terms:
        for t in dish.relaxed_evidence_terms:
            tl = t.lower()
            if tl and (tl in menu or tl in rev or tl in mild):
                return 1
    return 0


def dish_fit_score(r: RestaurantCandidate, dish: DishRequest) -> float:
    """0..1 for ranking — menu > reviews > name/editorial > cuisine-only (should be rare after filter)."""
    tier = dish_evidence_tier(r, dish)
    if tier >= 3:
        return 1.0
    if tier == 2:
        return 0.88
    if tier == 1:
        return 0.72
    if cuisine_aligned_with_dish(r, dish):
        return 0.35
    return 0.1


_SPECS: List[Tuple[re.Pattern[str], DishRequest]] = load_dish_pattern_specs()


def detect_dish_request(message: str, intent: UserIntent) -> Optional[DishRequest]:
    """Return the most specific dish request implied by the user message."""
    msg = (message or "").strip()
    if not msg:
        return None
    for rx, spec in _SPECS:
        if rx.search(msg):
            return spec
    return None


def dish_ambiguous_clarification(message: str, dish: Optional[DishRequest]) -> Optional[str]:
    """Short question only when the dish mention is underspecified."""
    if not dish or dish.slug != "biryani":
        return None
    low = (message or "").lower()
    if re.search(r"\b(chicken|lamb|goat|veg|vegetable|hyderabadi|pakistani|dum)\b", low):
        return None
    if len(low.split()) > 14:
        return None
    return (
        "For biryani: chicken, lamb, veg, or Hyderabadi/Pakistani-style? "
        "Also dine-in, pickup, or delivery? (Reply in one message and I’ll search.)"
    )


def apply_dish_cuisine_hint(intent: UserIntent, dish: Optional[DishRequest]) -> None:
    """Bias cuisine_match when the user named a dish but the LLM left cuisine empty."""
    if not dish or intent.cuisine:
        return
    if dish.primary_cuisine:
        intent.cuisine = dish.primary_cuisine
    elif dish.cuisine_labels:
        intent.cuisine = dish.cuisine_labels[0]


def filter_candidates_for_dish(
    candidates: List[RestaurantCandidate],
    dish: DishRequest,
) -> Tuple[List[RestaurantCandidate], bool]:
    """
    Returns (pool, used_relaxed_fallback).
    Prefer strict evidence matches; if none, use relaxed same-cuisine partial matches.
    """
    strict = [c for c in candidates if passes_strict_dish_gate(c, dish)]
    if strict:
        return strict, False
    relaxed = [c for c in candidates if passes_relaxed_dish_gate(c, dish)]
    return relaxed, bool(relaxed)
