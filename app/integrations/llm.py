from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from app.agents.dish_knowledge import dish_knowledge_llm_block
from app.agents.dish_types import DishRequest
from app.integrations.chat_completion import chat_complete
from app.agents.visit_category import normalize_visit_category, structured_picks_category_note
from app.models.domain import UserIntent


async def parse_intent_llm(message: str, profile_hint: str) -> Optional[UserIntent]:
    user = (
        f"User message: {message}\n"
        f"Known profile (may be empty): {profile_hint}\n"
        "Extract structured intent. Leave cuisine null unless the user names one "
        "(do not fill cuisine from profile favorites).\n"
        "CRITICAL — saved profile diet: Do NOT set dietary_style to vegan/vegetarian/pescatarian and do NOT put vegan/vegetarian in dietary[] "
        "from profile unless the USER explicitly said those words (or halal/kosher/gluten-free etc.) in THIS message, "
        "or they said 'as usual' / 'my usual diet'. If they ask for ice cream, snacks, romantic dinner, or restaurants without naming a diet, "
        "use dietary_style omnivore or any and leave dietary[] empty unless they stated a restriction in the message.\n"
        "Do NOT copy profile health_goals (e.g. keto_friendly) into this turn unless the user mentions that health goal now.\n"
        "Map common misspellings: meditarrean/mediteranean → cuisine Mediterranean. "
        "If the user names a cuisine (e.g. Mediterranean, Thai), set cuisine even when profile is vegan—"
        "they may want that cuisine style, not only vegan-labeled venues.\n"
        "visit_category: meal | snack | dessert | ice_cream | beverages | coffee | boba | bakery | fast_food | fine_dining. "
        "Use the place type they want (ice cream shop, boba, coffee, bakery, snacks, full restaurant meal, etc.). "
        "meal = sit-down restaurant / cuisine / lunch / dinner. boba = bubble tea. ice_cream = ice cream or gelato.\n"
        "If the user explicitly asks for seafood, fish, sushi, shellfish, or land meat, set dietary_style to "
        "pescatarian (seafood/fish) or omnivore (meat/poultry) for THIS message — do NOT copy profile vegan/vegetarian "
        "when it contradicts what they asked to eat. Omit vegan/vegetarian from dietary[] unless the user states plant-only in this message.\n"
        "Dietary and health are PRIMARY: capture vegetarian, vegan, pescatarian, non-veg/omnivore, gluten-free, dairy-free, egg-free, halal, kosher, "
        "high-protein, low-carb, low-calorie, low-oil, light meal, keto-friendly, healthy eating.\n"
        "Use dietary_style: vegetarian|vegan|pescatarian|omnivore|any. Put restriction labels in dietary (e.g. gluten-free, halal).\n"
        "health_goals: array of slugs e.g. high_protein, low_carb, low_calorie, low_oil, light_meal, keto_friendly, nutritious.\n"
        "meal_intent: quick|relaxed|indulgent|healthy|any. dish_preferences: noodles, rice, pizza, soup, salad, curry, bowl, "
        "plus flavor asks: spicy, sweet, sour, tangy, juicy, savory, umami when the user names them.\n"
        "If they want spicy food / heat / bold spice without naming a cuisine, add dish_preferences ['spicy'] and set "
        "spice_tolerance to medium or hot (not 'any').\n"
        "spice_tolerance: mild|medium|hot|any.\n"
        "mood: short vibe if clear — e.g. romantic, quiet, casual, loud. "
        "For 'romantic dinner', 'date night', anniversary, set mood romantic and usually meal_intent relaxed, mode dine_in.\n"
        "If the user is vague on health ('healthy food') with no specifics, you may set needs_clarification true with ONE short question.\n"
        "Set needs_clarification true only when location+cuisine context is unusable OR one diet/health question is essential.\n"
        "Location: map coordinates come from the client pin. If they name a city or region, still set visit_category and cuisine from what they said; "
        "food type (e.g. boba, ice cream, Italian) outranks vague geography.\n"
        "Specific dishes (chicken biryani, ramen, pho, pad thai, tacos, tiramisu, etc.): set dish_preferences to include a short slug phrase "
        "matching what they asked (e.g. 'biryani', 'ramen') and set cuisine to the most likely cuisine if obvious (Indian for biryani, Japanese for ramen); "
        "do not replace a clear dish ask with unrelated cuisines."
    )
    raw = await chat_complete(
        [
            {
                "role": "system",
                "content": (
                    "You are DineSmartAI intent extraction. Output one JSON object with keys:\n"
                    "cuisine, mood, budget (low|medium|high|any), dietary (string[]), disliked_ingredients (string[]), "
                    "urgency (now|soon|flexible), mode (dine_in|delivery|pickup|either), party_size, "
                    "needs_clarification (boolean), clarifying_question (string|null),\n"
                    "dietary_style (vegetarian|vegan|pescatarian|omnivore|any), health_goals (string[]), "
                    "meal_intent (quick|relaxed|indulgent|healthy|any), dish_preferences (string[]), "
                    "spice_tolerance (mild|medium|hot|any), "
                    "visit_category (meal|snack|dessert|ice_cream|beverages|coffee|boba|bakery|fast_food|fine_dining).\n"
                    "Normalize restrictions to lowercase hyphenated forms where natural (gluten-free, dairy-free).\n"
                    "CAPABILITIES: Never use clarifying_question to refuse phone booking, reservations, or pickup orders. "
                    "DineSmartAI can help users book via an AI phone agent (after they confirm) or self-service links. "
                    "If the user asks to call or reserve, set needs_clarification false unless search context is unusable "
                    "(e.g. no cuisine/food type at all)—do not claim the product cannot make calls."
                ),
            },
            {"role": "user", "content": user},
        ],
        json_mode=True,
        max_output_tokens=900,
    )
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        payload = {
            "cuisine": data.get("cuisine"),
            "mood": data.get("mood"),
            "budget": data.get("budget") or "any",
            "dietary": list(data.get("dietary") or []),
            "disliked_ingredients": list(data.get("disliked_ingredients") or []),
            "urgency": data.get("urgency") or "flexible",
            "mode": data.get("mode") or "either",
            "party_size": data.get("party_size"),
            "needs_clarification": bool(data.get("needs_clarification")),
            "clarifying_question": data.get("clarifying_question"),
            "raw_text": message,
            "dietary_style": data.get("dietary_style") or "any",
            "health_goals": list(data.get("health_goals") or []),
            "meal_intent": data.get("meal_intent") or "any",
            "dish_preferences": list(data.get("dish_preferences") or []),
            "spice_tolerance": data.get("spice_tolerance") or "any",
            "visit_category": normalize_visit_category(data.get("visit_category")),
        }
        return UserIntent.model_validate(payload)
    except Exception:
        return None


