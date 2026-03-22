"""Turn DineSmartAI API responses into short plain-text summaries (e.g. WebSocket)."""

from __future__ import annotations

import re
from typing import List

from app.models.domain import RankedPick, RecommendResponse


def _pick_plain_lines(pick: RankedPick, title_line: str) -> List[str]:
    """Structured, comparable block for WebSocket / voice-style summaries."""
    r = pick.restaurant
    lines = [title_line]
    cuisine = pick.cuisine_display or (", ".join(r.cuisine_tags) if r.cuisine_tags else "—")
    lines.append(f"- Cuisine: {cuisine}")
    if r.rating is not None:
        lines.append(f"- Rating: {r.rating:.1f}")
    else:
        lines.append("- Rating: —")
    dist = pick.distance_or_time_display or "—"
    lines.append(f"- Distance / timing: {dist}")
    oh = (pick.opening_hours_display or "").strip()
    if oh:
        lines.append(f"- Hours:\n{oh}")
    lines.append(f"- Price: {pick.price_display or '—'}")
    lines.append(f"- Dietary fit: {pick.dietary_compatibility or '—'}")
    if pick.why:
        lines.append(f"- Why this fits: {pick.why}")
    if pick.next_actions:
        labels = [a.label for a in pick.next_actions if a.label]
        if labels:
            lines.append("- Quick actions: " + "; ".join(labels))
    return lines


def format_dining_reply(resp: RecommendResponse) -> str:
    """Plain, structured summary for WebSocket (same fields as UI cards)."""
    if resp.clarification:
        return resp.clarification

    p = resp.primary
    if not p:
        return "I could not find a strong match nearby. Try a different cuisine or area."

    sections: List[str] = []
    if resp.location_search_note:
        sections.append(resp.location_search_note)
    sections.append("\n".join(_pick_plain_lines(p, f"Best pick: {p.restaurant.name}")))
    for i, alt in enumerate(resp.alternates, start=1):
        sections.append(
            "\n".join(_pick_plain_lines(alt, f"Backup option {i}: {alt.restaurant.name}"))
        )
    body = "\n\n".join(sections)
    return (
        body
        + "\n\nSuggested next step: say if you want directions, to book or order "
        "(including having the agent call the venue after you confirm), or different options."
    )


def clean_summary(text: str) -> str:
    """Strip markdown and URLs; keep line breaks so structured picks stay scannable."""
    text = re.sub(r"^\s*#{1,6}\s*.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"^\s*\d+\.\s*", "", text, flags=re.MULTILINE)
    lines = text.splitlines()
    out: List[str] = []
    for line in lines:
        collapsed = re.sub(r"[ \t]+", " ", line).strip()
        if collapsed:
            out.append(collapsed)
    return "\n".join(out).strip()
