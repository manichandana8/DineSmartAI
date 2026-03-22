from __future__ import annotations

import math
import re
from typing import Optional

from app.agents.dish_intent import dish_fit_score
from app.agents.dish_types import DishRequest
from app.agents.visit_category import normalize_visit_category, ranking_weight_deltas
from app.models.domain import RestaurantCandidate, ScoreBreakdown, UserIntent


def _norm_rating(rating: Optional[float], review_count: int) -> float:
    if rating is None:
        return 0.45
    base = min(1.0, max(0.0, rating / 5.0))
    conf = min(1.0, math.log10(review_count + 10) / 3.0)
    return 0.6 * base + 0.4 * base * conf


def _distance_score(distance_m: float, d0: float) -> float:
    return math.exp(-distance_m / max(d0, 100.0))


def _price_fit(price_level: Optional[int], budget: str) -> float:
    if price_level is None:
        return 0.65
    # Google: 0 free, 1-4 inexpensive to very expensive
    tier = min(4, max(0, int(price_level)))
    want = {"low": 1, "medium": 2, "high": 4, "any": 2}.get(budget, 2)
    diff = abs(tier - want)
    return max(0.0, 1.0 - 0.28 * diff)


def _text_hay(r: RestaurantCandidate) -> str:
    parts = [
        r.name,
        " ".join(r.cuisine_tags),
        " ".join(r.types),
        (r.editorial_summary or ""),
        " ".join(r.review_snippets[:3]),
    ]
    return " ".join(parts).lower()


def _cuisine_match(intent: UserIntent, r: RestaurantCandidate) -> float:
    if not intent.cuisine:
        return 0.72
    ic = intent.cuisine.lower()
    hay = _text_hay(r)
    if ic in hay:
        return 1.0
    if ic == "mediterranean":
        for syn in (
            "mediterranean",
            "greek",
            "lebanese",
            "turkish",
            "middle eastern",
            "falafel",
            "shawarma",
            "hummus",
            "moroccan",
            "israeli",
            "persian",
            "gyro",
            "kebab",
            "mezze",
            "tapas",
        ):
            if syn in hay:
                return 0.9
        return 0.32
    for tag in r.cuisine_tags:
        if ic in tag.lower() or tag.lower() in ic:
            return 0.92
    # partial token
    for tok in re.split(r"\W+", ic):
        if len(tok) > 2 and tok in hay:
            return 0.78
    return 0.35


def _full_intent_query(intent: UserIntent) -> str:
    parts = [
        intent.cuisine or "",
        intent.mood or "",
        " ".join(intent.dietary),
        intent.dietary_style if intent.dietary_style != "any" else "",
        " ".join(intent.health_goals),
        intent.meal_intent if intent.meal_intent != "any" else "",
        " ".join(intent.dish_preferences),
        intent.spice_tolerance if intent.spice_tolerance != "any" else "",
        intent.raw_text or "",
    ]
    base = " ".join(p for p in parts if p).lower()
    extras: list[str] = []
    prefs = {d.lower() for d in intent.dish_preferences}
    if "spicy" in prefs or intent.spice_tolerance in ("hot", "medium"):
        extras.append("spicy chili curry heat sichuan szechuan mala thai indian korean mexican gochujang")
    if "sweet" in prefs:
        extras.append("sweet coconut mango dessert caramel tamarind")
    if "sour" in prefs or "tangy" in prefs:
        extras.append("sour tangy tamarind citrus vinegar pickle lime lemon")
    if "juicy" in prefs:
        extras.append("juicy soup broth dumpling bao noodles")
    if "savory" in prefs or "umami" in prefs:
        extras.append("savory umami miso mushroom rich")
    if intent.mood and "romantic" in intent.mood.lower():
        extras.append("romantic date night intimate wine elegant upscale patio quiet")
    if extras:
        return f"{base} {' '.join(extras)}".strip()
    return base


