"""Persist booking requests after user confirms; optional email (Resend) and customer portal link."""

from __future__ import annotations

import json
import logging
import secrets
import string
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlmodel import Session, select

from app.config import get_settings
from app.integrations.retell import RetellCallOutcome
from app.models.db import BookingRecord
from app.services.memory import get_or_create_profile

logger = logging.getLogger(__name__)

_RESEND_API = "https://api.resend.com/emails"


def _generate_confirmation_code(session: Session) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(12):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        existing = session.exec(select(BookingRecord).where(BookingRecord.confirmation_code == code)).first()
        if not existing:
            return code
    return secrets.token_hex(4).upper()[:8]


def _booking_status_from_outcome(outcome: Optional[RetellCallOutcome], self_service: bool) -> str:
    if self_service:
        return "self_service"
    if not outcome:
        return "unknown"
    if outcome.mode == "live" and outcome.ok:
        return "call_started"
    if outcome.mode == "simulated" and outcome.ok:
        return "queued_simulated"
    if outcome.error == "missing_phone":
        return "missing_phone"
    return "paused"


def _portal_url(code: str) -> str:
    base = (get_settings().public_base_url or "").rstrip("/")
    if not base:
        base = "http://127.0.0.1:8000"
    return f"{base}/bookings/{code}"


def _notify_recipients(session: Session, user_id: str) -> List[str]:
    settings = get_settings()
    out: List[str] = []
    demo = (settings.booking_demo_notify_email or "").strip()
    if demo:
        out.append(demo)
    p = get_or_create_profile(session, user_id)
    em = (getattr(p, "contact_email", None) or "").strip()
    if em and em not in out:
        out.append(em)
    return out


async def _send_resend_html(to_list: List[str], subject: str, html: str) -> bool:
    settings = get_settings()
    key = (settings.resend_api_key or "").strip()
    from_addr = (settings.booking_from_email or "").strip() or "onboarding@resend.dev"
    if not key or not to_list:
        return False
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body: Dict[str, Any] = {
        "from": f"DineSmartAI <{from_addr}>",
        "to": to_list[:5],
        "subject": subject[:200],
        "html": html,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(_RESEND_API, json=body, headers=headers)
        if r.status_code >= 400:
            logger.warning("Resend email failed %s: %s", r.status_code, r.text[:500])
            return False
        return True
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Resend email error: %s", e)
        return False


async def record_booking_and_maybe_email(
    session: Session,
    user_id: str,
    payload: Dict[str, Any],
    outcome: Optional[RetellCallOutcome],
    action: str,
    *,
    self_service: bool = False,
) -> Dict[str, Any]:
    """
    Save a booking row and optionally email the customer (Resend + profile / demo inbox).
    Returns confirmation_code, portal_url, email_sent.
    """
    import uuid

    vname = str(payload.get("venue_name") or "Venue")
    place_id = str(payload.get("place_id") or "")
    code = _generate_confirmation_code(session)
    status = _booking_status_from_outcome(outcome, self_service)
    details = {
        "when_line": payload.get("when_line"),
        "party": payload.get("party"),
        "date_phrase": payload.get("date_phrase"),
        "time_phrase": payload.get("time_phrase"),
        "order_items": payload.get("order_items"),
        "venue_summary": (outcome.summary if outcome else None),
    }
    retell_mode = outcome.mode if outcome else ""
    retell_call_id = outcome.call_id if outcome and outcome.ok else None

    row = BookingRecord(
        id=str(uuid.uuid4()),
        confirmation_code=code,
        user_id=user_id,
        venue_name=vname[:500],
        place_id=place_id[:200],
        action_kind=action,
        status=status,
        retell_mode=retell_mode or ("self_service" if self_service else ""),
        retell_call_id=retell_call_id,
        details_json=json.dumps(details, ensure_ascii=False)[:8000],
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    portal = _portal_url(code)
    recipients = _notify_recipients(session, user_id)
    email_sent = False
    if recipients:
        subj = f"DineSmartAI — {('Reservation' if action == 'reserve_table' else 'Order')} request · {code}"
        html = f"""
        <div style="font-family:system-ui,sans-serif;max-width:520px;line-height:1.5;color:#1a2e28">
          <h2 style="margin:0 0 0.5rem">Booking update</h2>
          <p>Reference: <strong>{code}</strong></p>
          <p><strong>{vname}</strong></p>
          <p>Status: <strong>{status.replace('_', ' ')}</strong></p>
          <p>View details anytime:<br><a href="{portal}">{portal}</a></p>
          <p style="font-size:0.9rem;color:#6b756f">DineSmartAI connects to the venue by phone when Retell AI is configured.
          Simulated mode stores your request for demo and testing.</p>
        </div>
        """
        email_sent = await _send_resend_html(recipients, subj, html)
        if email_sent:
            row.email_sent_at = datetime.utcnow()
            session.add(row)
            session.commit()

    return {
        "confirmation_code": code,
        "portal_url": portal,
        "email_sent": email_sent,
    }


def get_booking_by_code(session: Session, code: str) -> Optional[BookingRecord]:
    c = (code or "").strip().upper()
    if len(c) < 6:
        return None
    return session.exec(select(BookingRecord).where(BookingRecord.confirmation_code == c)).first()
