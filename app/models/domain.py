from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field



DietaryStyle = Literal["vegetarian", "vegan", "pescatarian", "omnivore", "any", "eggtarian"]
MealIntent = Literal["quick", "relaxed", "indulgent", "healthy", "any"]
SpiceTolerance = Literal["mild", "medium", "hot", "any"]
VisitCategory = Literal[
    "meal",
    "snack",
    "dessert",
    "ice_cream",
    "beverages",
    "coffee",
    "boba",
    "bakery",
    "fast_food",
    "fine_dining",
]


class UserIntent(BaseModel):
    cuisine: Optional[str] = None
    mood: Optional[str] = None
    budget: Literal["low", "medium", "high", "any"] = "any"
    """Restrictions and labels: gluten-free, dairy-free, egg-free, halal, kosher, vegetarian, vegan, etc."""
    dietary: List[str] = Field(default_factory=list)
    disliked_ingredients: List[str] = Field(default_factory=list)
    urgency: Literal["now", "soon", "flexible"] = "flexible"
    mode: Literal["dine_in", "delivery", "pickup", "either"] = "either"
    party_size: Optional[int] = None
    needs_clarification: bool = False
    clarifying_question: Optional[str] = None
    raw_text: str = ""

    dietary_style: DietaryStyle = "any"
    health_goals: List[str] = Field(
        default_factory=list,
        description="Normalized: high_protein, low_carb, low_calorie, low_oil, light_meal, keto_friendly, nutritious",
    )
    meal_intent: MealIntent = "any"
    dish_preferences: List[str] = Field(
        default_factory=list,
        description="e.g. noodles, rice, pizza, soup, salad, curry, bowl",
    )
    spice_tolerance: SpiceTolerance = "any"
    visit_category: VisitCategory = Field(
        default="meal",
        description=(
            "What kind of place: meal, snack, dessert, ice_cream, beverages, coffee, boba, bakery, "
            "fast_food, fine_dining — drives Places search type."
        ),
    )
    ephemeral_diet_override: bool = Field(
        default=False,
        exclude=True,
        description=(
            "True when this turn explicitly requests food that contradicts saved diet defaults "
            "(e.g. seafood while profile is vegan). Used to skip overwriting profile diet fields."
        ),
    )
    best_in_area_query: bool = Field(
        default=False,
        exclude=True,
        description="User asked for best/top-rated spots in an area; tune ranking for ratings + variety.",
    )


class MenuItem(BaseModel):
    name: str
    description: Optional[str] = None