def _flavor_profile_boost(intent: UserIntent, r: RestaurantCandidate) -> float:
    """Nudge scores toward heat-forward or other flavor signals the user named."""
    mult = 1.0
    hay = _text_hay(r) + " " + " ".join(m.name + " " + (m.description or "") for m in r.menu_items).lower()
    prefs = {d.lower() for d in intent.dish_preferences}
    wants_spicy = "spicy" in prefs or intent.spice_tolerance in ("hot", "medium")
    if wants_spicy:
        spicy_kw = (
            "spicy",
            "chili",
            "chilli",
            "chile",
            "curry",
            "sichuan",
            "szechuan",
            "mala",
            "gochujang",
            "kimchi",
            "jerk",
            "hot sauce",
            "sriracha",
            "habanero",
            "cayenne",
            "thai basil",
            "ghost pepper",
        )
        n = sum(1 for w in spicy_kw if w in hay)
        if n >= 3:
            mult *= 1.11
        elif n >= 1:
            mult *= 1.06
    if "sweet" in prefs and any(
        w in hay for w in ("sweet", "coconut", "mango", "caramel", "dessert", "tamarind", "brown sugar")
    ):
        mult *= 1.05
    if ("sour" in prefs or "tangy" in prefs) and any(
        w in hay for w in ("sour", "tangy", "tamarind", "citrus", "vinegar", "pickle", "lime", "lemon")
    ):
        mult *= 1.05
    if "juicy" in prefs and any(w in hay for w in ("juicy", "soup", "broth", "dumpling", "bao", "noodle")):
        mult *= 1.04
    return min(mult, 1.2)


def _menu_relevance(intent: UserIntent, r: RestaurantCandidate) -> float:
    if not r.menu_items:
        return 0.55
    q = _full_intent_query(intent)
    best = 0.0
    for m in r.menu_items:
        blob = (m.name + " " + (m.description or "")).lower()
        score = 0.25
        for tok in re.split(r"\W+", q):
            if len(tok) > 2 and tok in blob:
                score += 0.2
        best = max(best, min(1.0, score))
    return best


def _ambience_match(intent: UserIntent, r: RestaurantCandidate) -> float:
    mood = (intent.mood or "").lower()
    if not mood:
        return 0.6
    hay = " ".join(r.ambience_hints) + " " + _text_hay(r)
    pairs = [
        ("quiet", ["quiet", "intimate", "calm", "peaceful"]),
        (
            "romantic",
            [
                "romantic",
                "date",
                "candle",
                "intimate",
                "wine",
                "wine bar",
                "elegant",
                "upscale",
                "fine dining",
                "chef",
                "tasting",
                "patio",
                "rooftop",
                "sunset",
                "cozy",
            ],
        ),
        ("loud", ["loud", "energetic", "busy", "music", "nightlife", "bar scene"]),
        ("casual", ["casual", "family", "quick", "neighborhood"]),
    ]
    for key, words in pairs:
        if key in mood:
            return 0.88 if any(w in hay for w in words) else 0.42
    return 0.62


def _romantic_mood_boost(intent: UserIntent, r: RestaurantCandidate) -> float:
    if not intent.mood or "romantic" not in intent.mood.lower():
        return 1.0
    hay = " ".join(r.ambience_hints) + " " + _text_hay(r)
    hits = sum(
        1
        for w in (
            "romantic",
            "intimate",
            "candle",
            "wine",
            "elegant",
            "upscale",
            "fine dining",
            "date",
            "quiet",
            "patio",
            "rooftop",
            "chef",
            "tasting",
        )
        if w in hay
    )
    if hits >= 3:
        return 1.1
    if hits >= 1:
        return 1.05
    return 1.0


