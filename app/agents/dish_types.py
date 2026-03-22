"""Shared dish-intent types (no imports from dish_intent / dish_knowledge)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class DishRequest:
    """A specific dish/drink/dessert the user asked for."""

    slug: str
    display_name: str
    evidence_terms: Tuple[str, ...]
    cuisine_markers: Tuple[str, ...]
    conflicting_types_if_no_evidence: Tuple[str, ...]
    search_boost: str
    relaxed_evidence_terms: Tuple[str, ...] = ()
    cuisine_labels: Tuple[str, ...] = ()
    typical_ingredients: Tuple[str, ...] = ()
    common_variations: Tuple[str, ...] = ()
    dietary_note: str = ""
    primary_cuisine: Optional[str] = None
