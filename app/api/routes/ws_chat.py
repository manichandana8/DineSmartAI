"""
WebSocket chat for conversational DineSmartAI clients.

Message types (JSON text frames):
- dine_query: run full recommendation pipeline
"""

from __future__ import annotations

import json
import math

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from app.db import engine
from app.models.domain import RecommendRequest
from app.services.conversation import clean_summary, format_dining_reply
from app.services.recommendation import run_recommendation

router = APIRouter(tags=["websocket"])


def _parse_lon_lat(payload: dict) -> tuple[float | None, float | None, str]:
    """Returns (lat, lng, \"\") on success, or (None, None, error_message)."""
    raw_lat = payload.get("latitude")
    raw_lng = payload.get("longitude")
    if raw_lat is None or raw_lng is None:
        return None, None, "latitude and longitude are required (numbers)."
    try:
        lat = float(raw_lat)
        lng = float(raw_lng)
    except (TypeError, ValueError):
        return None, None, "latitude and longitude must be numeric (e.g. 37.67, -122.08)."
    if not math.isfinite(lat) or not math.isfinite(lng):
        return None, None, "latitude and longitude must be finite numbers."
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None, None, "latitude must be between -90 and 90, longitude between -180 and 180."
    return lat, lng, ""


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "content": "Invalid JSON"})
                )
                continue

            msg_type = payload.get("type")

            if msg_type == "dine_query":
                await _handle_dine_query(websocket, payload)
            else:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "content": f"Unknown type: {msg_type}. Use dine_query.",
                        }
                    )
                )
    except WebSocketDisconnect:
        pass


async def _handle_dine_query(websocket: WebSocket, payload: dict) -> None:
    text = (payload.get("text") or "").strip()
    lat, lng, coord_err = _parse_lon_lat(payload)
    if coord_err:
        await websocket.send_text(
            json.dumps({"type": "error", "content": coord_err})
        )
        return
    user_id = payload.get("user_id") or "demo"

    req = RecommendRequest(
        message=text,
        latitude=lat,
        longitude=lng,
        user_id=user_id,
    )
    with Session(engine) as session:
        resp = await run_recommendation(req, session)

    data = json.loads(resp.model_dump_json())
    summary = clean_summary(format_dining_reply(resp))

    await websocket.send_text(
        json.dumps(
            {
                "type": "smartdine_result",
                "summary": summary,
                "payload": data,
            }
        )
    )