def _dominant_ambience_bucket(r: RestaurantCandidate) -> str:
    """Coarse vibe label for shortlist diversification (not shown to users)."""
    hay = (" ".join(r.ambience_hints) + " " + _text_hay(r)).lower()
    scored: list[tuple[int, str]] = []
    checks = [
        ("romantic", ("romantic", "date night", "intimate", "candle", "candlelit", "anniversary")),
        ("upscale", ("upscale", "fine dining", "elegant", "tasting", "sommelier", "chef's table", "white table")),
        ("lively", ("lively", "energetic", "nightlife", "dj", "dance", "bar scene", "bustling")),
        ("outdoor", ("patio", "rooftop", "outdoor", "garden", "al fresco", "terrace", "beer garden")),
        ("cozy", ("cozy", "warm", "dim", "fireplace", "booth", "intimate booth")),
        ("casual", ("casual", "neighborhood", "counter", "quick", "café", "cafe")),
    ]
    for label, kws in checks:
        n = sum(1 for k in kws if k in hay)
        if n:
            scored.append((n, label))
    if not scored:
        return "general"
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][1]


def _urgency_score(intent: UserIntent, r: RestaurantCandidate) -> float:
    if intent.urgency == "now":
        d = _distance_score(r.distance_m, 800.0)
        open_bonus = 0.15 if r.open_now else -0.1
        return max(0.0, min(1.0, d + open_bonus))
    if intent.urgency == "soon":
        return 0.55 * _distance_score(r.distance_m, 1800.0) + 0.45 * _norm_rating(r.rating, r.review_count)
    return 0.5 * _distance_score(r.distance_m, 3500.0) + 0.5 * _norm_rating(r.rating, r.review_count)


def _dietary_satisfied(rule: str, hay: str) -> bool:
    """Whether restaurant/menu text plausibly supports this dietary restriction."""
    rl = rule.lower().strip()
    if rl in ("vegetarian", "veggie"):
        return any(x in hay for x in ("vegan", "vegetarian", "veg "))
    if rl == "vegan":
        return "vegan" in hay
    if rl == "halal":
        return "halal" in hay
    if rl in ("kosher", "kosher-style", "kosher style"):
        return any(x in hay for x in ("kosher", "glatt", "cholov", "pareve", "parve"))
    if rl in ("gluten-free", "gluten free", "glutenfree", "celiac", "coeliac"):
        return any(
            x in hay
            for x in (
                "gluten-free",
                "gluten free",
                "gluten friendly",
                "glutenfriendly",
                "gf ",
                " celiac",
                "coeliac",
                "sans gluten",
            )
        )
    if rl in ("dairy-free", "dairy free", "lactose-free", "lactose free"):
        return any(x in hay for x in ("dairy-free", "dairy free", "lactose-free", "lactose free", "non-dairy"))
    if rl in ("nut-free", "nut free", "peanut-free", "tree nut"):
        return any(x in hay for x in ("nut-free", "nut free", "peanut-free", "tree-nut"))
    if rl in ("egg-free", "egg free", "no egg", "without egg"):
        return any(x in hay for x in ("egg-free", "egg free", "no egg", "eggless"))
    if rl in ("pescatarian", "pescetarian"):
        return any(x in hay for x in ("pescatarian", "pescetarian", "seafood", "fish"))
    # Generic: phrase appears in combined text
    return rl in hay


def _dietary_miss_multiplier(rule: str) -> float:
    """Per-failed-rule score multiplier (combined multiplicatively)."""
    rl = rule.lower().strip()
    if rl in ("vegetarian", "veggie"):
        return 0.4
    if rl == "vegan":
        return 0.35
    if rl == "halal":
        return 0.55
    if rl in ("kosher", "kosher-style", "kosher style"):
        return 0.5
    if rl in ("gluten-free", "gluten free", "glutenfree", "celiac", "coeliac"):
        return 0.45
    if rl in ("dairy-free", "dairy free", "lactose-free", "lactose free"):
        return 0.5
    if rl in ("nut-free", "nut free", "peanut-free", "tree nut"):
        return 0.48
    if rl in ("egg-free", "egg free", "no egg", "without egg"):
        return 0.5
    return 0.5


