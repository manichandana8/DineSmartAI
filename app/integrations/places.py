from __future__ import annotations

import asyncio
import logging
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import get_settings
from app.models.domain import RestaurantCandidate
from app.services.location import haversine_m

logger = logging.getLogger(__name__)

PLACES_V1 = "https://places.googleapis.com/v1"
# Field mask: no spaces (Places API New requirement)
_SEARCH_FIELD_MASK = (
    "places.id,places.displayName,places.location,places.rating,places.userRatingCount,"
    "places.priceLevel,places.types,places.formattedAddress"
)
_DETAILS_FIELD_MASK = (
    "id,displayName,location,rating,userRatingCount,priceLevel,types,formattedAddress,"
    "nationalPhoneNumber,websiteUri,currentOpeningHours,reviews,editorialSummary"
)


def _types_to_cuisine(types: List[str]) -> List[str]:
    mapping = {
        "italian_restaurant": "Italian",
        "mexican_restaurant": "Mexican",
        "japanese_restaurant": "Japanese",
        "chinese_restaurant": "Chinese",
        "indian_restaurant": "Indian",
        "thai_restaurant": "Thai",
        "american_restaurant": "American",
        "pizza_restaurant": "Pizza",
        "seafood_restaurant": "Seafood",
        "sushi_restaurant": "Sushi",
        "vegetarian_restaurant": "Vegetarian",
        "vegan_restaurant": "Vegan",
        "mediterranean_restaurant": "Mediterranean",
        "french_restaurant": "French",
        "korean_restaurant": "Korean",
        "vietnamese_restaurant": "Vietnamese",
    }
    out: List[str] = []
    for t in types:
        if t in mapping:
            out.append(mapping[t])
    if not out and types:
        out.append(types[0].replace("_", " ").title())
    return out[:5]


def _localized_text(node: Any) -> str:
    if isinstance(node, dict) and node.get("text"):
        return str(node["text"])
    if isinstance(node, str):
        return node
    return ""


def _price_level_to_legacy(raw: Any) -> Optional[int]:
    """Maps Places API (New) priceLevel enum string to legacy 0–4 integer."""
    if raw is None:
        return None
    if isinstance(raw, int) and 0 <= raw <= 4:
        return raw
    s = str(raw).upper()
    if "VERY_EXPENSIVE" in s:
        return 4
    if "INEXPENSIVE" in s:
        return 1
    if "MODERATE" in s:
        return 2
    # Must run after INEXPENSIVE: that string also contains "EXPENSIVE".
    if "EXPENSIVE" in s:
        return 3
    if "FREE" in s:
        return 0
    return None


