from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, Optional

from sqlmodel import Session

from app.agents.intent import (
    apply_message_cuisine,
    apply_message_flavor_preferences,
    apply_message_mood,
    parse_intent,
)
from app.agents.intent_dietary import (
    relax_saved_diet_if_not_explicit_in_message,
    sync_dietary_style_into_dietary,
)
from app.agents.intent_override import apply_explicit_meal_requests
from app.agents.preference_clarify import preference_clarification_question
from app.agents.refinement import (
    apply_refinement_to_intent,
    build_keyword,
    normalize_clarification_chip_groups,
    plan_refinement_turn,
)
from app.agents.next_action import plan_next_actions
from app.agents.personalization import (
    merge_intent_with_profile,
    personalization_vector,
    place_boost_from_feedback,
)
from app.agents.ranking import diversify_top, rank_restaurants
from app.agents.location_scope import (
    apply_location_query_heuristics,
    broad_area_needs_food_clarification,
    broad_location_chip_groups,
    broad_location_prompt,
    location_search_moved_enough_to_reset,
    merge_food_intent_for_location_followup,
    resolve_named_search_area,
)
from app.agents.dish_intent import (
    apply_dish_cuisine_hint,
    detect_dish_request,
    dish_ambiguous_clarification,
    filter_candidates_for_dish,
)
from app.agents.dish_knowledge import dish_knowledge_llm_block
from app.agents.dish_types import DishRequest
from app.agents.visit_category import (
    ensure_visit_category,
    normalize_visit_category,
    should_reset_refinement_context,
    visit_category_clarification_hint,
)
from app.integrations.geocode import geocode_address
from app.integrations.llm import structured_picks_llm
from app.integrations.places import candidate_from_place, enrich_many, nearby_search
from app.models.domain import (
    RankedPick,
    RecommendRequest,
    RecommendResponse,
    RestaurantCandidate,
    ScoreBreakdown,
)
from app.services.location import haversine_m, radius_for_urgency
from app.services.pick_display import (
    cuisine_line,
    dietary_compatibility_line,
    distance_or_time_line,
    format_full_address,
    format_opening_hours_card,
    format_price_display,
    neighborhood_from_address,
)
from app.services.automation import automation_availability_for, try_automation_flow
from app.services.memory import (
    get_or_create_profile,
    get_pending_automation,
    get_recommendation_for_user,
    persist_preferences_from_intent,
    profile_hint_json,
    recent_feedback_pairs,
    recently_recommended_place_ids,
    record_recommendation,
)


def _venue_llm_block(
    r: RestaurantCandidate,
    b: ScoreBreakdown,
    role_instruction: str,
    dish_request: Optional[DishRequest] = None,
) -> str:
    menu = ", ".join(m.name for m in r.menu_items[:10])
    ed = (r.editorial_summary or "")[:240]
    snippets = " | ".join(t[:120] for t in r.review_snippets[:4])
    addr = format_full_address(r.address)
    area = neighborhood_from_address(r.address)
    on_hint = ""
    if r.open_now is True:
        on_hint = "Likely OPEN now (per Google Places).\n"
    elif r.open_now is False:
        on_hint = "Likely CLOSED now (per Google Places).\n"
    oh_block = ""
    if r.opening_hours_lines:
        oh_block = "Opening hours (per Google):\n" + "\n".join(
            f"  • {ln}" for ln in r.opening_hours_lines[:8]
        )
        if len(r.opening_hours_lines) > 8:
            oh_block += "\n  • …"
        oh_block += "\n"
    dish_line = ""
    if dish_request:
        dish_line = (
            f"USER-REQUESTED DISH: {dish_request.display_name} (verify menu/review/cuisine fit).\n"
            f"{dish_knowledge_llm_block(dish_request)}\n"
        )
    return (
        f"{role_instruction}\n"
        f"{dish_line}"
        f"Name: {r.name}\n"
        f"Rating: {r.rating} stars, {r.review_count} reviews\n"
        f"Price level (1-4): {r.price_level}\n"
        f"Distance from user: {int(r.distance_m)} meters\n"
        f"Full address (show to user): {addr}\n"
        f"Area / neighborhood hint: {area or '(not parsed from address)'}\n"
        f"{on_hint}"
        f"{oh_block}"
        f"Cuisine tags: {', '.join(r.cuisine_tags)}\n"
        f"Place types: {', '.join(r.types[:10])}\n"
        f"Editorial: {ed}\n"
        f"Review snippet samples: {snippets}\n"
        f"Menu item names (if any): {menu or '(none in listing)'}\n"
        f"Ranker composite score: {b.total:.3f}"
    )


