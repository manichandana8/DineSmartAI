from __future__ import annotations

import urllib.parse

from app.models.domain import NextAction, RestaurantCandidate, UserIntent


def plan_next_actions(
    intent: UserIntent,
    restaurant: RestaurantCandidate,
) -> list[NextAction]:
    lat, lng = restaurant.lat, restaurant.lng
    name = restaurant.name

    maps_url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"
    reserve_url = (
        f"https://www.google.com/search?q={urllib.parse.quote_plus(name + ' reserve table')}"
    )
    delivery_url = (
        f"https://www.google.com/search?q={urllib.parse.quote_plus(name + ' order delivery')}"
    )
    pickup_url = (
        f"https://www.google.com/search?q={urllib.parse.quote_plus(name + ' order pickup')}"
    )

    reserve_snippet = (
        f"Reserve at {name} — use the DineSmartAI agent to call the restaurant for me "
        f"(party size, date, time). I want agent-handled booking, not just links."
    )
    order_snippet = (
        f"Place a pickup order at {name} through DineSmartAI — have the agent call the restaurant for me with my items."
    )
    either_snippet = (
        f"Use the DineSmartAI agent to call {name} for me to reserve a table or arrange pickup—"
        f"I want agent-handled execution, not only website links."
    )
    if intent.mode == "dine_in":
        agent_reply = reserve_snippet
    elif intent.mode in ("delivery", "pickup"):
        agent_reply = order_snippet
    else:
        agent_reply = either_snippet

    actions: list[NextAction] = [
        NextAction(
            action="agent_execute",
            label="Book / order via DineSmartAI agent",
            url=None,
            notes=(
                "DineSmartAI can call the venue on your behalf (Retell AI) after you confirm details—Yes/No. "
                "Say you want the agent to handle it even if they have online booking."
            ),
            suggested_reply=agent_reply,
        ),
        NextAction(
            action="navigate",
            label="Navigate",
            url=maps_url,
            notes="Opens directions in Google Maps (same URL pattern works on mobile).",
        ),
    ]

    if intent.mode == "delivery":
        actions.append(
            NextAction(
                action="delivery",
                label="Optional: order delivery (self-service)",
                url=delivery_url,
                notes="Only if you prefer apps or the restaurant site yourself—the agent path can still call for you.",
            )
        )
    elif intent.mode == "pickup":
        actions.append(
            NextAction(
                action="pickup",
                label="Optional: pickup / order online (self-service)",
                url=pickup_url,
                notes="Use if you want to click through yourself; agent execution is still available first.",
            )
        )
    elif intent.mode == "dine_in":
        actions.append(
            NextAction(
                action="reserve",
                label="Optional: reservation links (self-service)",
                url=reserve_url,
                notes="OpenTable / Google Reserve / Yelp—secondary if you chose not to use the agent.",
            )
        )
    else:
        actions.append(
            NextAction(
                action="reserve",
                label="Optional: reserve / call ahead (self-service)",
                url=reserve_url,
                notes="Secondary self-service; DineSmartAI agent can still place the call.",
            )
        )
        actions.append(
            NextAction(
                action="pickup",
                label="Optional: pickup or delivery (self-service)",
                url=pickup_url,
                notes="Compare pickup vs delivery if you are handling it yourself.",
            )
        )

    if restaurant.website:
        actions.append(
            NextAction(
                action="call",
                label="Optional: website / menu",
                url=restaurant.website,
                notes="Menu and contact—does not replace agent-handled booking when you ask DineSmartAI to act.",
            )
        )

    return actions[:6]
