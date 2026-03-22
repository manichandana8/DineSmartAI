"""One-click check: is the Places key loaded and does Places API (New) respond?"""

from __future__ import annotations

import httpx
from fastapi import APIRouter

from app.config import _ENV_FILE, get_settings

router = APIRouter(prefix="/v1/diagnostics", tags=["diagnostics"])

PLACES_V1 = "https://places.googleapis.com/v1"
_DIAG_FIELD_MASK = (
    "places.id,places.displayName,places.location,places.types,places.formattedAddress"
)


async def run_google_places_diagnostic() -> dict:
    """
    Shared logic for all diagnostics URLs. Does not expose your API key.
    Uses Places API (New) searchNearby (same stack as the app).
    """
    s = get_settings()
    key = (s.google_places_api_key or "").strip()

    base: dict = {
        "api": "places_new",
        "env_file_path": str(_ENV_FILE),
        "env_file_exists": _ENV_FILE.is_file(),
        "api_key_configured": bool(key),
        "api_key_length": len(key),
        "http_status": None,
        "google_error_message": None,
        "results_count": None,
        "fix_steps": [],
    }

    if not _ENV_FILE.is_file():
        base["fix_steps"].append(
            f"Create a file at {_ENV_FILE} with: GOOGLE_PLACES_API_KEY=your_key"
        )

    if not key:
        base["fix_steps"].extend(
            [
                "Set GOOGLE_PLACES_API_KEY in .env (same folder as main.py), no spaces around =.",
                "Restart the server after saving .env.",
                "If you use `export GOOGLE_PLACES_API_KEY=` in the terminal, remove it or leave it unset — an empty export can block .env.",
                "Enable **Places API (New)** (not legacy Places API) and billing on your Google Cloud project.",
            ]
        )
        return base

    body = {
        "includedTypes": ["restaurant"],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": 37.6688, "longitude": -122.0808},
                "radius": 1500.0,
            }
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": _DIAG_FIELD_MASK,
    }
    r = None  # httpx.Response
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(f"{PLACES_V1}/places:searchNearby", json=body, headers=headers)
            data = r.json() if r.content else {}
    except httpx.HTTPError as e:
        base["http_status"] = "HTTP_ERROR"
        base["google_error_message"] = str(e)
        base["fix_steps"].append("Network/firewall blocked the request to Google.")
        return base
    except ValueError:
        base["http_status"] = getattr(r, "status_code", None)
        base["google_error_message"] = "Invalid JSON from Google."
        return base

    base["http_status"] = r.status_code
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            base["google_error_message"] = str(err["message"])
        places = data.get("places") or []
        base["results_count"] = len(places) if isinstance(places, list) else 0

    if r.status_code >= 400:
        base["fix_steps"].extend(
            [
                "Google Cloud → APIs & Services → enable **Places API (New)** for this project.",
                "Billing must be enabled on the project.",
                "Credentials → API key → restrict to Places API (New) or use no API restriction while testing.",
                "Legacy “Places API” alone is not enough if Google returns legacy API errors — enable the New product.",
            ]
        )
        return base

    if base["results_count"] == 0:
        base["fix_steps"].append(
            "Request succeeded but no restaurants in the test circle. Try another area in the chat."
        )
    else:
        base["fix_steps"].append("Places API (New) is working.")

    return base


@router.get("/google-places")
async def google_places_check() -> dict:
    return await run_google_places_diagnostic()