def _place_v1_to_search_row(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    loc = p.get("location") or {}
    pid = p.get("id")
    lat, lng = loc.get("latitude"), loc.get("longitude")
    if not pid or lat is None or lng is None:
        return None
    return {
        "place_id": str(pid),
        "name": _localized_text(p.get("displayName")) or "Unknown",
        "lat": float(lat),
        "lng": float(lng),
        "rating": p.get("rating"),
        "user_ratings_total": p.get("userRatingCount"),
        "price_level": _price_level_to_legacy(p.get("priceLevel")),
        "types": list(p.get("types") or []),
        "vicinity": p.get("formattedAddress"),
    }


def _api_key() -> str:
    return (get_settings().google_places_api_key or "").strip()


def _places_error_message(data: Any, fallback: str) -> str:
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
    return fallback


async def _post_places_v1(path: str, body: dict, field_mask: str) -> Tuple[Optional[dict], Optional[str]]:
    key = _api_key()
    if not key:
        return None, "missing_key"

    url = f"{PLACES_V1}{path}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": field_mask,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(url, json=body, headers=headers)
            data = r.json()
    except httpx.HTTPError as e:
        logger.exception("Google Places (New) HTTP error")
        return None, f"Could not reach Google Places: {e}"
    except ValueError:
        return None, "Invalid JSON from Google Places."

    if r.status_code >= 400:
        msg = _places_error_message(data, r.text[:400] if r.text else r.reason_phrase)
        logger.error("Google Places (New) %s: %s", r.status_code, msg)
        return None, msg

    return data if isinstance(data, dict) else None, None


def _rows_from_places_payload(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in data.get("places") or []:
        if not isinstance(item, dict):
            continue
        row = _place_v1_to_search_row(item)
        if row:
            rows.append(row)
    return rows


def _merge_place_rows(
    first: List[Dict[str, Any]],
    second: List[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in first + second:
        pid = row.get("place_id")
        if not pid or pid in seen:
            continue
        seen.add(str(pid))
        out.append(row)
        if len(out) >= limit:
            break
    return out


async def nearby_search(
    lat: float,
    lng: float,
    radius_m: int,
    keyword: Optional[str],
    max_results: int = 20,
    visit_category: str = "meal",
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Returns (places, error_message). Uses Places API (New): searchNearby or searchText.
    visit_category switches included primary type (restaurant vs ice_cream_shop vs cafe, etc.).
    """
    from app.agents.visit_category import normalize_visit_category, places_search_params

    key = _api_key()
    if not key:
        logger.warning("GOOGLE_PLACES_API_KEY is empty — no restaurant results.")
        return [], (
            "Google Places API key is not configured. Add GOOGLE_PLACES_API_KEY to your .env file "
            "(project root, next to main.py), enable Places API (New) and billing in Google Cloud, then restart. "
            "Open /debug/places to verify the key."
        )

    n = max(1, min(max_results, 20))
    radius = float(max(1, min(radius_m, 50000)))
    center = {"latitude": float(lat), "longitude": float(lng)}
    circle = {"center": center, "radius": radius}

    vc = normalize_visit_category(visit_category)
    cfg = places_search_params(vc)
    included_type = str(cfg["included_type"])
    strict = bool(cfg["strict"])
    kw_part = (keyword or "").strip()
    tmpl = str(cfg["text_template"])
    if kw_part:
        text_query = tmpl.format(kw=kw_part).strip()
    else:
        text_query = str(cfg["fallback_text"]).strip()

    if text_query:
        body = {
            "textQuery": text_query,
            "includedType": included_type,
            "strictTypeFiltering": strict,
            "pageSize": n,
            "locationBias": {"circle": circle},
        }
        data, err = await _post_places_v1("/places:searchText", body, _SEARCH_FIELD_MASK)
    else:
        body = {
            "includedTypes": [included_type],
            "maxResultCount": n,
            "locationRestriction": {"circle": circle},
        }
        data, err = await _post_places_v1("/places:searchNearby", body, _SEARCH_FIELD_MASK)

    if err == "missing_key":
        return [], (
            "Google Places API key is not configured. Add GOOGLE_PLACES_API_KEY to your .env file "
            "(project root, next to main.py), enable Places API (New) and billing in Google Cloud, then restart. "
            "Open /debug/places to verify the key."
        )
    if err:
        hint = (
            " In Google Cloud Console enable **Places API (New)** (not only the legacy Places API), "
            "enable billing, and allow this key to call Places API (New)."
        )
        if "legacy" in err.lower() or "not enabled" in err.lower():
            return [], (
                "Google Places: " + err + hint + " See https://developers.google.com/maps/documentation/places/web-service/op-overview"
            )
        if "permission" in err.lower() or "denied" in err.lower() or "api key" in err.lower():
            return [], "Google Places: " + err + hint
        return [], "Google Places: " + err

    assert data is not None
    out = _rows_from_places_payload(data)

    # Boba: cafés/tea shops first, then restaurants that sell bubble tea (same text query, broader type).
    if vc == "boba" and text_query:
        body_boba_restaurant = {
            "textQuery": text_query,
            "includedType": "restaurant",
            "strictTypeFiltering": False,
            "pageSize": n,
            "locationBias": {"circle": circle},
        }
        data_r, err_r = await _post_places_v1(
            "/places:searchText", body_boba_restaurant, _SEARCH_FIELD_MASK
        )
        if not err_r and isinstance(data_r, dict):
            extra = _rows_from_places_payload(data_r)
            out = _merge_place_rows(out, extra, n)

    return out[:n], None


def _parse_current_opening_hours(coh: Any) -> tuple[Optional[bool], List[str]]:
    """Extract openNow and weekday description lines from Places API (New) currentOpeningHours."""
    if not isinstance(coh, dict):
        return None, []
    on_raw = coh.get("openNow")
    open_now: Optional[bool]
    if isinstance(on_raw, bool):
        open_now = on_raw
    else:
        open_now = None
    lines: List[str] = []
    wd = coh.get("weekdayDescriptions")
    if isinstance(wd, list):
        for x in wd:
            if isinstance(x, str) and x.strip():
                lines.append(x.strip())
    return open_now, lines


async def place_details(place_id: str) -> Optional[Dict[str, Any]]:
    key = _api_key()
    if not key or not place_id:
        return None

    enc = urllib.parse.quote(place_id, safe="")
    url = f"{PLACES_V1}/places/{enc}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": _DETAILS_FIELD_MASK,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url, headers=headers)
            data = r.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Google Place Details (New) failed")
        return None

    if r.status_code >= 400 or not isinstance(data, dict):
        return None

    loc = data.get("location") or {}
    es = data.get("editorialSummary")
    overview = _localized_text(es) if es else ""

    reviews_out: List[Dict[str, str]] = []
    for rv in (data.get("reviews") or [])[:6]:
        if isinstance(rv, dict):
            t = _localized_text(rv.get("text") or rv.get("originalText"))
            if t:
                reviews_out.append({"text": t})

    coh = data.get("currentOpeningHours")
    open_now, weekday_lines = _parse_current_opening_hours(coh)

    return {
        "name": _localized_text(data.get("displayName")),
        "geometry": {
            "location": {
                "lat": loc.get("latitude"),
                "lng": loc.get("longitude"),
            }
        },
        "rating": data.get("rating"),
        "user_ratings_total": data.get("userRatingCount"),
        "price_level": _price_level_to_legacy(data.get("priceLevel")),
        "types": list(data.get("types") or []),
        "formatted_address": data.get("formattedAddress"),
        "formatted_phone_number": data.get("nationalPhoneNumber"),
        "website": data.get("websiteUri"),
        "opening_hours": {
            **({"open_now": open_now} if open_now is not None else {}),
            "weekday_descriptions": weekday_lines,
        },
        "reviews": reviews_out,
        "editorial_summary": ({"overview": overview} if overview else None),
    }


def candidate_from_place(
    base: Dict[str, Any],
    user_lat: float,
    user_lng: float,
) -> RestaurantCandidate:
    lat, lng = float(base["lat"]), float(base["lng"])
    dist = haversine_m(user_lat, user_lng, lat, lng)
    types = list(base.get("types") or [])
    tags = _types_to_cuisine(types)
    rating = base.get("rating")
    return RestaurantCandidate(
        place_id=str(base["place_id"]),
        name=str(base.get("name") or "Unknown"),
        lat=lat,
        lng=lng,
        cuisine_tags=tags,
        price_level=base.get("price_level"),
        rating=float(rating) if rating is not None else None,
        review_count=int(base.get("user_ratings_total") or 0),
        distance_m=dist,
        types=types,
        address=base.get("vicinity") or base.get("formatted_address"),
        menu_items=[],
    )


async def enrich_candidate(
    c: RestaurantCandidate,
    user_lat: float,
    user_lng: float,
) -> RestaurantCandidate:
    detail = await place_details(c.place_id)
    if not detail:
        return c

    loc = (detail.get("geometry") or {}).get("location") or {}
    if loc.get("lat") is not None and loc.get("lng") is not None:
        c.lat = float(loc["lat"])
        c.lng = float(loc["lng"])
        c.distance_m = haversine_m(user_lat, user_lng, c.lat, c.lng)

    if detail.get("rating") is not None:
        c.rating = float(detail["rating"])
    c.review_count = int(detail.get("user_ratings_total") or c.review_count)
    if detail.get("price_level") is not None:
        c.price_level = detail.get("price_level")
    c.types = list(detail.get("types") or c.types)
    c.address = detail.get("formatted_address") or c.address
    c.website = detail.get("website")
    c.phone = detail.get("formatted_phone_number") or c.phone
    es = detail.get("editorial_summary")
    if isinstance(es, dict):
        c.editorial_summary = es.get("overview")
    elif isinstance(es, str):
        c.editorial_summary = es

    snippets: List[str] = []
    for rv in detail.get("reviews") or []:
        if isinstance(rv, dict) and rv.get("text"):
            snippets.append(str(rv["text"]).replace("\n", " "))
    c.review_snippets = snippets

    oh = detail.get("opening_hours") or {}
    c.open_now = bool(oh.get("open_now")) if isinstance(oh, dict) and "open_now" in oh else c.open_now
    wd = oh.get("weekday_descriptions") if isinstance(oh, dict) else None
    if isinstance(wd, list):
        c.opening_hours_lines = [str(x).strip() for x in wd if isinstance(x, str) and str(x).strip()]

    c.cuisine_tags = _types_to_cuisine(c.types) or c.cuisine_tags
    return c


async def enrich_many(
    candidates: List[RestaurantCandidate],
    user_lat: float,
    user_lng: float,
    concurrency: int = 5,
) -> List[RestaurantCandidate]:
    sem = asyncio.Semaphore(concurrency)

    async def one(x: RestaurantCandidate) -> RestaurantCandidate:
        async with sem:
            return await enrich_candidate(x, user_lat, user_lng)

    return await asyncio.gather(*[one(c) for c in candidates])