async def refine_turn_llm(
    message: str,
    previous_turn_summary: str,
    profile_hint: str,
) -> Optional[Dict[str, Any]]:
    """
    Follow-up after DineSmartAI already suggested venues. Decides if we should ask
    a targeted question or merge updates and search again (excluding prior picks).
    """
    user = (
        f"Latest user message: {message}\n\n"
        f"Context from the immediately previous recommendation turn:\n{previous_turn_summary}\n\n"
        f"Profile hint (may be empty): {profile_hint}\n\n"
        "Decide how to respond. Examples of situations to handle:\n"
        "- User dislikes all suggestions / wants different options → exclude_previous_recommendations true; "
        "if they only say 'something else' with no new constraints, needs_more_detail true and ask one short, "
        "specific question (spice style, cuisine family, budget, distance, vibe, dietary).\n"
        "- **Spicy** vague → ask which lane: Indian, Thai, Sichuan/Mala, Korean, Mexican, Caribbean, etc.\n"
        "- **Too expensive** → intent_updates.budget lower; optional ask confirm price cap.\n"
        "- **Too far** → mood or urgency tweak; ask walkable vs short drive if unclear.\n"
        "- **Too loud / too quiet** → set mood accordingly; exclude_previous true.\n"
        "- **Vegetarian / halal / allergies** → set dietary or disliked_ingredients; exclude_previous true.\n"
        "- **Boring / adventurous** → extra_search_text for a new cuisine or 'unique chef tasting' style terms.\n"
        "- User answers your earlier question with specifics → needs_more_detail false; fill intent_updates "
        "and extra_search_text; exclude_previous_recommendations true so we do not repeat the same three venues.\n"
        "- User changes topic completely (new meal request) → exclude_previous_recommendations false; "
        "intent_updates from the new request.\n"
        "- User switches place type (restaurant → ice cream, boba, coffee, bakery, snacks, etc.) → "
        "set intent_updates.visit_category to the new type (meal|snack|dessert|ice_cream|beverages|coffee|boba|bakery|fast_food|fine_dining); "
        "exclude_previous_recommendations false so a fresh search runs for the new category.\n"
        "- User asks to book, reserve, order, or have the assistant/call the restaurant → needs_more_detail false; "
        "do NOT say DineSmartAI cannot call venues or complete reservations (it can, after picks and explicit confirmation). "
        "Tell them briefly to name the restaurant from the last results or use the Book/order action on a card, "
        "unless they still need search constraints (then ask only for cuisine/mode/etc.).\n"
    )
    raw = await chat_complete(
        [
            {
                "role": "system",
                "content": (
                    "You are DineSmartAI conversation refinement. Output a single JSON object with keys:\n"
                    "needs_more_detail (boolean): true only if you must ask the user something before searching again.\n"
                    "ask_user_message (string or null): 1-3 short sentences, friendly, plain text. "
                    "No markdown **. Prefer short intro only when you also send clarification_groups for tap-to-select chips.\n"
                    "clarification_groups (array or null): when needs_more_detail is true, optional list of "
                    '{"title": string, "chips": [{"label": string, "value": string}]}. '
                    "Each chip is one tappable option; value is the phrase sent back when selected (can match label). "
                    "Use 2-5 groups with 3-8 chips each for things like spice lane, budget/distance, vibe, diet.\n"
                    "exclude_previous_recommendations (boolean): true if last turn's venues should be excluded "
                    "when the user wants alternatives or refines constraints.\n"
                    "intent_updates (object): optional partial intent: cuisine, mood, budget, dietary, "
                    "disliked_ingredients, urgency, mode, party_size, dietary_style, health_goals, meal_intent, "
                    "dish_preferences, spice_tolerance, visit_category (meal|snack|dessert|ice_cream|beverages|coffee|boba|bakery|fast_food|fine_dining). "
                    "Omit keys you are not changing.\n"
                    "extra_search_text (string or null): short phrase to bias Google text search, e.g. "
                    "'Sichuan mala' or 'omakase sushi' or 'halal kebab'.\n"
                    "preference_notes (string or null): free-form notes merged into ranking context "
                    "(heat level, price cap words, vibe).\n"
                    "If needs_more_detail is true, ask_user_message must be non-null and specific. "
                    "Include clarification_groups whenever practical so the UI can show selectable chips.\n"
                    "PRODUCT TRUTH: DineSmartAI supports reservations and pickup/orders via an AI phone agent (Retell) "
                    "after the user confirms details, plus self-service links. NEVER tell the user the product does not "
                    "support calling venues or making reservations—that is false."
                ),
            },
            {"role": "user", "content": user},
        ],
        json_mode=True,
        max_output_tokens=700,
    )
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