async def run_recommendation(req: RecommendRequest, session: Session) -> RecommendResponse:
    user_id = req.user_id or "demo"
    profile = get_or_create_profile(session, user_id)
    hint = profile_hint_json(session, user_id)

    prev_place_ids: list[str] = []
    prev_summary: Optional[str] = None
    prev_intent_dict: dict[str, Any] = {}
    if req.previous_recommendation_id:
        row = get_recommendation_for_user(
            session, user_id, req.previous_recommendation_id.strip()
        )
        if row:
            prev_place_ids, prev_summary, prev_intent_dict = row
            if location_search_moved_enough_to_reset(
                prev_intent_dict, req.latitude, req.longitude
            ):
                prev_place_ids = []
                prev_summary = None

    prev_summary_for_plan = prev_summary
    if prev_intent_dict and should_reset_refinement_context(
        prev_intent_dict.get("visit_category"), req.message
    ):
        prev_summary_for_plan = None

    pend = get_pending_automation(session, user_id)
    plan = await plan_refinement_turn(req.message, prev_summary_for_plan, hint)
    if not pend and plan.needs_more_detail and plan.ask_user_message:
        intent = await parse_intent(req.message, hint)
        intent = merge_intent_with_profile(intent, profile)
        intent = apply_explicit_meal_requests(req.message, intent)
        intent = apply_message_cuisine(intent, req.message)
        intent = apply_message_flavor_preferences(intent, req.message)
        intent = apply_message_mood(intent, req.message)
        intent = ensure_visit_category(intent, req.message)
        return RecommendResponse(
            clarification=plan.ask_user_message,
            clarification_chip_groups=normalize_clarification_chip_groups(
                plan.clarification_chip_groups
            ),
            intent=intent,
            recommendation_id=None,
        )

    intent = await parse_intent(req.message, hint)
    intent = apply_refinement_to_intent(
        intent,
        plan.intent_updates,
        plan.preference_notes,
        req.message,
    )
    intent = merge_intent_with_profile(intent, profile)
    intent = apply_explicit_meal_requests(req.message, intent)
    intent = apply_message_cuisine(intent, req.message)
    intent = apply_message_flavor_preferences(intent, req.message)
    intent = apply_message_mood(intent, req.message)
    intent = ensure_visit_category(intent, req.message)
    intent = relax_saved_diet_if_not_explicit_in_message(req.message, intent)
    intent = sync_dietary_style_into_dietary(intent)
    intent = apply_location_query_heuristics(req.message, intent)
    if prev_intent_dict and req.previous_recommendation_id:
        intent = merge_food_intent_for_location_followup(
            prev_intent_dict, intent, req.message
        )

    if prev_intent_dict and normalize_visit_category(
        prev_intent_dict.get("visit_category")
    ) != normalize_visit_category(intent.visit_category):
        prev_place_ids = []
        prev_summary = None

    auto_resp = await try_automation_flow(
        session, user_id, req.message, req.previous_recommendation_id, intent
    )
    if auto_resp is not None:
        return auto_resp

    if intent.needs_clarification and intent.clarifying_question:
        return RecommendResponse(
            clarification=intent.clarifying_question,
            intent=intent,
            recommendation_id=None,
        )

    if broad_area_needs_food_clarification(req.message, intent):
        return RecommendResponse(
            clarification=broad_location_prompt(),
            clarification_chip_groups=normalize_clarification_chip_groups(
                broad_location_chip_groups()
            ),
            intent=intent,
            recommendation_id=None,
        )

    dish_request = detect_dish_request(req.message, intent)
    if dish_request:
        dq = dish_ambiguous_clarification(req.message, dish_request)
        if dq:
            return RecommendResponse(
                clarification=dq,
                intent=intent,
                recommendation_id=None,
            )
        apply_dish_cuisine_hint(intent, dish_request)

    pref_q = preference_clarification_question(intent, req.message, hint)
    if not pref_q:
        pref_q = visit_category_clarification_hint(intent, req.message)
    if pref_q:
        return RecommendResponse(
            clarification=pref_q,
            intent=intent,
            recommendation_id=None,
        )

    radius_m = radius_for_urgency(intent.urgency)
    search_lat = float(req.latitude)
    search_lng = float(req.longitude)
    location_search_note: Optional[str] = None
    search_context_line: Optional[str] = None
    named_area = resolve_named_search_area(req.message)
    if named_area:
        geo = await geocode_address(named_area.geocode_query)
        if geo:
            search_lat, search_lng = geo
            radius_m = max(radius_m, 20_000)
            search_context_line = (
                f"SEARCH AREA: User asked for options in or near {named_area.display_label}. "
                "Distances in venue facts are from the center of that area (the user's map pin may be elsewhere). "
                "Use each venue's formatted address as ground truth; align why_fit and highlights with that city/neighborhood."
            )
            if haversine_m(float(req.latitude), float(req.longitude), search_lat, search_lng) > 3000:
                location_search_note = (
                    f"You asked for {named_area.display_label}; results are centered there—not on your map pin. "
                    "Mile distances are from that area's center."
                )

    keyword = build_keyword(intent, plan.extra_search_text, req.message)
    if dish_request:
        cuisine_tokens = (
            " ".join(dish_request.cuisine_labels[:5]) if dish_request.cuisine_labels else ""
        )
        sb = (dish_request.search_boost or "").strip()
        merged = " ".join(x for x in (cuisine_tokens, sb) if x).strip()
        if merged:
            keyword = f"{keyword} {merged}".strip() if keyword else merged
    raw_places, places_error = await nearby_search(
        search_lat,
        search_lng,
        radius_m,
        keyword,
        max_results=20,
        visit_category=intent.visit_category,
    )
    if not raw_places and keyword and re.search(
        r"\bvegan\b|\bvegetarian\b", keyword, re.I
    ):
        relaxed = re.sub(r"\bvegan\b|\bvegetarian\b", "", keyword, flags=re.I)
        relaxed = " ".join(relaxed.split()).strip()
        if relaxed and relaxed != keyword.strip():
            raw_places, places_error = await nearby_search(
                search_lat,
                search_lng,
                radius_m,
                relaxed,
                max_results=20,
                visit_category=intent.visit_category,
            )
    if places_error:
        return RecommendResponse(
            clarification=places_error,
            intent=intent,
            recommendation_id=None,
        )

    candidates = [
        candidate_from_place(p, search_lat, search_lng) for p in raw_places if p.get("place_id")
    ]

    if not candidates:
        cat_lbl = (intent.visit_category or "meal").replace("_", " ")
        return RecommendResponse(
            clarification=(
                f"No places matched in this area for “{cat_lbl}” with your filters. "
                "Try widening distance, simplifying keywords, or relaxing dietary terms—some categories "
                "(ice cream, boba, etc.) have fewer labeled vegan options nearby. "
                "Confirm Places API is enabled if this keeps happening."
            ),
            intent=intent,
            recommendation_id=None,
        )

    # Pre-sort for enrichment budget
    def prelim(c: RestaurantCandidate) -> float:
        r = c.rating or 4.0
        d = max(c.distance_m, 1.0)
        return r * 1.2 - (d / 5000.0)

    candidates.sort(key=prelim, reverse=True)
    top_for_enrich = candidates[:12]
    enriched = await enrich_many(top_for_enrich, search_lat, search_lng)

    dish_search_note: Optional[str] = None
    pool = enriched
    if dish_request:
        pool, used_relaxed = filter_candidates_for_dish(enriched, dish_request)
        if not pool:
            return RecommendResponse(
                clarification=(
                    f"No nearby venues cleared our dish check for “{dish_request.display_name}”. "
                    "We require the right cuisine family plus the dish (or a clear equivalent) on the menu, "
                    "in reviews, or in the listing—not a generic keyword hit. "
                    "Try moving the map pin, widening the search, or naming a neighborhood with more options."
                ),
                intent=intent,
                recommendation_id=None,
            )
        if used_relaxed:
            dish_search_note = (
                f"We didn’t find a strong exact on-menu match for “{dish_request.display_name}” nearby—these are "
                "the closest same-cuisine picks with partial signals (related dishes or weaker mentions). "
                "Confirm the menu before you head over."
            )

    pers_vec = personalization_vector(profile)
    fb_pairs = recent_feedback_pairs(session, user_id)
    pers_by_place = {
        c.place_id: place_boost_from_feedback(c.place_id, fb_pairs) for c in pool
    }

    ranked = rank_restaurants(
        intent, pool, pers_vec, pers_by_place, dish_request=dish_request
    )
    exclude_prev = set(prev_place_ids) if plan.exclude_previous_recommendations and prev_place_ids else set()
    if exclude_prev:
        filtered = [(r, b) for r, b in ranked if r.place_id not in exclude_prev]
        if len(filtered) >= 3:
            ranked = filtered

    recent_ids = recently_recommended_place_ids(session, user_id)
    if recent_ids:
        # Down-rank venues we already suggested so repeat chats hit fresh Places results.
        adjusted: list[tuple[RestaurantCandidate, ScoreBreakdown, float]] = []
        for r, b in ranked:
            adj = b.total - (0.22 if r.place_id in recent_ids else 0.0)
            adjusted.append((r, b, adj))
        adjusted.sort(key=lambda x: -x[2])
        ranked = [(x[0], x[1]) for x in adjusted]
    top3 = diversify_top(ranked, limit=3, intent=intent)
    if not top3:
        return RecommendResponse(intent=intent, recommendation_id=None)

    primary_r, primary_b = top3[0]
    backups = top3[1:]
    nbs = [neighborhood_from_address(r.address) for r, _ in top3]
    nonempty = [x for x in nbs if x]
    cluster_note = ""
    if len(nonempty) == 3 and len(set(nonempty)) == 1:
        cluster_note = f"Most of these picks are around {nonempty[0]} — a solid pocket to explore for food."
    elif len(nonempty) >= 2 and len(set(nonempty)) == 1:
        cluster_note = f"Several picks cluster near {nonempty[0]}."

    role_lines = [
        "ROLE: BEST PICK — best overall match for this user; justify vs the two backups.",
        "ROLE: BACKUP #1 — same depth as best pick; state tradeoffs vs best pick and vs backup #2.",
        "ROLE: BACKUP #2 — same depth as best pick; state tradeoffs vs best pick and vs backup #1.",
    ]
    venue_blocks = [
        _venue_llm_block(
            r,
            b,
            role_lines[i] if i < len(role_lines) else f"ROLE: BACKUP #{i + 1}",
            dish_request=dish_request,
        )
        for i, (r, b) in enumerate(top3)
    ]
    venue_names = [r.name for r, _ in top3]
    narratives = await structured_picks_llm(
        intent,
        venue_blocks,
        venue_names,
        dish_request=dish_request,
        search_context_line=search_context_line,
    )

    async def build_pick_from_narrative(
        r: RestaurantCandidate,
        b: ScoreBreakdown,
        narr: Dict[str, Any],
    ) -> RankedPick:
        actions = plan_next_actions(intent, r)
        why = str(narr.get("why_fit") or "").strip() or (
            f"{r.name} fits your search among nearby options given distance, ratings, and your criteria."
        )
        hl_raw = narr.get("highlights")
        highlights: list[str] = []
        if isinstance(hl_raw, list):
            highlights = [str(x).strip() for x in hl_raw[:5] if str(x).strip()]
        addr_disp = format_full_address(r.address)
        nbh = neighborhood_from_address(r.address)
        dm = str(narr.get("dish_match_evidence") or "").strip()
        sd = str(narr.get("suggested_dish_order") or "").strip()
        dish_parts = [p for p in (dm, f"Suggested order: {sd}" if sd else "") if p]
        dish_disp = " ".join(dish_parts).strip()
        return RankedPick(
            restaurant=r,
            score_breakdown=b,
            why=why,
            review_summary="",
            suggested_dishes=[],
            next_actions=actions,
            automation=automation_availability_for(r, intent),
            cuisine_display=cuisine_line(r, intent),
            distance_or_time_display=distance_or_time_line(intent, r.distance_m),
            price_display=format_price_display(r.price_level),
            ambience_display="",
            dietary_compatibility=dietary_compatibility_line(intent, r),
            address_display=addr_disp,
            neighborhood_display=nbh,
            location_cluster_note=cluster_note,
            highlights=highlights,
            dish_match_display=dish_disp,
            comparative_note="",
            opening_hours_display=format_opening_hours_card(r),
        )

    picks_out = await asyncio.gather(
        *[
            build_pick_from_narrative(r, b, narr)
            for (r, b), narr in zip(top3, narratives)
        ]
    )
    primary_pick = picks_out[0]
    alt_picks = list(picks_out[1:])

    scores_out: dict[str, Any] = {
        primary_r.place_id: primary_b.model_dump(),
        **{br.place_id: bb.model_dump() for (br, bb) in backups},
    }
    venues_snapshot = []
    for r, _ in top3:
        row: dict[str, str] = {"place_id": r.place_id, "name": r.name}
        if r.types:
            row["types_json"] = json.dumps(list(r.types)[:24])
        if r.opening_hours_lines:
            row["opening_hours_json"] = json.dumps(list(r.opening_hours_lines)[:14])
        venues_snapshot.append(row)
    intent_record = intent.model_dump()
    intent_record["_search_latitude"] = search_lat
    intent_record["_search_longitude"] = search_lng
    rec_id = record_recommendation(
        session,
        user_id,
        req.message,
        intent_record,
        primary_r.place_id,
        [b[0].place_id for b in backups],
        scores_out,
        venues_snapshot=venues_snapshot,
    )
    persist_preferences_from_intent(session, profile, intent)

    return RecommendResponse(
        intent=intent,
        primary=primary_pick,
        alternates=alt_picks,
        comparison=[],
        recommendation_id=rec_id,
        dish_search_note=dish_search_note,
        location_search_note=location_search_note,
        debug=None,
    )
