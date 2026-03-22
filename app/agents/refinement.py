"""
Follow-up turns: user didn't like last picks, wants alternatives, or is answering a detail question.
Uses an LLM plan + light heuristics; merges intent updates and drives search exclusions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.agents.intent import detect_cuisine_from_message, user_message_signals_spicy_food
from app.agents.visit_category import category_keyword_prefix, normalize_visit_category
from app.integrations.llm import refine_turn_llm
from app.models.domain import ClarificationChip, ClarificationChipGroup, UserIntent


@dataclass
class RefinementPlan:
    needs_more_detail: bool
    ask_user_message: Optional[str]
    exclude_previous_recommendations: bool
    intent_updates: Dict[str, Any]
    extra_search_text: Optional[str]
    preference_notes: Optional[str]
    clarification_chip_groups: Optional[List[Dict[str, Any]]] = None


DEFAULT_REFINEMENT_CHIP_GROUPS: List[Dict[str, Any]] = [
    {
        "title": "Spice",
        "chips": [
            {"label": "Indian heat", "value": "Indian-style spicy"},
            {"label": "Thai chili", "value": "Thai chili heat"},
            {"label": "Sichuan / mala", "value": "Sichuan mala numbing-spicy"},
            {"label": "Mexican salsas", "value": "Mexican spicy salsas"},
            {"label": "Korean gochujang", "value": "Korean gochujang spicy"},
            {"label": "Mild only", "value": "mild spice only"},
        ],
    },
    {
        "title": "Flavor balance",
        "chips": [
            {"label": "More heat", "value": "spicier chili-forward dishes"},
            {"label": "Sweeter", "value": "sweeter coconut mango or caramel notes"},
            {"label": "Sour / tangy", "value": "sour tangy citrus tamarind or pickles"},
            {"label": "Juicy / soupy", "value": "juicy broths noodles or dumplings"},
        ],
    },
    {
        "title": "Price or distance",
        "chips": [
            {"label": "Cheaper", "value": "cheaper options"},
            {"label": "Splurge OK", "value": "okay to splurge"},
            {"label": "Closer", "value": "closer to me"},
            {"label": "Under ~$25", "value": "under $25 per person"},
        ],
    },
    {
        "title": "Vibe",
        "chips": [
            {"label": "Quieter", "value": "quieter spot"},
            {"label": "Livelier", "value": "livelier atmosphere"},
            {"label": "Date night", "value": "date-night vibe"},
            {"label": "Kid-friendly", "value": "kid-friendly"},
            {"label": "Casual", "value": "casual"},
        ],
    },
    {
        "title": "Diet",
        "chips": [
            {"label": "Vegetarian", "value": "vegetarian"},
            {"label": "Vegan", "value": "vegan"},
            {"label": "Halal", "value": "halal"},
            {"label": "Gluten-free", "value": "gluten-free"},
            {"label": "Nut allergy", "value": "nut allergy—nut-free options"},
        ],
    },
]


def normalize_clarification_chip_groups(
    raw: Optional[List[Any]],
) -> List[ClarificationChipGroup]:
    if not raw:
        return []
    out: List[ClarificationChipGroup] = []
    for g in raw:
        if isinstance(g, ClarificationChipGroup):
            if g.title and g.chips:
                out.append(g)
            continue
        if not isinstance(g, dict):
            continue
        title = str(g.get("title") or "").strip()
        chips_raw = g.get("chips") or g.get("options") or []
        chips: List[ClarificationChip] = []
        for c in chips_raw if isinstance(chips_raw, list) else []:
            if isinstance(c, ClarificationChip):
                chips.append(c)
                continue
            if not isinstance(c, dict):
                continue
            lb = str(c.get("label") or "").strip()
            val = str(c.get("value") or lb).strip()
            if lb:
                chips.append(ClarificationChip(label=lb, value=val))
        if title and chips:
            exclusive = bool(g.get("exclusive", False))
            immediate_submit = bool(g.get("immediate_submit", False))
            tod_raw = g.get("time_options_by_date")
            tod_parsed: Optional[Dict[str, List[ClarificationChip]]] = None
            if isinstance(tod_raw, dict):
                tod_parsed = {}
                for dk, arr in tod_raw.items():
                    if not isinstance(arr, list):
                        continue
                    dkey = str(dk).strip()
                    row: List[ClarificationChip] = []
                    for c in arr:
                        if isinstance(c, ClarificationChip):
                            row.append(c)
                        elif isinstance(c, dict):
                            lb = str(c.get("label") or "").strip()
                            val = str(c.get("value") or lb).strip()
                            if lb:
                                row.append(ClarificationChip(label=lb, value=val))
                    if dkey and row:
                        tod_parsed[dkey] = row
                if not tod_parsed:
                    tod_parsed = None
            out.append(
                ClarificationChipGroup(
                    title=title,
                    chips=chips,
                    exclusive=exclusive,
                    time_options_by_date=tod_parsed,
                    immediate_submit=immediate_submit,
                )
            )
    return out


def _parse_clarification_groups_llm(raw: Any) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(raw, list) or not raw:
        return None
    parsed: List[Dict[str, Any]] = []
    for g in raw:
        if not isinstance(g, dict):
            continue
        title = str(g.get("title") or "").strip()
        opts = g.get("chips") or g.get("options") or []
        chips: List[Dict[str, str]] = []
        for o in opts if isinstance(opts, list) else []:
            if not isinstance(o, dict):
                continue
            lb = str(o.get("label") or "").strip()
            val = str(o.get("value") or lb).strip()
            if lb:
                chips.append({"label": lb, "value": val})
        if title and chips:
            parsed.append({"title": title, "chips": chips})
    return parsed or None


def _heuristic_plan(message: str, has_previous: bool) -> Optional[RefinementPlan]:
    if not has_previous:
        return None
    low = message.lower().strip()
    dissatisfaction = (
        "don't like",
        "didn't like",
        "dont like",
        "not those",
        "not that",
        "something else",
        "other options",
        "more options",
        "other suggestions",
        "different",
        "try again",
        "anything else",
        "none of those",
        "skip",
        "pass on",
        "nah",
        "no thanks",
        "not feeling",
        "hate those",
    )
    if not any(p in low for p in dissatisfaction):
        return None

    # User already steered — skip clarifying question.
    steer_markers = (
        "cheap",
        "cheaper",
        "budget",
        "closer",
        "nearer",
        "walking",
        "quiet",
        "loud",
        "vegetarian",
        "vegan",
        "halal",
        "kosher",
        "gluten",
        "italian",
        "thai",
        "indian",
        "mexican",
        "chinese",
        "korean",
        "japanese",
        "vietnamese",
        "sichuan",
        "szechuan",
        "caribbean",
        "ethiopian",
        "mediterranean",
        "french",
        "seafood",
        "bbq",
        "barbecue",
        "spicy",
        "mild",
        "date",
        "romantic",
        "family",
        "fancy",
        "casual",
        "fast",
        "delivery",
        "dine in",
    )
    if any(m in low for m in steer_markers):
        return RefinementPlan(
            needs_more_detail=False,
            ask_user_message=None,
            exclude_previous_recommendations=True,
            intent_updates={},
            extra_search_text=None,
            preference_notes=None,
            clarification_chip_groups=None,
        )

    return RefinementPlan(
        needs_more_detail=True,
        ask_user_message=(
            "No problem. What should we change? Tap any options below (you can pick several), "
            "then send—or type your own in the box."
        ),
        exclude_previous_recommendations=False,
        intent_updates={},
        extra_search_text=None,
        preference_notes=None,
        clarification_chip_groups=list(DEFAULT_REFINEMENT_CHIP_GROUPS),
    )


def _plan_from_llm_dict(data: Dict[str, Any]) -> RefinementPlan:
    iu = data.get("intent_updates")
    if not isinstance(iu, dict):
        iu = {}
    msg = data.get("ask_user_message") or data.get("ask_user")
    if msg is not None:
        msg = str(msg).strip() or None
    cg = _parse_clarification_groups_llm(
        data.get("clarification_groups") or data.get("clarification_chip_groups")
    )
    return RefinementPlan(
        needs_more_detail=bool(data.get("needs_more_detail")),
        ask_user_message=msg,
        exclude_previous_recommendations=bool(data.get("exclude_previous_recommendations")),
        intent_updates=iu,
        extra_search_text=(str(data["extra_search_text"]).strip() if data.get("extra_search_text") else None),
        preference_notes=(
            str(data["preference_notes"]).strip() if data.get("preference_notes") else None
        ),
        clarification_chip_groups=cg,
    )


async def plan_refinement_turn(
    message: str,
    previous_turn_summary: Optional[str],
    profile_hint: str,
) -> RefinementPlan:
    empty = RefinementPlan(
        needs_more_detail=False,
        ask_user_message=None,
        exclude_previous_recommendations=False,
        intent_updates={},
        extra_search_text=None,
        preference_notes=None,
        clarification_chip_groups=None,
    )
    if not (previous_turn_summary or "").strip():
        return empty

    raw = await refine_turn_llm(message, previous_turn_summary.strip(), profile_hint)
    if raw:
        plan = _plan_from_llm_dict(raw)
        if plan.needs_more_detail and plan.ask_user_message:
            return plan
        if not plan.needs_more_detail:
            return plan
        # needs_more_detail but empty message — fall through to heuristic
    h = _heuristic_plan(message, True)
    if h:
        return h
    return empty


_ALLOWED_INTENT_KEYS = frozenset(
    {
        "cuisine",
        "mood",
        "budget",
        "dietary",
        "disliked_ingredients",
        "urgency",
        "mode",
        "party_size",
        "dietary_style",
        "health_goals",
        "meal_intent",
        "dish_preferences",
        "spice_tolerance",
        "visit_category",
    }
)


def apply_refinement_to_intent(
    intent: UserIntent,
    updates: Dict[str, Any],
    preference_notes: Optional[str],
    original_message: str,
) -> UserIntent:
    d = intent.model_dump()
    for k, v in updates.items():
        if k not in _ALLOWED_INTENT_KEYS or v is None:
            continue
        if k in ("dietary", "disliked_ingredients", "health_goals", "dish_preferences") and isinstance(
            v, list
        ):
            d[k] = [str(x) for x in v]
        elif k == "party_size":
            try:
                d[k] = int(v) if v is not None else None
            except (TypeError, ValueError):
                continue
        elif k == "budget" and v in ("low", "medium", "high", "any"):
            d[k] = v
        elif k == "urgency":
            if v in ("now", "soon", "flexible"):
                d[k] = v
            # Ignore bad LLM values (e.g. "tonight 9 pm" conflated with reservation time chips).
        elif k == "mode" and v in ("dine_in", "delivery", "pickup", "either"):
            d[k] = v
        elif k in ("cuisine", "mood"):
            d[k] = str(v) if v else None
        elif k == "dietary_style" and v in ("vegetarian", "vegan", "pescatarian", "omnivore", "any"):
            d[k] = v
        elif k == "meal_intent" and v in ("quick", "relaxed", "indulgent", "healthy", "any"):
            d[k] = v
        elif k == "spice_tolerance" and v in ("mild", "medium", "hot", "any"):
            d[k] = v
        elif k == "visit_category":
            d[k] = normalize_visit_category(v)
        else:
            d[k] = v

    notes = (preference_notes or "").strip()
    if notes:
        d["raw_text"] = f"{original_message.strip()}\nRefined preferences: {notes}"
    else:
        d["raw_text"] = original_message.strip()

    return UserIntent.model_validate(d)


def build_keyword(
    intent: UserIntent,
    extra_search_text: Optional[str],
    user_message: str = "",
) -> Optional[str]:
    """
    Places text search. If the user named a cuisine in the message but did not say vegan/vegetarian
    there, omit profile-only diet tokens so we don't drown Mediterranean (etc.) in vegan-only hits.
    """
    parts: List[str] = []
    if extra_search_text and extra_search_text.strip():
        parts.append(extra_search_text.strip())
    if intent.cuisine:
        parts.append(intent.cuisine.strip())
        if intent.cuisine.strip().lower() == "mediterranean":
            parts.append("Greek Lebanese falafel Mediterranean food")

    joined_so_far = " ".join(parts).lower()
    for dp in intent.dish_preferences:
        t = (dp or "").strip()
        if t and t.lower() not in joined_so_far:
            parts.append(t)
            joined_so_far = " ".join(parts).lower()

    msg = (user_message or "").strip()
    low_msg = msg.lower()
    bk = re.search(r"\b(pancakes?|waffles?|french\s+toast|crepes?)\b", msg, re.I)
    if bk:
        anchor = "breakfast brunch diner " + bk.group(1).lower()
        blob = " ".join(parts).lower()
        if anchor.lower() not in blob and "pancake" not in blob and "waffle" not in blob:
            parts.append(anchor)

    plant_in_msg = bool(re.search(r"\b(vegan|vegetarian|plant[- ]based)\b", low_msg))
    msg_names_cuisine = detect_cuisine_from_message(msg) is not None
    skip_diet_kw = bool(msg_names_cuisine and not plant_in_msg)

    if not skip_diet_kw:
        for tag in intent.dietary[:2]:
            if tag and tag.lower() not in " ".join(parts).lower():
                parts.append(tag)
        if intent.dietary_style == "vegan":
            parts.append("vegan")
        elif intent.dietary_style == "vegetarian":
            parts.append("vegetarian")
        elif intent.dietary_style == "pescatarian":
            parts.append("seafood")
    if (
        user_message_signals_spicy_food(user_message)
        and not intent.cuisine
        and detect_cuisine_from_message(user_message) is None
    ):
        parts.append(
            "Thai Indian Korean Sichuan Mexican spicy chili curry vegan vegetarian plant-based"
        )

    if (
        intent.mood
        and "romantic" in (intent.mood or "").lower()
        and not intent.cuisine
        and detect_cuisine_from_message(user_message) is None
    ):
        parts.append("romantic dinner date night intimate wine upscale vegan vegetarian")

    vc = normalize_visit_category(intent.visit_category)
    extra = category_keyword_prefix(vc)
    if extra and extra.lower() not in " ".join(parts).lower():
        parts.append(extra)

    q = " ".join(parts).strip()
    return q if q else None
