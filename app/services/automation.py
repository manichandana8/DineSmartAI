"""Reservation / order automation with mandatory Yes/No confirmation (demo: no live APIs)."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlmodel import Session

from app.config import get_settings
from app.integrations.llm import parse_automation_llm
from app.integrations.places import place_details
from app.integrations.retell import RetellCallOutcome, initiate_dining_call, normalize_phone_e164_us
from app.models.domain import (
    AutomationAvailability,
    ClarificationChip,
    ClarificationChipGroup,
    RecommendResponse,
    RestaurantCandidate,
    UserIntent,
)
from app.services.memory import (
    clear_pending_automation,
    get_pending_automation,
    get_venues_snapshot,
    save_pending_automation,
)
from app.services.booking_confirmation import record_booking_and_maybe_email
from app.services.reservation_time_slots import (
    resolve_profile_for_automation,
    time_suggestion_chip_group,
)


async def _automation_completion_response(
    session: Session,
    user_id: str,
    intent: UserIntent,
    payload: Dict[str, Any],
    action: str,
    body: str,
    *,
    outcome: Optional[RetellCallOutcome] = None,
    self_service: bool = False,
) -> RecommendResponse:
    extra = await record_booking_and_maybe_email(
        session, user_id, payload, outcome, action, self_service=self_service
    )
    b = body.strip()
    b += (
        f"\n\n---\nBooking reference: {extra['confirmation_code']}\n"
        f"Customer portal: {extra['portal_url']}\n"
    )
    if extra["email_sent"]:
        b += "We sent a confirmation email to your saved address (or the demo inbox).\n"
    else:
        b += (
            "To get confirmations by email: set contact_email on your profile "
            "(PATCH /v1/profile/{uid}) and add RESEND_API_KEY + BOOKING_FROM_EMAIL to your server .env.\n"
        ).replace("{uid}", user_id)
    return RecommendResponse(
        clarification=b,
        intent=intent,
        automation_completed="completed",
        booking_confirmation_code=extra["confirmation_code"],
        booking_portal_url=extra["portal_url"],
    )

_RESERVE_OR_ORDER_IN_MESSAGE = re.compile(
    r"\b("
    r"book|reserved?|reservation|table\s+for|order\s+from|order\s+at|"
    r"place\s+(?:my\s+|an\s+)?order|checkout|pay(?:ment)?"
    r")\b",
    re.I,
)

# User named a major chain that is not on the last result cards — run a new search (avoid "near me" alone).
_CHAIN_OR_NAMED_FAST_FOOD = re.compile(
    r"\b("
    r"(?:in[\s-]+){1,2}n[\s-]*out(?:\s+burger)?|in[\s-]*n[\s-]*out(?:\s+burger)?|innout|"
    r"chipotle|mcdonald'?s?|burger\s+king|taco\s+bell|subway|"
    r"starbucks|panera|wendy'?s?|kfc|popeyes?|shake\s+shack|five\s+guys|"
    r"dunkin(?:'\s*donuts)?|domino'?s?|pizza\s+hut|little\s+caesars|"
    r"olive\s+garden|applebee'?s?|ihop|denny'?s?|waffle\s+house"
    r")\b",
    re.I,
)


def _automation_yield_to_new_search(
    message: str,
    venues: List[Dict[str, str]],
    *,
    allow_without_reserve_keyword: bool = False,
) -> bool:
    """
    True when the user is trying to book/order a place that does not match any venue
    in the current snapshot but clearly names another target (chain, 'near me', etc.).
    Caller should clear pending automation and return None so recommendation runs fresh.
    """
    if not venues:
        return False
    if _match_venue_by_name(message, venues) is not None:
        return False
    low = message.lower()
    has_reserve = bool(_RESERVE_OR_ORDER_IN_MESSAGE.search(message))
    if not has_reserve and not allow_without_reserve_keyword:
        return False
    if _CHAIN_OR_NAMED_FAST_FOOD.search(low):
        return True
    return False


def _message_pivots_to_new_search(message: str) -> bool:
    """True when the user names a cuisine/food search without booking-or-order language."""
    from app.agents.intent import detect_cuisine_from_message

    if detect_cuisine_from_message(message) is None:
        return False
    if _RESERVE_OR_ORDER_IN_MESSAGE.search(message):
        return False
    return True


def _large_group_threshold() -> int:
    raw = os.environ.get("SMARTDINE_LARGE_GROUP_MIN", "8")
    try:
        n = int(raw)
        return max(2, min(n, 50))
    except ValueError:
        return 8


LARGE_GROUP_MIN_GUESTS = _large_group_threshold()

_WD_NAMES = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _party_int_safe(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _payload_has_date(payload: Dict[str, Any]) -> bool:
    return bool((payload.get("date_phrase") or "").strip())


def _parse_clock_to_normalized_phrase(raw: str) -> Optional[str]:
    """Normalize to 'h:mm am|pm' for storage when possible (supports 24h)."""
    if not (raw or "").strip():
        return None
    s = raw.strip()
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap]m)\b", s, re.I)
    if m:
        return m.group(0).strip()
    m24 = re.search(r"(?<![:/\d])([01]?\d|2[0-3]):([0-5]\d)(?!\d)", s)
    if m24:
        h, mn = int(m24.group(1)), int(m24.group(2))
        h12 = h % 12
        if h12 == 0:
            h12 = 12
        ap = "am" if h < 12 else "pm"
        return f"{h12}:{mn:02d} {ap}"
    return None


def _payload_has_time(payload: Dict[str, Any]) -> bool:
    tp = (payload.get("time_phrase") or "").strip()
    if not tp:
        return False
    low = tp.lower()
    if low in ("custom time", "custom"):
        return False
    return _parse_clock_to_normalized_phrase(tp) is not None


def _payload_has_party(payload: Dict[str, Any]) -> bool:
    return _party_int_safe(payload.get("party")) is not None


def reserve_missing_slots(payload: Dict[str, Any]) -> List[str]:
    """Ordered required slots for a table reservation (restaurant is chosen separately)."""
    slots: List[str] = []
    if not _payload_has_party(payload):
        slots.append("party")
    if not _payload_has_date(payload):
        slots.append("date")
    if not _payload_has_time(payload):
        slots.append("time")
    return slots


def _next_occurrence_of_weekday(name: str, now: datetime) -> datetime:
    target = _WD_NAMES.index(name.lower())
    delta = (target - now.weekday()) % 7
    return now + timedelta(days=delta)


def _format_calendar_date_line(date_phrase: Optional[str]) -> str:
    if not date_phrase:
        return ""
    dp = date_phrase.strip().lower()
    now = datetime.now()
    if dp in ("today", "tonight"):
        return now.strftime("%A, %B %d, %Y")
    if dp == "tomorrow":
        return (now + timedelta(days=1)).strftime("%A, %B %d, %Y")
    if dp in _WD_NAMES:
        d = _next_occurrence_of_weekday(dp, now)
        return d.strftime("%A, %B %d, %Y")
    return date_phrase.strip().title()


def _format_clock_line(time_phrase: Optional[str]) -> str:
    if not time_phrase:
        return ""
    norm = _parse_clock_to_normalized_phrase(time_phrase)
    if not norm:
        return time_phrase.strip()
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap]m)\b", norm, re.I)
    if not m:
        return time_phrase.strip()
    h = int(m.group(1))
    mn_raw = m.group(2)
    mn_i = int(mn_raw) if mn_raw else 0
    ap = m.group(3).upper()
    suffix = "AM" if ap == "AM" else "PM"
    return f"{h}:{mn_i:02d} {suffix}"


def _targeted_reserve_clarification(venue_name: str, payload: Dict[str, Any], missing: List[str]) -> str:
    have_bits: List[str] = []
    pi = _party_int_safe(payload.get("party"))
    dp = payload.get("date_phrase")
    tp = payload.get("time_phrase")
    if dp and "date" not in missing:
        have_bits.append(f"the date ({dp})")
    if tp and "time" not in missing:
        have_bits.append(f"the time ({tp})")
    if pi is not None and "party" not in missing:
        have_bits.append(f"party size ({pi} guests)")

    known = ""
    if have_bits:
        if len(have_bits) == 1:
            known = f"Got {have_bits[0]}. "
        else:
            known = "Got " + ", ".join(have_bits[:-1]) + f", and {have_bits[-1]}. "

    asks: List[str] = []
    if "date" in missing:
        asks.append("What date should I book for?")
    if "time" in missing:
        asks.append(
            "What time should I book? Tap a slot, or Custom time and type a time in the box "
            "(e.g. 7:30 pm, 7:30pm, or 19:30), then Send choices."
        )
    if "party" in missing:
        asks.append("How many guests should I reserve for?")

    ask = " ".join(asks)
    extra = ""
    if pi is not None and pi >= LARGE_GROUP_MIN_GUESTS and missing:
        extra = (
            "\n\nFor larger groups, availability is often limited—I’ll flag that before any confirmation. "
            "If plans are flexible, consider an earlier seating or a less busy night."
        )
    head = f"For {venue_name}: " if venue_name else ""
    return f"{head}{known}{ask}{extra}".strip()


def automation_availability_for(r: RestaurantCandidate, intent: UserIntent) -> AutomationAvailability:
    web = bool((r.website or "").strip())
    mode = intent.mode
    s = get_settings()
    retell_on = bool((s.retell_api_key or "").strip() and (s.retell_from_number or "").strip())
    return AutomationAvailability(
        reservation_supported=True,
        delivery_order_supported=mode in ("delivery", "either", "pickup"),
        pickup_order_supported=mode in ("pickup", "either", "dine_in"),
        payment_supported=web and mode in ("delivery", "pickup"),
        agent_execution_supported=True,
        retell_configured=retell_on,
    )


def _classify_yes_no(message: str) -> Optional[bool]:
    low = message.strip().lower()
    if not low:
        return None
    if re.search(r"\b(no|nope|nah|cancel|don't|dont|do not|stop|never mind|abort)\b", low):
        if re.search(r"\b(yes|yeah|yep|confirm|proceed)\b", low):
            return None
        return False
    if re.match(
        r"^(yes|yeah|yep|yup|sure|ok|okay|please|go ahead|book it|reserve it|do it|confirm|proceed)\b",
        low,
    ):
        return True
    if low in ("y", "k", "kk"):
        return True
    if low == "n":
        return False
    return None


def execution_preference_for_payload(
    payload: Dict[str, Any],
    message: str,
    parsed: Optional[Dict[str, Any]] = None,
) -> str:
    """
    agent = DineSmartAI executes via Retell (or simulated) after Yes.
    self_service = user gets links only after Yes (no outbound call).
    Explicit phrases in the latest message win.
    """
    low = (message or "").lower()
    if re.search(
        r"\b(i'?ll\s+book\s+online|just\s+(the\s+)?links?|i\s+prefer\s+to\s+book\s+myself|i'?ll\s+do\s+it\s+myself|"
        r"only\s+(the\s+)?links?|send\s+me\s+the\s+links?)\b",
        low,
    ):
        return "self_service"
    if re.search(
        r"\b(you\s+do\s+it|handle\s+it\s+(yourself|for\s+me)|use\s+the\s+agent|call\s+for\s+me|call\s+and\s+reserve|"
        r"have\s+(?:smartdine|dinesmartai)|(?:smartdine|dinesmartai)\s+to\s+(book|call|order)|place\s+the\s+order\s+for\s+me|"
        r"book\s+it\s+for\s+me|let\s+the\s+agent|retell|phone\s+call\s+to\s+(book|reserve|order))\b",
        low,
    ):
        return "agent"
    cur = payload.get("execution_preference")
    if isinstance(cur, str) and cur.lower() in ("agent", "self_service"):
        return cur.lower()
    if parsed:
        v = parsed.get("execution_preference")
        if isinstance(v, str) and v.lower() in ("agent", "self_service"):
            return v.lower()
    return "agent"


async def _self_service_link_bundle(place_id: str, venue_name: str) -> str:
    d = await place_details(place_id)
    lat = lng = None
    if d:
        loc = (d.get("geometry") or {}).get("location") or {}
        lat, lng = loc.get("lat"), loc.get("lng")
    if lat is not None and lng is not None:
        maps = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"
    else:
        maps = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote_plus(venue_name)
    reserve = "https://www.google.com/search?q=" + urllib.parse.quote_plus(f"{venue_name} reserve table")
    order_q = "https://www.google.com/search?q=" + urllib.parse.quote_plus(f"{venue_name} order online pickup")
    web = (d or {}).get("website") if isinstance(d, dict) else None
    lines = [
        f"Self-service links for {venue_name}:",
        f"- Directions / Maps: {maps}",
        f"- Reservation search: {reserve}",
        f"- Ordering search: {order_q}",
    ]
    if web:
        lines.append(f"- Website / menu: {web}")
    lines.append("")
    lines.append(
        "DineSmartAI did not place a call—you chose self-service. "
        "Say if you want the DineSmartAI agent to call the venue instead (Retell AI)."
    )
    return "\n".join(lines)


def _normalize_for_match(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _venue_name_score(norm_message: str, venue_name: str) -> int:
    nv = _normalize_for_match(venue_name)
    if not nv or len(norm_message) < 2:
        return 0
    score = 0
    if len(nv) >= 4 and nv in norm_message:
        score += 80 + min(len(nv), 40)
    for t in nv.split():
        if len(t) >= 3 and t in norm_message:
            score += len(t)
    for raw in re.split(r"[\s']+", venue_name):
        part = _normalize_for_match(raw)
        if len(part) >= 3 and part in norm_message:
            score += max(0, len(part) - 1)
    return score


def _match_venue_by_name(message: str, venues: List[Dict[str, str]]) -> Optional[int]:
    norm = _normalize_for_match(message)
    scored: List[tuple[int, int]] = []
    for i, v in enumerate(venues):
        s = _venue_name_score(norm, v.get("name", ""))
        scored.append((s, i))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] < 10:
        return None
    if len(scored) > 1 and scored[1][0] >= 10 and scored[0][0] - scored[1][0] <= 4:
        return None
    return scored[0][1]


def _ordinal_pick_from_message(low: str) -> Optional[int]:
    if re.search(r"\b(first|1st|top\s*pick|option\s*1|#1)\b", low):
        return 0
    if re.search(r"\b(second|2nd|backup\s*1|option\s*2|#2)\b", low):
        return 1
    if re.search(r"\b(third|3rd|backup\s*2|option\s*3|#3)\b", low):
        return 2
    if re.search(r"\b(fourth|4th|#4)\b", low):
        return 3
    if re.search(r"\b(fifth|5th|#5)\b", low):
        return 4
    return None


def resolve_automation_venue_index(
    message: str,
    venues: List[Dict[str, str]],
    parsed_pick_index: Any,
) -> tuple[int, bool]:
    """
    Returns (pick_index, needs_venue_selection).
    When needs_venue_selection is True with multiple venues, do not assume index 0.
    """
    n = len(venues)
    if n <= 1:
        return 0, False

    low = message.lower()
    name_idx = _match_venue_by_name(message, venues)
    if name_idx is not None:
        return name_idx, False

    ord_idx = _ordinal_pick_from_message(low)
    if ord_idx is not None:
        return min(max(ord_idx, 0), n - 1), False

    try:
        pi = 0 if parsed_pick_index is None else int(parsed_pick_index)
    except (TypeError, ValueError):
        pi = 0
    pi = max(0, min(pi, n - 1))
    if pi != 0:
        return pi, False

    return 0, True


def _venue_chip_groups(action: str, venues: List[Dict[str, Any]]) -> List[ClarificationChipGroup]:
    verb = "Reserve at" if action == "reserve_table" else "Order from"
    chips = [
        ClarificationChip(label=str(v.get("name") or "?"), value=f"{verb} {v.get('name', '')}")
        for v in venues
    ]
    return [
        ClarificationChipGroup(title="Which restaurant?", chips=chips, exclusive=True),
    ]


def _party_size_chip_group() -> ClarificationChipGroup:
    chips = [
        ClarificationChip(label="2 people", value="2 people"),
        ClarificationChip(label="4 people", value="4 people"),
        ClarificationChip(label="6 people", value="6 people"),
        ClarificationChip(label="8 people", value="8 people"),
        ClarificationChip(label="12 people", value="12 people"),
        ClarificationChip(label="20 people", value="20 people"),
    ]
    return ClarificationChipGroup(title="Party size", chips=chips, exclusive=True)


async def _async_time_suggestion_chip_group(
    venues: List[Dict[str, Any]],
    payload: Optional[Dict[str, Any]] = None,
) -> ClarificationChipGroup:
    prof = await resolve_profile_for_automation(
        venues,
        payload,
        place_details_fn=place_details,
    )
    return time_suggestion_chip_group(prof)


def _date_suggestion_chip_group() -> ClarificationChipGroup:
    chips = [
        ClarificationChip(label="Today", value="Today"),
        ClarificationChip(label="Tomorrow", value="Tomorrow"),
        ClarificationChip(label="Monday", value="Monday"),
        ClarificationChip(label="Tuesday", value="Tuesday"),
        ClarificationChip(label="Wednesday", value="Wednesday"),
        ClarificationChip(label="Thursday", value="Thursday"),
        ClarificationChip(label="Friday", value="Friday"),
        ClarificationChip(label="Saturday", value="Saturday"),
        ClarificationChip(label="Sunday", value="Sunday"),
    ]
    return ClarificationChipGroup(title="Date", chips=chips, exclusive=True)


async def _gathering_followup_chip_groups(
    action: str,
    need_party: bool,
    need_time: bool,
    need_date: bool,
    venues: List[Dict[str, Any]],
    payload: Optional[Dict[str, Any]] = None,
) -> List[ClarificationChipGroup]:
    """After the restaurant is known, suggest party / date / time (parsed by _merge_gathering_payload)."""
    if action != "reserve_table":
        return []
    out: List[ClarificationChipGroup] = []
    if need_party:
        out.append(_party_size_chip_group())
    if need_date:
        out.append(_date_suggestion_chip_group())
    if need_time:
        out.append(await _async_time_suggestion_chip_group(venues, payload))
    return out


async def _gathering_followup_from_slots(
    action: str,
    slots: List[str],
    venues: List[Dict[str, Any]],
    payload: Optional[Dict[str, Any]] = None,
) -> List[ClarificationChipGroup]:
    return await _gathering_followup_chip_groups(
        action,
        "party" in slots,
        "time" in slots,
        "date" in slots,
        venues,
        payload,
    )


def _booking_yes_no_chip_groups() -> List[ClarificationChipGroup]:
    """Exclusive Yes/No; UI submits one choice immediately (no separate Send)."""
    return [
        ClarificationChipGroup(
            title="Confirm",
            chips=[
                ClarificationChip(label="Yes", value="Yes"),
                ClarificationChip(label="No", value="No"),
            ],
            exclusive=True,
            immediate_submit=True,
        )
    ]


async def _combined_venue_and_reserve_chips(
    action: str,
    venues: List[Dict[str, Any]],
    need_party: bool,
    need_time: bool,
    need_date: bool,
    draft_payload: Optional[Dict[str, Any]] = None,
) -> List[ClarificationChipGroup]:
    """When the venue is not yet chosen, optionally stack detail groups in the same step."""
    groups = list(_venue_chip_groups(action, venues))
    groups.extend(
        await _gathering_followup_chip_groups(
            action, need_party, need_time, need_date, venues, draft_payload
        )
    )
    return groups


async def _complete_gathering_to_confirmation(
    session: Session,
    user_id: str,
    rid: Optional[str],
    intent: UserIntent,
    venues: List[Dict[str, Any]],
    payload: Dict[str, Any],
) -> RecommendResponse:
    idx = int(payload.get("pick_index", 0))
    idx = max(0, min(idx, len(venues) - 1))
    v = venues[idx]
    action = payload.get("action", "reserve_table")
    if action == "reserve_table":
        slots = reserve_missing_slots(payload)
        if slots:
            vn = payload.get("venue_name") or v["name"]
            pay = dict(payload)
            pay["venue_name"] = vn
            pay["pick_index"] = idx
            pay["place_id"] = v["place_id"]
            aid = save_pending_automation(
                session, user_id, rid, "gathering", action, "", pay
            )
            return RecommendResponse(
                clarification=_targeted_reserve_clarification(vn, pay, slots),
                clarification_chip_groups=await _gathering_followup_from_slots(
                    action, slots, venues, pay
                ),
                intent=intent,
                pending_automation_id=aid,
            )
    party = payload.get("party")
    try:
        party_i = int(party) if party is not None else 2
    except (TypeError, ValueError):
        party_i = 2
    dline = _format_calendar_date_line(payload.get("date_phrase"))
    tline = _format_clock_line(payload.get("time_phrase"))
    if dline and tline:
        when_line = f"{dline} at {tline}"
    elif dline:
        when_line = dline
    elif tline:
        when_line = tline
    else:
        when_line = ""
    total = payload.get("estimated_total_usd")
    try:
        total_f = float(total) if total is not None else None
    except (TypeError, ValueError):
        total_f = None
    pref = execution_preference_for_payload(payload, "", None)
    payload["execution_preference"] = pref
    conf = _build_confirmation_text(
        action,
        v["name"],
        payload.get("date_phrase"),
        payload.get("time_phrase"),
        party_i,
        payload.get("order_items"),
        total_f,
        pref,
    )
    full_payload = {
        **payload,
        "venue_name": v["name"],
        "place_id": v["place_id"],
        "pick_index": idx,
        "party": party_i,
        "when_line": when_line or "see above",
        "order_items": payload.get("order_items"),
        "total_line": (
            f"Estimated total: ${total_f:.2f}" if total_f is not None else ""
        ),
        "execution_preference": pref,
    }
    aid = save_pending_automation(
        session,
        user_id,
        rid,
        "awaiting_yes_no",
        action,
        conf,
        full_payload,
    )
    return RecommendResponse(
        clarification=conf,
        clarification_chip_groups=_booking_yes_no_chip_groups(),
        intent=intent,
        pending_automation_id=aid,
    )


def _merge_gathering_payload(payload: Dict[str, Any], message: str) -> Dict[str, Any]:
    low = message.lower()
    party_m = re.search(r"\b(\d+)\s*(people|guests|persons|pax)\b", low)
    if party_m:
        payload["party"] = int(party_m.group(1))
    elif re.search(r"\bfor two\b|\btwo people\b|\b2 people\b", low):
        payload["party"] = 2
    tm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap]m)\b", low, re.I)
    if tm:
        payload["time_phrase"] = tm.group(0).strip()
    elif re.search(r"\b(\d{1,2})\s*pm\b", low, re.I):
        m = re.search(r"\b(\d{1,2})\s*pm\b", low, re.I)
        payload["time_phrase"] = f"{m.group(1)} pm"
    if not payload.get("time_phrase"):
        norm_t = _parse_clock_to_normalized_phrase(message)
        if norm_t:
            payload["time_phrase"] = norm_t
    if not payload.get("date_phrase"):
        mcal = re.search(
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december|"
            r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b",
            low,
        )
        if mcal:
            payload["date_phrase"] = f"{mcal.group(1)} {mcal.group(2)}"
    if not payload.get("date_phrase"):
        mslash = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", message.strip())
        if mslash:
            payload["date_phrase"] = mslash.group(0).strip()
    if not payload.get("date_phrase"):
        for w in (
            "today",
            "tonight",
            "tomorrow",
            "friday",
            "saturday",
            "sunday",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
        ):
            if w in low:
                payload["date_phrase"] = w
                break
    if payload.get("time_phrase"):
        norm = _parse_clock_to_normalized_phrase(str(payload["time_phrase"]))
        if norm:
            payload["time_phrase"] = norm
        elif not _payload_has_time(payload):
            payload.pop("time_phrase", None)
    return payload


def _build_confirmation_text(
    action: str,
    venue_name: str,
    date_phrase: Optional[str],
    time_phrase: Optional[str],
    party: Optional[int],
    order_items: Optional[str],
    total: Optional[float],
    execution_preference: str,
) -> str:
    pref = execution_preference if execution_preference in ("agent", "self_service") else "agent"

    if action == "place_order":
        if pref == "self_service":
            lines = [
                f"Selected restaurant: {venue_name}",
                "Action: Self-service ordering (links after you confirm)",
                "DineSmartAI will not place a call or charge anything.",
                "",
                "Details:",
                f"- Items: {order_items or 'your items (confirm with the restaurant or site)'}",
            ]
            if total is not None:
                lines.append(f"- Total (estimate): ${total:.2f}")
            lines.append("")
            lines.append("Use the buttons below to confirm or decline.")
            return "\n".join(lines)
        lines = [
            f"Selected restaurant: {venue_name}",
            "Action: Order via DineSmartAI",
            "",
            "Details:",
            f"- Items: {order_items or 'your items (confirm on the call)'}",
        ]
        if total is not None:
            lines.append(f"- Total (estimate): ${total:.2f}")
        else:
            lines.append("- Total: confirm with the restaurant on the call")
        lines.append("")
        lines.append("Use the buttons below to confirm or decline.")
        return "\n".join(lines)

    pi = _party_int_safe(party) or 2
    dline = _format_calendar_date_line(date_phrase)
    tline = _format_clock_line(time_phrase)
    if pref == "self_service":
        lines = [
            f"Selected place: {venue_name}",
            "Here's your booking summary—please confirm.",
            "Action: Self-service reservation (links after you confirm)",
            "DineSmartAI will not place an outbound call for this step.",
            "",
            "Details:",
            f"- Date: {dline}",
            f"- Time: {tline}",
            f"- Guests: {pi}",
        ]
        if pi >= LARGE_GROUP_MIN_GUESTS:
            lines.append("")
            lines.append(
                f"Note: Large groups often need direct confirmation—links are starting points, not a guarantee."
            )
        lines.append("")
        lines.append("Use the buttons below to confirm or decline.")
        return "\n".join(lines)

    lines = [
        f"Selected place: {venue_name}",
        "Here's your booking summary—please confirm.",
        "Action: Reservation via DineSmartAI",
        "",
        "Details:",
        f"- Date: {dline}",
        f"- Time: {tline}",
        f"- Guests: {pi}",
    ]
    if pi >= LARGE_GROUP_MIN_GUESTS:
        lines.append("")
        lines.append(
            f"Note: Large group bookings may require confirmation from the restaurant. "
            f"Availability for {pi} guests is not guaranteed until the call completes."
        )
        lines.append(
            "If plans are flexible, mention backup times when you confirm Yes."
        )
    lines.append("")
    lines.append("Use the buttons below to confirm or decline.")
    return "\n".join(lines)


def _heuristic_automation(message: str, venues: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    low = message.lower()
    reserve = bool(re.search(r"\b(book|reserve|reservation|table for)\b", low))
    order = bool(re.search(r"\b(order|pay|payment|checkout|place my order)\b", low))
    agent_only = bool(
        re.search(
            r"\b(you\s+do\s+it|handle\s+it\s+yourself|use\s+the\s+agent|call\s+for\s+me|call\s+and\s+reserve|"
            r"have\s+(?:smartdine|dinesmartai)|(?:smartdine|dinesmartai)\s+to\s+(book|call|order)|book\s+it\s+for\s+me|place\s+the\s+order\s+for\s+me)\b",
            low,
        )
    )
    if not reserve and not order:
        if not agent_only:
            return None
        reserve = True
    action = "place_order" if order and not reserve else "reserve_table"
    ord_i = _ordinal_pick_from_message(low)
    idx = ord_i if ord_i is not None else 0
    idx = min(max(idx, 0), len(venues) - 1)
    party = None
    pm = re.search(r"\b(\d+)\s*(people|guests|persons|pax)\b", low)
    if pm:
        party = int(pm.group(1))
    elif re.search(r"\bfor two\b|\btwo people\b|\b2 people\b", low):
        party = 2
    time_phrase = None
    tm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap]m)\b", low, re.I)
    if tm:
        time_phrase = tm.group(0).strip()
    dp = None
    for w in (
        "today",
        "tonight",
        "tomorrow",
        "friday",
        "saturday",
        "sunday",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
    ):
        if w in low:
            dp = w
            break
    missing: List[str] = []
    if action == "reserve_table":
        if not party:
            missing.append("party")
        if not time_phrase:
            missing.append("time")
        if not dp:
            missing.append("date")
    ep = execution_preference_for_payload({}, message, None)
    return {
        "wants_automation": True,
        "action": action,
        "pick_index": idx,
        "party": party,
        "time_phrase": time_phrase,
        "date_phrase": dp,
        "order_items": None,
        "estimated_total_usd": None,
        "missing": missing,
        "execution_preference": ep,
    }


async def try_automation_flow(
    session: Session,
    user_id: str,
    message: str,
    recommendation_id: Optional[str],
    intent: UserIntent,
) -> Optional[RecommendResponse]:
    pending = get_pending_automation(session, user_id)

    if pending and pending.phase == "awaiting_yes_no":
        yn = _classify_yes_no(message)
        if yn is None:
            if _message_pivots_to_new_search(message):
                clear_pending_automation(session, user_id)
                return None
            return RecommendResponse(
                clarification=(
                    "I need a clear choice. After Yes, DineSmartAI runs the path we agreed on "
                    "(Retell AI call for agent mode, or self-service links for link-only mode)."
                ),
                clarification_chip_groups=_booking_yes_no_chip_groups(),
                intent=intent,
                pending_automation_id=pending.id,
            )
        payload = json.loads(pending.payload_json or "{}")
        vname = payload.get("venue_name", "the restaurant")
        place_id = str(payload.get("place_id") or "")
        if yn is False:
            clear_pending_automation(session, user_id)
            return RecommendResponse(
                clarification=(
                    f"I will not proceed for {vname}. Say if you want a different time, party size, "
                    "another restaurant from your list, or a new search."
                ),
                intent=intent,
                automation_completed="cancelled",
            )
        clear_pending_automation(session, user_id)
        action = pending.action_kind
        pref = str(payload.get("execution_preference") or "agent").lower()
        if pref not in ("agent", "self_service"):
            pref = "agent"

        if pref == "self_service":
            if not place_id:
                body = (
                    f"Self-service mode for {vname}, but no place id is stored—open Maps or search the venue name "
                    f"to finish booking or ordering yourself."
                )
            else:
                body = await _self_service_link_bundle(place_id, vname)
            return await _automation_completion_response(
                session, user_id, intent, payload, action, body, self_service=True
            )

        detail = await place_details(place_id) if place_id else None
        raw_phone = (detail or {}).get("formatted_phone_number") if isinstance(detail, dict) else None
        to_e164 = normalize_phone_e164_us(raw_phone)

        outcome = await initiate_dining_call(
            to_number_e164=to_e164,
            venue_name=vname,
            action_kind=action,
            payload=payload,
            user_id=user_id,
            place_id=place_id or "unknown",
        )

        if action == "reserve_table":
            body = (
                f"{outcome.summary}\n\n"
                f"Requested reservation: {vname}\n"
                f"When: {payload.get('when_line', 'see above')}\n"
                f"Guests: {payload.get('party', 2)}\n"
            )
            if not outcome.ok and outcome.mode == "skipped":
                body += (
                    "\nYou can still use optional self-service links from the last recommendation card, "
                    "or reply with a phone number for the venue if you have one."
                )
        else:
            items = (payload.get("order_items") or "your items").strip()
            total_line = (payload.get("total_line") or "").strip()
            body = f"{outcome.summary}\n\nPlace: {vname}\nItems: {items}\n"
            if total_line:
                body += f"{total_line}\n"
            if not outcome.ok and outcome.mode == "skipped":
                body += "\nTry the venue’s website or ordering search from the card, or provide a direct phone number."

        return await _automation_completion_response(
            session, user_id, intent, payload, action, body, outcome=outcome
        )

    if pending and pending.phase == "choosing_venue":
        low = message.lower()
        if re.search(r"\b(cancel|never mind|forget it|start over|different search)\b", low):
            clear_pending_automation(session, user_id)
            return None
        if _message_pivots_to_new_search(message):
            clear_pending_automation(session, user_id)
            return None
        rid = pending.recommendation_id or (recommendation_id or "").strip() or None
        venues = get_venues_snapshot(session, user_id, rid) if rid else []
        if not venues:
            clear_pending_automation(session, user_id)
            return None
        payload = json.loads(pending.payload_json or "{}")
        action = payload.get("action", "reserve_table")
        payload = _merge_gathering_payload(dict(payload), message)
        payload["execution_preference"] = execution_preference_for_payload(payload, message)
        resolved = False
        name_idx = _match_venue_by_name(message, venues)
        if name_idx is not None:
            payload["pick_index"] = name_idx
            payload["venue_name"] = venues[name_idx]["name"]
            payload["place_id"] = venues[name_idx]["place_id"]
            resolved = True
        else:
            ord_idx = _ordinal_pick_from_message(low)
            if ord_idx is not None:
                oi = min(max(ord_idx, 0), len(venues) - 1)
                payload["pick_index"] = oi
                payload["venue_name"] = venues[oi]["name"]
                payload["place_id"] = venues[oi]["place_id"]
                resolved = True
            elif len(venues) == 1:
                payload["pick_index"] = 0
                payload["venue_name"] = venues[0]["name"]
                payload["place_id"] = venues[0]["place_id"]
                resolved = True
        if not resolved:
            if _automation_yield_to_new_search(
                message, venues, allow_without_reserve_keyword=True
            ):
                clear_pending_automation(session, user_id)
                return None
            miss_nv = reserve_missing_slots(payload) if action == "reserve_table" else []
            need_p = "party" in miss_nv
            need_t = "time" in miss_nv
            need_d = "date" in miss_nv
            aid = save_pending_automation(
                session, user_id, rid, "choosing_venue", action, "", payload
            )
            clar_nv = "Pick a restaurant from your last results (tap below or type the name)."
            if miss_nv:
                clar_nv = (
                    "Pick a restaurant and add any missing date, time, or party size using the groups "
                    "below, then Send choices—or type one line (e.g. Tahina, Friday, 7 pm, 20 people)."
                )
            return RecommendResponse(
                clarification=clar_nv,
                clarification_chip_groups=await _combined_venue_and_reserve_chips(
                    action, venues, need_p, need_t, need_d, payload
                ),
                intent=intent,
                pending_automation_id=aid,
            )
        slots_cv = reserve_missing_slots(payload) if action == "reserve_table" else []
        if slots_cv:
            vn = payload.get("venue_name", "that pick")
            aid = save_pending_automation(
                session, user_id, rid, "gathering", action, "", payload
            )
            return RecommendResponse(
                clarification=_targeted_reserve_clarification(vn, payload, slots_cv),
                clarification_chip_groups=await _gathering_followup_from_slots(
                    action, slots_cv, venues, payload
                ),
                intent=intent,
                pending_automation_id=aid,
            )
        return await _complete_gathering_to_confirmation(
            session, user_id, rid, intent, venues, payload
        )

    if pending and pending.phase == "gathering":
        low = message.lower()
        if re.search(r"\b(cancel|never mind|forget it|start over|different search)\b", low):
            clear_pending_automation(session, user_id)
            return None
        if _message_pivots_to_new_search(message):
            clear_pending_automation(session, user_id)
            return None
        payload = json.loads(pending.payload_json or "{}")
        rid = pending.recommendation_id or (recommendation_id or "").strip() or None
        venues = get_venues_snapshot(session, user_id, rid) if rid else []
        if not venues:
            clear_pending_automation(session, user_id)
            return None
        payload = _merge_gathering_payload(dict(payload), message)
        payload["execution_preference"] = execution_preference_for_payload(payload, message)
        if _automation_yield_to_new_search(
            message, venues, allow_without_reserve_keyword=True
        ):
            clear_pending_automation(session, user_id)
            return None
        name_idx = _match_venue_by_name(message, venues)
        if name_idx is not None:
            payload["pick_index"] = name_idx
            payload["venue_name"] = venues[name_idx]["name"]
            payload["place_id"] = venues[name_idx]["place_id"]
        action = payload.get("action", "reserve_table")
        slots_g = reserve_missing_slots(payload) if action == "reserve_table" else []
        if slots_g:
            vn = payload.get("venue_name", "that pick")
            aid = save_pending_automation(
                session,
                user_id,
                rid,
                "gathering",
                action,
                "",
                payload,
            )
            return RecommendResponse(
                clarification=_targeted_reserve_clarification(vn, payload, slots_g),
                clarification_chip_groups=await _gathering_followup_from_slots(
                    action, slots_g, venues, payload
                ),
                intent=intent,
                pending_automation_id=aid,
            )
        return await _complete_gathering_to_confirmation(
            session, user_id, rid, intent, venues, payload
        )

    rid = (recommendation_id or "").strip() or None
    if not rid:
        return None
    venues = get_venues_snapshot(session, user_id, rid)
    if not venues:
        return None

    if _automation_yield_to_new_search(message, venues):
        clear_pending_automation(session, user_id)
        return None

    if _message_pivots_to_new_search(message):
        return None

    parsed = await parse_automation_llm(message, venues, intent.mode, None)
    if not parsed or not parsed.get("wants_automation"):
        parsed = _heuristic_automation(message, venues)
    if not parsed or not parsed.get("wants_automation"):
        return None

    action = parsed.get("action") or "reserve_table"
    if action not in ("reserve_table", "place_order"):
        action = "reserve_table"
    idx, need_pick = resolve_automation_venue_index(
        message, venues, parsed.get("pick_index")
    )

    party = parsed.get("party")
    if party is not None:
        try:
            party = int(party)
        except (TypeError, ValueError):
            party = None

    slots = (
        reserve_missing_slots(
            {
                "party": party,
                "time_phrase": parsed.get("time_phrase"),
                "date_phrase": parsed.get("date_phrase"),
            }
        )
        if action == "reserve_table"
        else []
    )

    if need_pick:
        draft: Dict[str, Any] = {
            "action": action,
            "party": party,
            "time_phrase": parsed.get("time_phrase"),
            "date_phrase": parsed.get("date_phrase"),
            "order_items": parsed.get("order_items"),
            "estimated_total_usd": parsed.get("estimated_total_usd"),
        }
        draft["execution_preference"] = execution_preference_for_payload(draft, message, parsed)
        aid = save_pending_automation(session, user_id, rid, "choosing_venue", action, "", draft)
        need_party_chips = "party" in slots
        need_time_chips = "time" in slots
        need_date_chips = "date" in slots
        if not slots:
            clar_pick = "Which restaurant should I use? Tap one below or type its name."
        else:
            clar_pick = (
                "Choose a restaurant and add any missing date, time, or party size using the groups "
                "below, then Send choices—or type one line (e.g. Tahina, Friday, 7 pm, 20 people)."
            )
        return RecommendResponse(
            clarification=clar_pick,
            clarification_chip_groups=await _combined_venue_and_reserve_chips(
                action, venues, need_party_chips, need_time_chips, need_date_chips, draft
            ),
            intent=intent,
            pending_automation_id=aid,
        )

    idx = max(0, min(idx, len(venues) - 1))
    v = venues[idx]

    gather_payload = {
        "pick_index": idx,
        "venue_name": v["name"],
        "place_id": v["place_id"],
        "action": action,
        "party": party,
        "time_phrase": parsed.get("time_phrase"),
        "date_phrase": parsed.get("date_phrase"),
        "order_items": parsed.get("order_items"),
        "estimated_total_usd": parsed.get("estimated_total_usd"),
    }
    gather_payload["execution_preference"] = execution_preference_for_payload(
        gather_payload, message, parsed
    )
    slots_g2 = reserve_missing_slots(gather_payload) if action == "reserve_table" else []
    if slots_g2:
        aid = save_pending_automation(session, user_id, rid, "gathering", action, "", gather_payload)
        return RecommendResponse(
            clarification=_targeted_reserve_clarification(v["name"], gather_payload, slots_g2),
            clarification_chip_groups=await _gathering_followup_from_slots(
                action, slots_g2, venues, gather_payload
            ),
            intent=intent,
            pending_automation_id=aid,
        )
    return await _complete_gathering_to_confirmation(
        session, user_id, rid, intent, venues, gather_payload
    )