def _dietary_penalty(intent: UserIntent, r: RestaurantCandidate) -> float:
    """Returns multiplier in (0,1]; stacks when several dietary needs are unmet."""
    if not intent.dietary:
        return 1.0
    hay = _text_hay(r) + " " + " ".join(m.name for m in r.menu_items).lower()
    mult = 1.0
    for rule in intent.dietary:
        if _dietary_satisfied(rule, hay):
            continue
        mult *= _dietary_miss_multiplier(rule)
    return max(0.06, mult)


def _review_diet_health_bonus(intent: UserIntent, hay: str) -> float:
    """Boost when reviews mention strong diet labeling (0.85–1.12)."""
    if not hay:
        return 1.0
    mult = 1.0
    pairs = [
        (("vegan", "vegetarian"), ("vegan option", "vegetarian option", "plant-based", "vegan menu")),
        (("gluten-free", "gluten free", "celiac"), ("gluten free", "gluten-free", "gf menu", "celiac")),
        (("halal",), ("halal",)),
        (("kosher",), ("kosher",)),
    ]
    diet_blob = " ".join(intent.dietary).lower() + " " + (intent.dietary_style or "")
    for keys, phrases in pairs:
        if not any(k in diet_blob for k in keys):
            continue
        if any(p in hay for p in phrases):
            mult *= 1.08
    if intent.health_goals and any(
        x in hay for x in ("healthy", "fresh", "grilled", "light", "clean", "nutritious", "salad", "bowl")
    ):
        mult *= 1.05
    return min(1.15, mult)


def _health_goal_fit(intent: UserIntent, r: RestaurantCandidate) -> float:
    """How well text/menu signals match stated health goals (0–1)."""
    if not intent.health_goals and intent.meal_intent != "healthy":
        return 0.72
    hay = _text_hay(r) + " " + " ".join(m.name + " " + (m.description or "") for m in r.menu_items).lower()
    scores: list[float] = []
    goals = {g.lower().replace("-", "_").replace(" ", "_") for g in intent.health_goals}
    if intent.meal_intent == "healthy":
        goals.update({"nutritious", "light_meal", "low_oil"})

    def has_any(*words: str) -> bool:
        return any(w in hay for w in words)

    if "high_protein" in goals:
        scores.append(
            1.0
            if has_any("protein", "chicken", "salmon", "steak", "tofu", "paneer", "fish", "shrimp")
            else 0.45
        )
    if "low_carb" in goals or "keto_friendly" in goals or "keto" in goals:
        good = has_any("keto", "low carb", "cauliflower", "salad", "grilled")
        bad = has_any("pasta", "bread", "rice bowl", "noodle")
        scores.append(0.85 if good and not bad else 0.5)
    if "low_calorie" in goals:
        scores.append(1.0 if has_any("salad", "soup", "grilled", "steamed", "light") else 0.5)
    if "low_oil" in goals:
        scores.append(0.35 if has_any("fried", "deep fried", "tempura", "greasy") else 0.85)
    if "light_meal" in goals or "light" in goals:
        scores.append(1.0 if has_any("salad", "soup", "steamed", "sashimi", "appetizer") else 0.55)
    if not scores:
        return 0.72
    return sum(scores) / len(scores)


def _menu_clarity_multiplier(intent: UserIntent, r: RestaurantCandidate) -> float:
    """Penalize unknown menus when user has strict diet labeling needs."""
    strict = any(
        x in " ".join(intent.dietary).lower()
        for x in ("vegan", "gluten", "halal", "kosher", "nut-free", "dairy-free")
    )
    strict = strict or intent.dietary_style in ("vegan", "vegetarian")
    if not strict:
        return 1.0
    if r.menu_items:
        return 1.0
    return 0.82


def _ingredient_penalty(intent: UserIntent, r: RestaurantCandidate) -> float:
    if not intent.disliked_ingredients:
        return 1.0
    hay = _text_hay(r) + " " + " ".join(m.name for m in r.menu_items).lower()
    for ing in intent.disliked_ingredients:
        if ing.lower() in hay:
            return 0.25
    return 1.0