class RestaurantCandidate(BaseModel):
    place_id: str
    name: str
    lat: float
    lng: float
    cuisine_tags: List[str] = Field(default_factory=list)
    price_level: Optional[int] = None
    rating: Optional[float] = None
    review_count: int = 0
    distance_m: float = 0.0
    open_now: Optional[bool] = None
    opening_hours_lines: List[str] = Field(
        default_factory=list,
        description="Lines from Google Places weekdayDescriptions (e.g. 'Monday: 11:00 AM – 9:00 PM').",
    )
    types: List[str] = Field(default_factory=list)
    address: Optional[str] = None
    editorial_summary: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    review_snippets: List[str] = Field(default_factory=list)
    menu_items: List[MenuItem] = Field(default_factory=list)
    ambience_hints: List[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    rating: float
    distance: float
    price_fit: float
    cuisine_match: float
    menu_relevance: float
    ambience: float
    urgency: float
    personalization: float
    diet_health_fit: float = 0.0
    dish_fit: float = Field(
        default=0.0,
        description="Menu/review alignment with a specific requested dish (0–1).",
    )
    total: float


class NextAction(BaseModel):
    action: Literal["navigate", "reserve", "pickup", "delivery", "call", "agent_execute"]
    label: str
    url: Optional[str] = None
    notes: Optional[str] = None
    suggested_reply: Optional[str] = Field(
        default=None,
        description="When set (e.g. agent_execute), client may insert this as the user's next message.",
    )


class DishSuggestion(BaseModel):
    name: str
    why: str
    caution: Optional[str] = None


class ComparisonRow(BaseModel):
    place_id: str
    name: str
    rating: Optional[float]
    price_level: Optional[int]
    distance_m: float
    top_dish_signals: List[str] = Field(default_factory=list)


class AutomationAvailability(BaseModel):
    """What DineSmartAI can help automate (agent execution via Retell AI + optional self-service links)."""

    reservation_supported: bool = True
    delivery_order_supported: bool = True
    pickup_order_supported: bool = True
    payment_supported: bool = False
    agent_execution_supported: bool = Field(
        default=True,
        description="DineSmartAI can place outbound Retell calls on the user's behalf after Yes/No confirmation.",
    )
    retell_configured: bool = Field(
        default=False,
        description="True when RETELL_API_KEY and RETELL_FROM_NUMBER are set (live calls); otherwise simulated path.",
    )


class RankedPick(BaseModel):
    restaurant: RestaurantCandidate
    score_breakdown: ScoreBreakdown
    why: str = Field(
        description="Tailored explanation: why this place fits this user's request (not generic praise)."
    )
    review_summary: str
    suggested_dishes: List[DishSuggestion] = Field(default_factory=list)
    next_actions: List[NextAction] = Field(default_factory=list)
    automation: AutomationAvailability = Field(default_factory=AutomationAvailability)
    cuisine_display: str = ""
    distance_or_time_display: str = ""
    price_display: str = ""
    ambience_display: str = ""
    dietary_compatibility: str = ""
    address_display: str = Field(
        default="",
        description="Full street + city from Places (never omit; fallback guides user to Maps).",
    )
    neighborhood_display: str = Field(
        default="",
        description="Area / neighborhood when inferable from the formatted address.",
    )
    location_cluster_note: str = Field(
        default="",
        description="Optional note when shortlist clusters in the same neighborhood.",
    )
    highlights: List[str] = Field(default_factory=list)
    dish_match_display: str = Field(
        default="",
        description="Whether the requested dish appears on menu/reviews; suggested variant if known.",
    )
    comparative_note: str = Field(
        default="",
        description="How this option differs from the others (quality, distance, price, vibe).",
    )
    opening_hours_display: str = Field(
        default="",
        description="Open now + condensed hours for the card (from Places).",
    )


class ClarificationChip(BaseModel):
    label: str
    value: str


class ClarificationChipGroup(BaseModel):
    title: str
    chips: List[ClarificationChip] = Field(default_factory=list)
    """When True, only one chip may be selected in this row (restaurant, party, date, time)."""
    exclusive: bool = False
    """If set, Time row updates when a Date chip is selected; keys must match date chip `value` strings."""
    time_options_by_date: Optional[Dict[str, List[ClarificationChip]]] = None
    immediate_submit: bool = Field(
        default=False,
        description="When True, the assistant UI sends the chip value immediately (e.g. booking Yes/No).",
    )


class RecommendResponse(BaseModel):
    clarification: Optional[str] = Field(
        default=None,
        description="Short prompt when more detail is needed; pair with clarification_chip_groups when present.",
    )
    clarification_chip_groups: List[ClarificationChipGroup] = Field(default_factory=list)
    intent: UserIntent
    primary: Optional[RankedPick] = None
    alternates: List[RankedPick] = Field(default_factory=list)
    comparison: List[ComparisonRow] = Field(default_factory=list)
    recommendation_id: Optional[str] = None
    pending_automation_id: Optional[str] = Field(
        default=None,
        description="Set when user must reply Yes/No to confirm a reservation or order before we act.",
    )
    automation_completed: Optional[str] = Field(
        default=None,
        description="After a confirmed action: short status e.g. reserved | order_placed | cancelled.",
    )
    booking_confirmation_code: Optional[str] = Field(
        default=None,
        description="Short reference for the customer booking portal after a confirmed reservation/order.",
    )
    booking_portal_url: Optional[str] = Field(
        default=None,
        description="URL to open booking status (email + browser).",
    )
    dish_search_note: Optional[str] = Field(
        default=None,
        description="When dish intent used relaxed fallback: explain weaker menu/review matches.",
    )
    location_search_note: Optional[str] = Field(
        default=None,
        description="When search was centered on a named city/region from the message (not the map pin).",
    )
    debug: Optional[Dict[str, Any]] = None


class RecommendRequest(BaseModel):
    message: str
    latitude: float
    longitude: float
    user_id: Optional[str] = "demo"
    previous_recommendation_id: Optional[str] = Field(
        default=None,
        description="Prior /v1/recommend response id so follow-ups can exclude those venues and ask smarter questions.",
    )


class FeedbackRequest(BaseModel):
    user_id: str = "demo"
    recommendation_id: Optional[str] = None
    place_id: str
    action: Literal["accepted", "rejected", "visited", "ordered"]
    reason_tags: List[str] = Field(default_factory=list)
    free_text: Optional[str] = None


class UserProfilePatch(BaseModel):
    contact_email: Optional[str] = None
    favorite_cuisines: Optional[List[str]] = None
    budget_tier: Optional[Literal["low", "medium", "high"]] = None
    spice_tolerance: Optional[SpiceTolerance] = None
    disliked_ingredients: Optional[List[str]] = None
    dietary_restrictions: Optional[List[str]] = None
    ambience_prefs: Optional[List[str]] = None
    default_mode: Optional[Literal["dine_in", "delivery", "pickup", "either"]] = None
    dietary_style: Optional[DietaryStyle] = None
    meal_intent: Optional[MealIntent] = None
    health_goals: Optional[List[str]] = None
    dish_preferences: Optional[List[str]] = None


class UserProfileOut(BaseModel):
    user_id: str
    contact_email: Optional[str] = None
    favorite_cuisines: List[str]
    budget_tier: str
    spice_tolerance: str
    disliked_ingredients: List[str]
    dietary_restrictions: List[str]
    ambience_prefs: List[str]
    default_mode: str
    dietary_style: str
    meal_intent: str
    health_goals: List[str]
    dish_preferences: List[str]
