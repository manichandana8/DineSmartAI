from __future__ import annotations

import html
import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.api.deps import SessionDep
from app.services.booking_confirmation import get_booking_by_code

router = APIRouter(tags=["bookings"])


def _details_dict(row_details: str) -> Dict[str, Any]:
    try:
        d = json.loads(row_details or "{}")
        return d if isinstance(d, dict) else {}
    except json.JSONDecodeError:
        return {}


def _status_explanation(status: str, action_kind: str) -> str:
    kind = "reservation" if action_kind == "reserve_table" else "order"
    if status == "call_started":
        return (
            f"We started an outbound call to the venue for your {kind}. "
            "Final confirmation still depends on the restaurant answering and agreeing—check back here for updates you paste from SMS or email."
        )
    if status == "queued_simulated":
        return (
            f"Your {kind} request is saved. Retell AI is not fully configured (or this is demo mode), "
            "so no live call was placed. Configure RETELL_API_KEY and numbers to reach the venue by phone automatically."
        )
    if status == "self_service":
        return (
            "You chose self-service: use the Maps and booking links from the chat to finish on the venue’s site or by phone."
        )
    if status == "missing_phone":
        return "We could not find a phone number for this place in Google Places—try the venue’s website or call them directly."
    return "This request is on file. If something failed, start a new search in the assistant or use the venue’s official channels."


@router.get("/bookings/{code}", include_in_schema=False, response_class=HTMLResponse)
def booking_portal_page(code: str, session: SessionDep) -> str:
    row = get_booking_by_code(session, code)
    if not row:
        raise HTTPException(status_code=404, detail="Booking reference not found.")
    d = _details_dict(row.details_json)
    when = html.escape(str(d.get("when_line") or "—"))
    party = html.escape(str(d.get("party") or "—"))
    venue = html.escape(row.venue_name or "")
    st = html.escape(row.status.replace("_", " ").title())
    explain = html.escape(_status_explanation(row.status, row.action_kind))
    retell = html.escape(row.retell_call_id or "—")
    created = row.created_at.strftime("%Y-%m-%d %H:%M UTC") if row.created_at else "—"

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>DineSmartAI — Booking {html.escape(row.confirmation_code)}</title>
<style>
body{{font-family:"DM Sans",system-ui,sans-serif;margin:0;background:#e8f2ec;color:#1a2e28;
  background-image:radial-gradient(ellipse 100% 80% at 50% -30%,rgba(244,168,184,.18),transparent),
  radial-gradient(ellipse 70% 50% at 100% 0%,rgba(168,205,184,.35),transparent);min-height:100dvh;padding:1.5rem;}}
.wrap{{max-width:520px;margin:0 auto;background:rgba(255,255,255,.85);backdrop-filter:blur(12px);
  border-radius:1.25rem;padding:1.5rem 1.35rem;border:1px solid rgba(255,255,255,.8);
  box-shadow:0 4px 24px -4px rgba(26,46,40,.08);}}
h1{{font-family:Fraunces,Georgia,serif;font-size:1.35rem;margin:0 0 .35rem;font-weight:600;}}
.ref{{font-size:.85rem;color:#6b756f;margin-bottom:1rem;}}
.ref strong{{color:#417459;}}
dl{{margin:0;font-size:.92rem;line-height:1.5;}}
dt{{color:#6b756f;font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;margin-top:.75rem;}}
dd{{margin:.15rem 0 0 0;font-weight:600;}}
.note{{margin-top:1.1rem;padding:.85rem 1rem;background:rgba(244,168,184,.15);border-radius:.75rem;
  font-size:.88rem;line-height:1.45;color:#1a2e28;border:1px solid rgba(236,122,148,.25);}}
.footer{{margin-top:1.25rem;font-size:.78rem;color:#6b756f;}}
a{{color:#417459;font-weight:600;}}
</style>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,600;0,9..40,700&family=Fraunces:opsz,wght@9..144,600&display=swap" rel="stylesheet"/>
</head><body>
<div class="wrap">
  <h1>Booking status</h1>
  <p class="ref">Reference <strong>{html.escape(row.confirmation_code)}</strong> · {html.escape(created)}</p>
  <dl>
    <dt>Venue</dt><dd>{venue}</dd>
    <dt>When</dt><dd>{when}</dd>
    <dt>Guests</dt><dd>{party}</dd>
    <dt>Status</dt><dd>{st}</dd>
    <dt>Call / job id</dt><dd>{retell}</dd>
  </dl>
  <p class="note">{explain}</p>
  <p class="footer"><a href="/assistant">← Back to DineSmartAI assistant</a></p>
</div>
</body></html>"""


@router.get("/v1/bookings/{code}", include_in_schema=True)
def booking_portal_json(code: str, session: SessionDep) -> dict:
    row = get_booking_by_code(session, code)
    if not row:
        raise HTTPException(status_code=404, detail="Booking reference not found.")
    d = _details_dict(row.details_json)
    return {
        "confirmation_code": row.confirmation_code,
        "venue_name": row.venue_name,
        "place_id": row.place_id,
        "action_kind": row.action_kind,
        "status": row.status,
        "retell_mode": row.retell_mode,
        "retell_call_id": row.retell_call_id,
        "details": d,
        "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
        "email_sent_at": row.email_sent_at.isoformat() + "Z" if row.email_sent_at else None,
    }