def default_weights(
    intent: UserIntent,
    dish_request: Optional[DishRequest] = None,
) -> dict[str, float]:
    w = {
        "rating": 0.2,
        "distance": 0.18,
        "price": 0.11,
        "cuisine": 0.16,
        "menu": 0.1,
        "ambience": 0.06,
        "urgency": 0.06,
        "personalization": 0.04,
        "diet_health": 0.09,
        "dish": 0.0,
    }
    if intent.urgency == "now":
        w["distance"] += 0.1
        w["rating"] -= 0.05
    if intent.cuisine:
        w["cuisine"] += 0.05
        w["menu"] += 0.03
        w["distance"] -= 0.04
    # Food constraints are primary: emphasize menu + diet/health fit
    if intent.dietary or intent.dietary_style not in ("any", "omnivore"):
        w["menu"] += 0.05
        w["diet_health"] += 0.06
        w["rating"] -= 0.04
    if intent.health_goals or intent.meal_intent == "healthy":
        w["diet_health"] += 0.05
        w["menu"] += 0.03
        w["rating"] -= 0.03
    if intent.disliked_ingredients:
        w["diet_health"] += 0.03
        w["menu"] += 0.02
        w["rating"] -= 0.02
    if any(d.lower() == "spicy" for d in intent.dish_preferences) or intent.spice_tolerance in (
        "hot",
        "medium",
    ):
        w["menu"] += 0.04
        w["cuisine"] += 0.02
        w["rating"] -= 0.03
    if intent.mood and intent.mood.lower() != "any":
        w["ambience"] += 0.06
        w["rating"] -= 0.03
        if "romantic" in intent.mood.lower():
            w["ambience"] += 0.03
            w["price"] += 0.02
    vc = normalize_visit_category(getattr(intent, "visit_category", None))
    for k, dv in ranking_weight_deltas(vc).items():
        if k in w:
            w[k] += dv
    if getattr(intent, "best_in_area_query", False):
        w["rating"] += 0.08
        w["distance"] -= 0.05
        w["cuisine"] += 0.04
        w["menu"] += 0.02
    if dish_request:
        w["dish"] = 0.2
        w["menu"] += 0.08
        w["cuisine"] += 0.07
        w["rating"] -= 0.06
        w["distance"] -= 0.06
        w["ambience"] -= 0.04
        w["personalization"] -= 0.02
        w["diet_health"] -= 0.03
    s = sum(w.values())
    return {k: v / s for k, v in w.items()}


def apply_personalization_weights(
    base: dict[str, float], pers: dict[str, float]
) -> dict[str, float]:
    out = dict(base)
    for k, v in pers.items():
        if k in out:
            out[k] = max(0.01, out[k] + v)
    if "dish" not in out:
        out["dish"] = 0.0
    s = sum(out.values())
    return {k: v / s for k, v in out.items()}


def score_candidate(
    intent: UserIntent,
    r: RestaurantCandidate,
    personalization: dict[str, float],
    pers_boost: float,
    dish_request: Optional[DishRequest] = None,
) -> tuple[float, ScoreBreakdown]:
    d0 = 900.0 if intent.urgency == "now" else 2200.0
    rating_s = _norm_rating(r.rating, r.review_count)
    dist_s = _distance_score(r.distance_m, d0)
    price_s = _price_fit(r.price_level, intent.budget)
    cuisine_s = _cuisine_match(intent, r)
    menu_s = _menu_relevance(intent, r)
    amb_s = _ambience_match(intent, r)
    urg_s = _urgency_score(intent, r)
    pers_s = max(0.0, min(1.0, 0.65 + 0.35 * pers_boost))

    hay_reviews = _text_hay(r) + " " + " ".join(r.review_snippets).lower()
    diet_health_s = _health_goal_fit(intent, r)
    diet_health_s = max(0.0, min(1.0, diet_health_s * _review_diet_health_bonus(intent, hay_reviews)))

    dish_fit_s = dish_fit_score(r, dish_request) if dish_request else 0.0
    weights = apply_personalization_weights(
        default_weights(intent, dish_request=dish_request), personalization
    )
    wd = weights.get("diet_health", 0.09)
    w_dish = weights.get("dish", 0.0)

    total = (
        weights["rating"] * rating_s
        + weights["distance"] * dist_s
        + weights["price"] * price_s
        + weights["cuisine"] * cuisine_s
        + weights["menu"] * menu_s
        + weights["ambience"] * amb_s
        + weights["urgency"] * urg_s
        + weights["personalization"] * pers_s
        + wd * diet_health_s
        + w_dish * dish_fit_s
    )
    total *= _menu_clarity_multiplier(intent, r)
    total *= _dietary_penalty(intent, r)
    total *= _ingredient_penalty(intent, r)
    total *= _flavor_profile_boost(intent, r)
    total *= _romantic_mood_boost(intent, r)

    breakdown = ScoreBreakdown(
        rating=rating_s,
        distance=dist_s,
        price_fit=price_s,
        cuisine_match=cuisine_s,
        menu_relevance=menu_s,
        ambience=amb_s,
        urgency=urg_s,
        personalization=pers_s,
        diet_health_fit=diet_health_s,
        dish_fit=dish_fit_s,
        total=total,
    )
    return total, breakdown


