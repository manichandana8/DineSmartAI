"""
Load dish → cuisine knowledge base from app/data/dish_knowledge.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.agents.dish_types import DishRequest

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "dish_knowledge.json"
_raw_cache: Optional[Dict[str, Any]] = None
_specs_cache: Optional[List[Tuple[re.Pattern[str], DishRequest]]] = None


def _load_raw() -> Dict[str, Any]:
    global _raw_cache
    if _raw_cache is None:
        with open(_DATA_PATH, encoding="utf-8") as f:
            _raw_cache = json.load(f)
    return _raw_cache


def _conflicts_for_entry(e: Dict[str, Any], presets: Dict[str, List[str]]) -> Tuple[str, ...]:
    key = e.get("conflict_preset")
    if key and key in presets:
        return tuple(presets[key])
    return tuple(e.get("conflicting_types") or ())


def _entry_to_dish_request(e: Dict[str, Any], presets: Dict[str, List[str]]) -> DishRequest:
    cuisines = tuple(e.get("cuisines") or [])
    return DishRequest(
        slug=str(e["slug"]),
        display_name=str(e["display_name"]),
        evidence_terms=tuple(e.get("evidence_terms") or []),
        cuisine_markers=tuple(e.get("cuisine_markers") or []),
        conflicting_types_if_no_evidence=_conflicts_for_entry(e, presets),
        search_boost=str(e.get("search_boost") or "").strip(),
        relaxed_evidence_terms=tuple(e.get("relaxed_evidence_terms") or []),
        cuisine_labels=cuisines,
        typical_ingredients=tuple(e.get("ingredients") or []),
        common_variations=tuple(e.get("variations") or []),
        dietary_note=str(e.get("dietary") or ""),
        primary_cuisine=(str(e["primary_cuisine"]).strip() if e.get("primary_cuisine") else None),
    )


def load_dish_pattern_specs() -> List[Tuple[re.Pattern[str], DishRequest]]:
    """(pattern, DishRequest) pairs, longest regex first for specificity."""
    global _specs_cache
    if _specs_cache is not None:
        return _specs_cache
    data = _load_raw()
    presets: Dict[str, List[str]] = data.get("conflict_presets") or {}
    specs: List[Tuple[re.Pattern[str], DishRequest]] = []
    for e in data.get("entries") or []:
        if not isinstance(e, dict):
            continue
        dr = _entry_to_dish_request(e, presets)
        for p in e.get("patterns") or []:
            if not isinstance(p, str) or not p.strip():
                continue
            specs.append((re.compile(p, re.I), dr))
    specs.sort(key=lambda x: (-len(x[0].pattern), x[1].slug))
    _specs_cache = specs
    return specs


def dish_knowledge_llm_block(dish: DishRequest) -> str:
    """Structured KB snippet for the recommendation LLM."""
    lines = [
        f"Dish KB — {dish.display_name} ({dish.slug})",
        f"Mapped cuisines (search restricted to this family): {', '.join(dish.cuisine_labels) or dish.primary_cuisine or 'see cuisine_markers'}",
    ]
    if dish.typical_ingredients:
        lines.append("Typical ingredients: " + ", ".join(dish.typical_ingredients))
    if dish.common_variations:
        lines.append("Common variations: " + "; ".join(dish.common_variations))
    if dish.dietary_note:
        lines.append("Dietary notes: " + dish.dietary_note)
    lines.append(
        "Only recommend if menu/reviews/listing support this dish; do not infer from single generic tokens."
    )
    return "\n".join(lines)


def reload_dish_knowledge_cache() -> None:
    """For tests / hot reload."""
    global _raw_cache, _specs_cache
    _raw_cache = None
    _specs_cache = None