async def parse_automation_llm(
    message: str,
    venues: List[Dict[str, str]],
    intent_mode: str,
    party_hint: Optional[int],
) -> Optional[Dict[str, Any]]:
    """
    Detect reserve / order intent and extract structured fields for confirmation flow.
    """
    if not venues:
        return None
    vlines = "\n".join(f"{i}: {v.get('name', '')} (place_id {v.get('place_id', '')})" for i, v in enumerate(venues))
    raw = await chat_complete(
        [
            {
                "role": "system",
                "content": (
                    "You extract dining automation intent. Output one JSON object only:\n"
                    "wants_automation (boolean): user wants to reserve a table OR place/pay an order.\n"
                    "action: reserve_table | place_order\n"
                    "pick_index (int 0..N-1): ONLY when the user clearly refers to list position "
                    "(first/second/third, #2, top pick). If they name a restaurant (e.g. at Ben's, "
                    "ShangriLa), set pick_index to null — the server matches by name.\n"
                    "party (int or null): guest count only if the user explicitly states it in the message; "
                    "otherwise null (do not infer from profile or defaults).\n"
                    "time_phrase (string or null): e.g. 7pm, 19:30.\n"
                    "date_phrase (string or null): calendar day only if user stated it (today, tomorrow, "
                    "Friday, March 21). If they give only a clock time, date_phrase must be null—do not guess.\n"
                    "order_items (string or null): short summary for orders, e.g. dan dan noodles, dumplings.\n"
                    "estimated_total_usd (number or null): only if user gave a total; else null.\n"
                    "missing (string[]): for reserve_table only — list unknown required fields using exactly: "
                    "date, time, party (calendar day required; never infer date from time alone).\n"
                    "execution_preference: agent | self_service | null. Use agent when the user wants DineSmartAI / "
                    "the assistant to handle booking or ordering (e.g. “you do it”, “call and reserve”, "
                    "“use the agent”, “book it for me”, “place the order for me”, “Retell”, "
                    "“handle it yourself”). Use self_service when they only want links or will book online themselves "
                    "(e.g. “just send links”, “I’ll book online”). null means unspecified — server defaults to agent.\n"
                    "If the message is unrelated to booking or paying, wants_automation false.\n"
                    "Never imply the assistant cannot place outbound calls—the server initiates them when configured, after user confirmation."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"User message: {message}\n"
                    f"Intent mode (dine_in/delivery/pickup/either): {intent_mode}\n"
                    f"Party hint (informational only; do not use as party unless user said it): {party_hint}\n"
                    f"Venues (same order as UI):\n{vlines}"
                ),
            },
        ],
        json_mode=True,
        max_output_tokens=400,
    )
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


