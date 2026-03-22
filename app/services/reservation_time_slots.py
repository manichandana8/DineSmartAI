"""Dynamic reservation time-slot chips: venue hours, place types, 30-minute intervals."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.models.domain import ClarificationChip, ClarificationChipGroup

_SLOT_STEP = timedelta(minutes=30)
_MAX_CHIPS = 36
_CUSTOM_LABEL = "Custom time"
_CUSTOM_VALUE = "Custom time"

_WD_ORDER = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

_DATE_CHIP_KEYS = (
    "Today",
    "Tomorrow",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

# (open_minutes_from_midnight, close_minutes_from_midnight, close_next_calendar_day)
_DEFAULT_WINDOWS: Dict[str, Tuple[int, int, bool]] = {
    "restaurant": (11 * 60, 22 * 60, False),
    "cafe": (7 * 60, 20 * 60, False),
    "hotel_dining": (6 * 60, 23 * 60, False),
    "bakery": (7 * 60, 18 * 60, False),
    "dessert_shop": (12 * 60, 23 * 60, False),
    "boba_shop": (11 * 60, 22 * 60, False),
    "bar_lounge": (17 * 60, 1 * 60, True),
}


@dataclass(frozen=True)
class VenueTimeProfile:
    types: Tuple[str, ...]
    opening_hours_lines: Tuple[str, ...]
    name: str = ""


def venue_profile_from_snapshot_row(row: Dict[str, Any]) -> VenueTimeProfile:
    types: List[str] = []
    raw_t = row.get("types_json")
    if isinstance(raw_t, str) and raw_t.strip():
        try:
            data = json.loads(raw_t)
            if isinstance(data, list):
                types = [str(x) for x in data if isinstance(x, str)]
        except json.JSONDecodeError:
            pass
    oh: List[str] = []
    raw_oh = row.get("opening_hours_json")
    if isinstance(raw_oh, str) and raw_oh.strip():
        try:
            data = json.loads(raw_oh)
            if isinstance(data, list):
                oh = [str(x).strip() for x in data if isinstance(x, str) and str(x).strip()]
        except json.JSONDecodeError:
            pass
    name = str(row.get("name") or "")
    return VenueTimeProfile(types=tuple(types), opening_hours_lines=tuple(oh), name=name)


def detect_venue_kind(types: Sequence[str], venue_name: str = "") -> str:
    """Map Google Places types (+ name hints) to a default-hours bucket."""
    tset = {str(x).lower() for x in types if x}
    nm = (venue_name or "").lower()
    if any(k in nm for k in ("boba", "bubble tea", "tapioca", "pearl milk")):
        return "boba_shop"
    if "lodging" in tset:
        return "hotel_dining"
    if tset & {"bar", "night_club", "wine_bar", "lounge"}:
        return "bar_lounge"
    if "bakery" in tset:
        return "bakery"
    if tset & {"dessert_shop", "ice_cream_shop", "confectionery"}:
        return "dessert_shop"
    if tset & {"cafe", "coffee_shop", "tea_house"}:
        return "cafe"
    if "bubble_tea_store" in tset:
        return "boba_shop"
    if tset & {
        "restaurant",
        "meal_takeaway",
        "meal_delivery",
        "brunch_restaurant",
        "fine_dining_restaurant",
        "fast_food_restaurant",
        "food",
    }:
        return "restaurant"
    return "restaurant"


def default_service_window_minutes(kind: str) -> Tuple[int, int, bool]:
    return _DEFAULT_WINDOWS.get(kind, _DEFAULT_WINDOWS["restaurant"])


_TIME_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*([AaPp][Mm])\b",
    re.I,
)
_RANGE_RE = re.compile(
    r"(\d{1,2}(?::\d{2})?\s*[AaPp][Mm])\s*[–\-]\s*(\d{1,2}(?::\d{2})?\s*[AaPp][Mm])",
    re.I,
)


def _parse_clock_to_minutes(raw: str) -> Optional[int]:
    m = _TIME_RE.search(raw.strip())
    if not m:
        return None
    h = int(m.group(1))
    mn = int(m.group(2) or 0)
    ap = m.group(3).upper()
    if ap == "PM" and h != 12:
        h += 12
    if ap == "AM" and h == 12:
        h = 0
    if h > 23 or mn > 59:
        return None
    return h * 60 + mn


def _segments_from_hours_body(body: str) -> List[Tuple[int, int, bool]]:
    """Return list of (open_min, close_min, close_next_day) for one weekday line body."""
    low = body.strip().lower()
    if "closed" in low:
        return []
    segments: List[Tuple[int, int, bool]] = []
    for m in _RANGE_RE.finditer(body):
        o_raw, c_raw = m.group(1), m.group(2)
        om = _parse_clock_to_minutes(o_raw)
        cm = _parse_clock_to_minutes(c_raw)
        if om is None or cm is None:
            continue
        spans = cm <= om
        segments.append((om, cm, spans))
    return segments


def _weekday_key_from_line(line: str) -> Optional[str]:
    m = re.match(r"^\s*([A-Za-z]+)\s*:\s*(.*)$", line.strip())
    if not m:
        return None
    key = m.group(1).strip().lower()
    if key not in _WD_ORDER:
        return None
    return key


def segments_for_weekday(
    opening_hours_lines: Sequence[str], weekday_index: int
) -> Optional[List[Tuple[int, int, bool]]]:
    """
    weekday_index: 0=Monday .. 6=Sunday (matches datetime.weekday()).
    Returns None if no usable parsed hours for that day (caller falls back to defaults).
    """
    if not opening_hours_lines or weekday_index < 0 or weekday_index > 6:
        return None
    want = _WD_ORDER[weekday_index]
    for ln in opening_hours_lines:
        wk = _weekday_key_from_line(ln)
        if wk != want:
            continue
        body = ln.split(":", 1)[1] if ":" in ln else ""
        if "closed" in body.lower():
            return []
        segs = _segments_from_hours_body(body)
        if segs:
            return segs
        return None
    return None


def resolve_chip_calendar_date(date_label: str, now: datetime) -> date:
    low = (date_label or "").strip().lower()
    today = now.date()
    if low in ("today", "tonight"):
        return today
    if low == "tomorrow":
        return today + timedelta(days=1)
    if low in _WD_ORDER:
        target = _WD_ORDER.index(low)
        delta = (target - now.weekday()) % 7
        return today + timedelta(days=delta)
    return today


def _combine_datetime(d: date, minutes_from_midnight: int) -> datetime:
    h, m = divmod(int(minutes_from_midnight), 60)
    return datetime.combine(d, time(hour=h, minute=m))


def _iter_slot_datetimes_for_segment(
    day: date, open_m: int, close_m: int, closes_next_day: bool
) -> List[datetime]:
    open_dt = _combine_datetime(day, open_m)
    if not closes_next_day:
        end_dt = _combine_datetime(day, close_m)
    else:
        end_dt = _combine_datetime(day + timedelta(days=1), close_m)
    out: List[datetime] = []
    cur = open_dt
    while cur <= end_dt:
        out.append(cur)
        cur += _SLOT_STEP
    return out


def slot_datetimes_for_day(
    profile: VenueTimeProfile,
    day: date,
    kind: str,
    now: datetime,
) -> List[datetime]:
    """All 30-minute slot start times that fall on `day` (local) within service windows."""
    wd = day.weekday()
    parsed = segments_for_weekday(profile.opening_hours_lines, wd)
    slots: List[datetime] = []
    if parsed is not None:
        if not parsed:
            return []
        for open_m, close_m, spans in parsed:
            slots.extend(_iter_slot_datetimes_for_segment(day, open_m, close_m, spans))
    else:
        om, cm, spans = default_service_window_minutes(kind)
        slots.extend(_iter_slot_datetimes_for_segment(day, om, cm, spans))
    # De-dupe and sort (overlapping segments from Google)
    uniq = sorted({s.replace(second=0, microsecond=0) for s in slots})
    if day == now.date():
        uniq = [s for s in uniq if s > now]
    return uniq


def _format_slot_value(slot: datetime) -> str:
    h = slot.hour
    m = slot.minute
    ap = "am" if h < 12 else "pm"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    if m:
        return f"{h12}:{m:02d} {ap}"
    return f"{h12} {ap}"


def _format_slot_label_pretty(slot: datetime) -> str:
    h = slot.hour
    m = slot.minute
    ap = "AM" if h < 12 else "PM"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    if m:
        return f"{h12}:{m:02d} {ap}"
    return f"{h12} {ap}"


def _format_slot_label(date_label: str, slot: datetime) -> str:
    val = _format_slot_label_pretty(slot)
    low = (date_label or "").strip().lower()
    if low in ("today", "tonight", "tomorrow"):
        prefix = date_label.strip()[:1].upper() + date_label.strip()[1:].lower()
        return f"{prefix} {val}"
    dname = slot.strftime("%a")
    return f"{dname} {val}"


def _subsample_slots(slots: List[datetime]) -> List[datetime]:
    if not slots:
        return []
    if len(slots) <= _MAX_CHIPS:
        return slots
    step = max(1, (len(slots) + _MAX_CHIPS - 2) // (_MAX_CHIPS - 1))
    picked = slots[::step]
    if slots and picked[-1] != slots[-1]:
        picked = picked[: _MAX_CHIPS - 1] + [slots[-1]]
    return picked[:_MAX_CHIPS]


def chips_for_date_label(
    date_label: str,
    profile: VenueTimeProfile,
    *,
    now: Optional[datetime] = None,
) -> List[ClarificationChip]:
    now = now or datetime.now()
    kind = detect_venue_kind(profile.types, profile.name)
    day = resolve_chip_calendar_date(date_label, now)
    slot_dts = slot_datetimes_for_day(profile, day, kind, now)
    slot_dts = _subsample_slots(slot_dts)
    chips: List[ClarificationChip] = [
        ClarificationChip(
            label=_format_slot_label(date_label, s),
            value=_format_slot_value(s),
        )
        for s in slot_dts
    ]
    chips.append(ClarificationChip(label=_CUSTOM_LABEL, value=_CUSTOM_VALUE))
    return chips


def time_suggestion_chip_group(
    profile: VenueTimeProfile,
    *,
    now: Optional[datetime] = None,
) -> ClarificationChipGroup:
    by_date: Dict[str, List[ClarificationChip]] = {}
    first_row: List[ClarificationChip] = []
    for dk in _DATE_CHIP_KEYS:
        row = chips_for_date_label(dk, profile, now=now)
        by_date[dk] = row
        if not first_row:
            first_row = row
    return ClarificationChipGroup(
        title="Time",
        chips=list(first_row),
        exclusive=True,
        time_options_by_date=by_date,
    )


def conservative_profile_for_venue_list(rows: Sequence[Dict[str, Any]]) -> VenueTimeProfile:
    """Before a restaurant is chosen: neutral full-service window (no per-venue hours merge)."""
    if len(rows) == 1:
        return venue_profile_from_snapshot_row(rows[0])
    return VenueTimeProfile(types=("restaurant",), opening_hours_lines=tuple(), name="")


async def resolve_profile_for_automation(
    venues: Sequence[Dict[str, Any]],
    payload: Optional[Dict[str, Any]],
    *,
    place_details_fn: Any,
) -> VenueTimeProfile:
    """
    Single chosen venue uses its snapshot row; fetch Places details if types/hours missing.
    Multiple venues with no place_id in payload uses conservative merge.
    """
    if not venues:
        return VenueTimeProfile(types=("restaurant",), opening_hours_lines=tuple(), name="")
    if payload and payload.get("place_id"):
        pid = str(payload.get("place_id") or "")
        row = next((v for v in venues if str(v.get("place_id") or "") == pid), None)
        if row is None and venues:
            row = venues[0]
        if row is None:
            return VenueTimeProfile(types=("restaurant",), opening_hours_lines=tuple(), name="")
        prof = venue_profile_from_snapshot_row(row)
        if prof.types and prof.opening_hours_lines:
            return prof
        if pid:
            detail = await place_details_fn(pid)
            if isinstance(detail, dict):
                types = [str(x) for x in (detail.get("types") or []) if isinstance(x, str)]
                oh = (
                    (detail.get("opening_hours") or {}).get("weekday_descriptions")
                    if isinstance(detail.get("opening_hours"), dict)
                    else None
                )
                lines: List[str] = []
                if isinstance(oh, list):
                    lines = [str(x).strip() for x in oh if isinstance(x, str) and str(x).strip()]
                if types or lines:
                    return VenueTimeProfile(
                        types=tuple(types) if types else prof.types,
                        opening_hours_lines=tuple(lines) if lines else prof.opening_hours_lines,
                        name=str(detail.get("name") or prof.name or row.get("name") or ""),
                    )
        return prof

    if len(venues) == 1:
        row = venues[0]
        prof = venue_profile_from_snapshot_row(row)
        pid = str(row.get("place_id") or "")
        if (not prof.types or not prof.opening_hours_lines) and pid:
            detail = await place_details_fn(pid)
            if isinstance(detail, dict):
                types = [str(x) for x in (detail.get("types") or []) if isinstance(x, str)]
                oh = (
                    (detail.get("opening_hours") or {}).get("weekday_descriptions")
                    if isinstance(detail.get("opening_hours"), dict)
                    else None
                )
                lines: List[str] = []
                if isinstance(oh, list):
                    lines = [str(x).strip() for x in oh if isinstance(x, str) and str(x).strip()]
                if types or lines:
                    return VenueTimeProfile(
                        types=tuple(types) if types else prof.types,
                        opening_hours_lines=tuple(lines) if lines else prof.opening_hours_lines,
                        name=str(detail.get("name") or prof.name or ""),
                    )
        return prof

    return conservative_profile_for_venue_list(list(venues))
