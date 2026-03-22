from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class UserProfile(SQLModel, table=True):
    id: str = Field(primary_key=True)
    contact_email: Optional[str] = Field(default=None, description="Optional email for booking confirmations.")
    favorite_cuisines: str = "[]"  # JSON list as string for sqlite simplicity
    budget_tier: str = "medium"
    spice_tolerance: str = "any"
    disliked_ingredients: str = "[]"
    dietary_restrictions: str = "[]"
    ambience_prefs: str = "[]"
    default_mode: str = "either"
    dietary_style: str = "any"
    meal_intent: str = "any"
    health_goals: str = "[]"
    dish_preferences: str = "[]"
    personalization_weights: str = "{}"  # JSON blob for learned nudges
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RecommendationEvent(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    query_text: str
    intent_json: str
    primary_place_id: Optional[str] = None
    backup_place_ids: str = "[]"
    scores_json: str = "{}"
    venues_snapshot_json: str = "[]"
    """JSON: [{\"place_id\",\"name\"}, ...] primary first, then backups — for booking automation."""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PendingAutomation(SQLModel, table=True):
    """Single active automation draft per user (booking / order); gated by explicit yes/no."""

    id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    recommendation_id: Optional[str] = None
    phase: str = "awaiting_yes_no"
    action_kind: str = "reserve_table"
    confirmation_prompt: str
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BookingRecord(SQLModel, table=True):
    """Customer-visible booking / order request after they confirm Yes in chat."""

    id: str = Field(primary_key=True)
    confirmation_code: str = Field(index=True, unique=True, max_length=16)
    user_id: str = Field(index=True)
    venue_name: str
    place_id: str = ""
    action_kind: str = "reserve_table"
    status: str = "queued_simulated"
    retell_mode: str = ""
    retell_call_id: Optional[str] = None
    details_json: str = "{}"
    email_sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FeedbackEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    recommendation_id: Optional[str] = None
    place_id: str = Field(index=True)
    action: str
    reason_tags: str = "[]"
    free_text: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