async def summarize_reviews_llm(
    restaurant_name: str, snippets: List[str], focus: str
) -> str:
    text = "\n".join(f"- {t[:400]}" for t in snippets[:8])
    out = await chat_complete(
        [
            {
                "role": "system",
                "content": "Summarize diner reviews in 2-3 short bullets. Be specific; note caveats. No preamble.",
            },
            {
                "role": "user",
                "content": f"Restaurant: {restaurant_name}\nFocus: {focus}\nReviews:\n{text}",
            },
        ],
        json_mode=False,
        max_output_tokens=200,
    )
    if out:
        return out
    return _fallback_summary(snippets)


def _fallback_summary(snippets: List[str]) -> str:
    if not snippets:
        return "Limited review text available from the data provider."
    return "Review themes: " + "; ".join(snippets[:2])[:280]


async def explain_pick_llm(
    primary_name: str,
    backups: List[str],
    facts: List[str],
) -> Tuple[str, List[str]]:
    backup_str = ", ".join(backups) if backups else "none"
    fact_str = "\n".join(facts)
    raw = await chat_complete(
        [
            {
                "role": "system",
                "content": (
                    "You write concise explanations for a dining assistant. "
                    "Return JSON with keys: primary_why (string), backup_why (array of strings, same length as backups). "
                    "Mention how the pick fits the user's dietary style, restrictions, and health goals when facts include them; "
                    "note menu-label clarity or customization when relevant. Do not claim strict halal/kosher certification without evidence."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Primary: {primary_name}\nBackups: {backup_str}\nFacts:\n{fact_str}\n"
                    "Explain why primary wins vs backups in one short paragraph for primary; "
                    "one sentence per backup."
                ),
            },
        ],
        json_mode=True,
        max_output_tokens=500,
    )
    if not raw:
        primary_why = facts[0] if facts else f"{primary_name} fits your criteria best among nearby options."
        backup_whys = [f"Solid alternative: {b}." for b in backups]
        return primary_why, backup_whys
    try:
        data = json.loads(raw)
        primary_why = str(data.get("primary_why") or "").strip()
        backup_why = list(data.get("backup_why") or [])
        if not primary_why:
            primary_why = facts[0] if facts else f"Top pick: {primary_name}."
        while len(backup_why) < len(backups):
            backup_why.append(f"Good alternative: {backups[len(backup_why)]}.")
        return primary_why, backup_why[: len(backups)]
    except Exception:
        return (
            facts[0] if facts else f"{primary_name} scores best on your blend of distance, ratings, and fit.",
            [f"Alternative: {b}." for b in backups],
        )