def rank_restaurants(
    intent: UserIntent,
    candidates: list[RestaurantCandidate],
    personalization: dict[str, float],
    pers_by_place: dict[str, float],
    dish_request: Optional[DishRequest] = None,
) -> list[tuple[RestaurantCandidate, ScoreBreakdown]]:
    scored: list[tuple[RestaurantCandidate, ScoreBreakdown, float]] = []
    for r in candidates:
        boost = pers_by_place.get(r.place_id, 0.75)
        t, b = score_candidate(intent, r, personalization, boost, dish_request=dish_request)
        scored.append((r, b, t))
    scored.sort(key=lambda x: -x[2])
    return [(x[0], x[1]) for x in scored]


def diversify_top(
    ordered: list[tuple[RestaurantCandidate, ScoreBreakdown]],
    limit: int = 3,
    intent: Optional[UserIntent] = None,
) -> list[tuple[RestaurantCandidate, ScoreBreakdown]]:
    if len(ordered) <= limit:
        return ordered
    pool = ordered[: min(len(ordered), 28)]
    picked: list[tuple[RestaurantCandidate, ScoreBreakdown]] = []
    picked_ids: set[str] = set()
    used_tag_sets: list[set[str]] = []
    used_buckets: list[str] = []
    romantic = bool(intent and intent.mood and "romantic" in intent.mood.lower())
    best_area = bool(intent and getattr(intent, "best_in_area_query", False))
    div_weight = 4 if best_area else 2

    while len(picked) < limit:
        best: Optional[tuple[RestaurantCandidate, ScoreBreakdown]] = None
        best_key: Optional[tuple[int, int, float]] = None
        for r, b in pool:
            if r.place_id in picked_ids:
                continue
            cur_tags = set(r.cuisine_tags or [])
            dup_tags = bool(cur_tags) and any(cur_tags == pt for pt in used_tag_sets if pt)
            buck = _dominant_ambience_bucket(r)
            if buck == "general":
                bucket_fresh = used_buckets.count("general") == 0
            else:
                bucket_fresh = buck not in used_buckets
            w_b = (3 if romantic else 2) if bucket_fresh else 0
            w_c = div_weight if not dup_tags else 0
            key = (w_b + w_c, b.total)
            if best_key is None or key > best_key:
                best_key = key
                best = (r, b)
        if not best:
            break
        picked.append(best)
        picked_ids.add(best[0].place_id)
        ct = set(best[0].cuisine_tags or [])
        if ct:
            used_tag_sets.append(ct)
        used_buckets.append(_dominant_ambience_bucket(best[0]))

    if len(picked) < min(limit, len(ordered)):
        for r, b in ordered:
            if r.place_id in picked_ids:
                continue
            picked.append((r, b))
            picked_ids.add(r.place_id)
            if len(picked) >= limit:
                break
    return picked[:limit]
