"""Resolve free-text place names to coordinates (Google Geocoding API)."""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


async def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """
    Returns (lat, lng) or None. Uses the same Maps key as Places; enable Geocoding API in GCP if needed.
    """
    q = (address or "").strip()
    key = (get_settings().google_places_api_key or "").strip()
    if not q or not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(_GEOCODE_URL, params={"address": q, "key": key})
            data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Geocoding HTTP/JSON error for %r: %s", q, e)
        return None
    if not isinstance(data, dict) or data.get("status") != "OK":
        logger.warning("Geocoding status %s for %r", data.get("status") if isinstance(data, dict) else None, q)
        return None
    results = data.get("results") or []
    if not results or not isinstance(results[0], dict):
        return None
    loc = (results[0].get("geometry") or {}).get("location") or {}
    lat, lng = loc.get("lat"), loc.get("lng")
    if lat is None or lng is None:
        return None
    return float(lat), float(lng)
