"""
Retell AI outbound calls — primary execution path when the user asks DineSmartAI to book/order by phone.

API: POST https://api.retellai.com/v2/create-phone-call (Bearer token).
Requires RETELL_API_KEY and RETELL_FROM_NUMBER; optional RETELL_AGENT_ID (override_agent_id).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_RETELL_CREATE_CALL = "https://api.retellai.com/v2/create-phone-call"


@dataclass(frozen=True)
class RetellCallOutcome:
    ok: bool
    mode: str  # "live" | "simulated" | "skipped"
    summary: str
    call_id: Optional[str] = None
    call_status: Optional[str] = None
    error: Optional[str] = None


def normalize_phone_e164_us(raw: Optional[str]) -> Optional[str]:
    """Best-effort E.164 from Places nationalPhoneNumber (US-centric +1 if 10 digits)."""
    if not raw:
        return None
    s = str(raw).strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) < 10:
        return None
    if s.startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits


def _dynamic_vars_for_dining(
    venue_name: str,
    action_kind: str,
    payload: Dict[str, Any],
) -> Dict[str, str]:
    """Inject into Retell LLM prompt — tune your agent to read these variable names."""
    out: Dict[str, str] = {
        "venue_name": venue_name[:200],
        "action_kind": action_kind,
        "party": str(payload.get("party") or ""),
        "date_phrase": str(payload.get("date_phrase") or ""),
        "time_phrase": str(payload.get("time_phrase") or ""),
        "when_line": str(payload.get("when_line") or ""),
        "order_items": str(payload.get("order_items") or ""),
    }
    return {k: v for k, v in out.items() if v}


async def initiate_dining_call(
    *,
    to_number_e164: Optional[str],
    venue_name: str,
    action_kind: str,
    payload: Dict[str, Any],
    user_id: str,
    place_id: str,
) -> RetellCallOutcome:
    """
    Start an outbound Retell call when configured; otherwise return a clear simulated outcome.
    """
    settings = get_settings()
    key = (settings.retell_api_key or "").strip()
    from_num = (settings.retell_from_number or "").strip()
    agent_id = (settings.retell_agent_id or "").strip()

    dyn = _dynamic_vars_for_dining(venue_name, action_kind, payload)
    metadata: Dict[str, Any] = {
        "smartdine_user_id": user_id,
        "place_id": place_id,
        "venue_name": venue_name,
        "action_kind": action_kind,
    }

    if not to_number_e164:
        return RetellCallOutcome(
            ok=False,
            mode="skipped",
            summary=(
                f"No callable phone number on file for {venue_name}. "
                "Add or verify the venue’s phone in Google Places, or complete booking using the optional links in the app."
            ),
            error="missing_phone",
        )

    if not key or not from_num:
        if action_kind == "place_order":
            sim = (
                f"Your order for {venue_name} is queued. In production, DineSmartAI would call the restaurant "
                f"at {to_number_e164} to read back items and confirm pickup or timing."
            )
        else:
            sim = (
                f"Your reservation for {venue_name} is queued. In production, DineSmartAI would call the venue "
                f"at {to_number_e164} to confirm date, time, and party size."
            )
        return RetellCallOutcome(ok=True, mode="simulated", summary=sim)

    body: Dict[str, Any] = {
        "from_number": from_num,
        "to_number": to_number_e164,
        "metadata": metadata,
        "retell_llm_dynamic_variables": {k: str(v)[:500] for k, v in dyn.items()},
    }
    if agent_id:
        body["override_agent_id"] = agent_id

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(_RETELL_CREATE_CALL, json=body, headers=headers)
            data = r.json() if r.content else {}
    except (httpx.HTTPError, ValueError) as e:
        logger.exception("Retell create-phone-call failed")
        return RetellCallOutcome(
            ok=False,
            mode="skipped",
            summary="Could not reach Retell AI to start the call. Try again or use the optional booking links.",
            error=str(e),
        )

    if r.status_code >= 400:
        msg = data.get("message") if isinstance(data, dict) else r.text
        logger.error("Retell API error %s: %s", r.status_code, msg)
        return RetellCallOutcome(
            ok=False,
            mode="skipped",
            summary=f"Retell AI declined the call ({r.status_code}). Check API key, numbers, and dashboard limits.",
            error=str(msg)[:300],
        )

    if not isinstance(data, dict):
        return RetellCallOutcome(
            ok=False,
            mode="skipped",
            summary="Unexpected response from Retell AI.",
            error="bad_json",
        )

    cid = data.get("call_id")
    st = data.get("call_status")
    goal = "confirm your reservation" if action_kind == "reserve_table" else "place your order"
    return RetellCallOutcome(
        ok=True,
        mode="live",
        summary=(
            f"Started a call to {venue_name} to {goal}. "
            f"Reference: {cid}. We’ll update you when the restaurant responds."
        ),
        call_id=str(cid) if cid else None,
        call_status=str(st) if st else None,
    )