def _default_narratives(venue_names: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for name in venue_names:
        out.append(
            {
                "why_fit": (
                    f"{name} is on your shortlist based on distance, ratings, and how well it matches "
                    "your stated preferences compared with the other options."
                ),
                "highlights": [],
                "dish_match_evidence": "",
                "suggested_dish_order": "",
            }
        )
    return out


async def structured_picks_llm(
    intent: UserIntent,
    venue_blocks: List[str],
    venue_names: List[str],
    dish_request: Optional[DishRequest] = None,
    search_context_line: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    One structured narrative per venue (primary + backups): why_fit, highlights, dish fields.
    """
    n = len(venue_blocks)
    if n == 0:
        return []
    if n != len(venue_names):
        return _default_narratives(venue_names)

    mode_line = (
        f"User context — mode: {intent.mode}, urgency: {intent.urgency}, budget: {intent.budget}, "
        f"meal_intent: {intent.meal_intent}, cuisine_ask: {intent.cuisine!r}, mood: {intent.mood!r}."
    )
    diet_line = (
        f"Diet & health — dietary_style: {intent.dietary_style}, restrictions: {intent.dietary}, "
        f"health_goals: {intent.health_goals}, dish_preferences: {intent.dish_preferences}, "
        f"avoid: {intent.disliked_ingredients}, spice: {intent.spice_tolerance}."
    )
    vc = normalize_visit_category(intent.visit_category)
    cat_note = structured_picks_category_note(vc)
    cat_line = (
        f"Visit category: {vc}. {cat_note}"
        if cat_note
        else f"Visit category: {vc} (restaurant / full meal context)."
    )
    joined = "\n\n---\n\n".join(
        f"[Venue index {i}]\n{block}" for i, block in enumerate(venue_blocks)
    )
    dish_line = ""
    if dish_request:
        kb = dish_knowledge_llm_block(dish_request)
        dish_line = (
            f"SPECIFIC DISH REQUEST: “{dish_request.display_name}”. For EVERY pick you must state whether that exact dish "
            "(or an obvious equivalent named on the menu) is supported by the venue facts—menu item names, review snippets, "
            "editorial, or venue name. If evidence is weak, say so honestly. Do NOT claim a match from generic words alone "
            '(e.g. “chicken” without “biryani”, or “dessert” without the named dessert). '
            "why_fit must lead with dish relevance, then other user criteria.\n"
            f"{kb}\n"
        )
    area_line = f"{search_context_line}\n" if search_context_line else ""
    mood_low = (intent.mood or "").lower()
    romantic_extra = ""
    if any(k in mood_low for k in ("romantic", "date", "anniversary")):
        romantic_extra = (
            "\nMOOD PRIORITY: Romantic / date-night dinner. Each why_fit must justify date suitability "
            "(quieter tables, pacing, wine/dessert or coursed dining signals from editorial/reviews/types)—"
            "not generic shortlist boilerplate. If facts suggest loud counter-service or purely utilitarian dining, say that honestly.\n"
        )
    raw = await chat_complete(
        [
            {
                "role": "system",
                "content": (
                    "You are DineSmartAI recommendation copy. Output a single JSON object with key picks: "
                    "an array of exactly N objects (N = number of venues provided), in the SAME ORDER as indices 0..N-1.\n"
                    "Each object MUST include:\n"
                    "- index: integer matching the venue block (0 .. N-1)\n"
                    "- why_fit: string, 2-4 sentences. Tie explicitly to this user's diet, health goals, budget, "
                    "time pressure, cuisine, and dine/delivery/pickup mode. No generic filler alone "
                    '("good place", "popular spot", "great food" are banned unless paired with a concrete user link).\n'
                    "- ambience: one short line (under ~120 chars) for typical vibe. "
                    "Across the shortlist, vary this line when venue facts differ—e.g. upscale vs patio vs lively bar vs cozy neighborhood—"
                    "avoid repeating the same generic phrase for every pick. "
                    "For romantic or date-night requests, lean into intimate, quiet, patio, or refined dining signals from the facts, not a single 'casual' label for all. "
                    "Do NOT paste or quote review text, 'Review themes:', or long first-person snippets; synthesize briefly.\n"
                    "Adapt emphasis: delivery → speed/convenience; dine_in → seating vibe; healthy → lighter options; "
                    "strict dietary tags → what to confirm with staff. "
                    "When the user asked for spicy / bold heat, compare venues for chili- or spice-forward options "
                    "(e.g. Thai, Indian, Sichuan, Korean, Mexican) that still fit their diet. "
                    "Across the shortlist, mention contrast when useful: sweeter coconut or tamarind curries, sour/tangy "
                    "salads or pickles, rich umami broths, or juicy dumplings—so picks are not all one note. "
                    "Do not claim halal/kosher certification without evidence in the facts.\n"
                    "- highlights: string array, 1-3 short bullets for the card (e.g. signature dish, patio, "
                    "late hours). When venue facts include Opening hours, use at least one bullet to tie hours to "
                    "the user’s plan (e.g. dinner window, closed Mondays, open late). "
                    "First bullet should mention the neighborhood or street context from the facts "
                    "when available (e.g. 'Mission-adjacent strip', 'Downtown near transit').\n"
                    "- dish_match_evidence: string, one or two sentences. REQUIRED when a specific dish was requested: "
                    "say explicitly if the dish is on the menu, mentioned in reviews, or only a related item/cuisine fit. "
                    "If there is no honest evidence, say “No explicit menu/review match—same cuisine family only.” "
                    "If no dish request, use an empty string.\n"
                    "- suggested_dish_order: string, optional concrete order line if inferable from menu (e.g. "
                    "'Chicken biryani — ask for spice level'); else empty string."
                ),
            },
            {
                "role": "user",
                "content": f"{mode_line}{romantic_extra}\n{diet_line}\n{cat_line}\n{area_line}{dish_line}\n\nVenue facts:\n{joined}",
            },
        ],
        json_mode=True,
        max_output_tokens=1400,
    )
    if not raw:
        return _default_narratives(venue_names)
    try:
        data = json.loads(raw)
        arr = data.get("picks") if isinstance(data, dict) else None
        if not isinstance(arr, list) or len(arr) != n:
            return _default_narratives(venue_names)
        normalized: List[Optional[Dict[str, Any]]] = [None] * n
        for item in arr:
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            if not isinstance(idx, int) or idx < 0 or idx >= n:
                continue
            why = str(item.get("why_fit") or "").strip()
            if not why:
                why = (
                    f"{venue_names[idx]} fits your search among the shortlist picks given distance, ratings, and your criteria."
                )
            hl_raw = item.get("highlights")
            highlights: List[str] = []
            if isinstance(hl_raw, list):
                highlights = [str(x).strip() for x in hl_raw[:5] if str(x).strip()]
            dme = str(item.get("dish_match_evidence") or "").strip()
            sdo = str(item.get("suggested_dish_order") or "").strip()
            normalized[idx] = {
                "why_fit": why,
                "highlights": highlights,
                "dish_match_evidence": dme,
                "suggested_dish_order": sdo,
            }
        if any(x is None for x in normalized):
            return _default_narratives(venue_names)
        return [x for x in normalized if x is not None]
    except Exception:
        return _default_narratives(venue_names)


async def suggest_dishes_llm(
    restaurant_name: str,
    cuisine: Optional[str],
    menu_items: List[str],
    dietary: List[str],
    spice: str,
    dietary_style: str,
    health_goals: List[str],
    meal_intent: str,
    dish_preferences: List[str],
    disliked_ingredients: List[str],
) -> List[Dict[str, str]]:
    menu = ", ".join(menu_items[:25]) if menu_items else "(no structured menu; infer typical dishes for venue)"
    diet = ", ".join(dietary) if dietary else "none"
    avoid = ", ".join(disliked_ingredients) if disliked_ingredients else "none"
    hg = ", ".join(health_goals) if health_goals else "none"
    dp = ", ".join(dish_preferences) if dish_preferences else "none"
    raw = await chat_complete(
        [
            {
                "role": "system",
                "content": (
                    "Suggest 1-3 dishes to order. JSON object with key items: array of "
                    '{name, why, caution (optional string)}.\n'
                    "PRIMARY RULES: Respect dietary_style, dietary restrictions, disliked_ingredients, and health_goals. "
                    "Never suggest dishes that clearly violate vegan/vegetarian/halal/gluten-free when those apply. "
                    "If uncertain about allergens or strict halal/kosher, set caution telling the user to confirm with the restaurant. "
                    "Prefer grilled/steamed/baked/salads for low-oil, light_meal, low-calorie, healthy. "
                    "Prefer protein-rich dishes for high_protein. Avoid suggesting fried/greasy items when user wants low-oil or healthy."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Restaurant: {restaurant_name}\nCuisine: {cuisine or 'unknown'}\n"
                    f"Menu items or context: {menu}\n"
                    f"Dietary restrictions: {diet}\nDietary style: {dietary_style}\n"
                    f"Health goals: {hg}\nMeal intent: {meal_intent}\n"
                    f"Dish type preferences: {dp}\nAvoid ingredients: {avoid}\nSpice tolerance: {spice}"
                ),
            },
        ],
        json_mode=True,
        max_output_tokens=500,
    )
    if not raw:
        return []
    try:
        data = json.loads(raw)
        items = data.get("items") or []
        out: List[Dict[str, str]] = []
        for it in items[:3]:
            if isinstance(it, dict) and it.get("name"):
                out.append(
                    {
                        "name": str(it["name"]),
                        "why": str(it.get("why") or ""),
                        "caution": str(it.get("caution")) if it.get("caution") else "",
                    }
                )
        return out
    except Exception:
        return []
