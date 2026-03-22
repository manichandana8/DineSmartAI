from collections.abc import Generator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings


def _engine():
    url = get_settings().database_url
    connect = {}
    if url.startswith("sqlite"):
        connect["check_same_thread"] = False
    return create_engine(url, connect_args=connect)


engine = _engine()


def init_db() -> None:
    from app.models.db import (  # noqa: F401
        BookingRecord,
        FeedbackEvent,
        PendingAutomation,
        RecommendationEvent,
        UserProfile,
    )

    SQLModel.metadata.create_all(engine)
    _migrate_sqlite_userprofile(engine)
    _migrate_sqlite_recommendation_venues(engine)


def _migrate_sqlite_userprofile(engine) -> None:
    """Add columns added after first deploy (SQLite has no ALTER IF NOT EXISTS)."""
    url = str(engine.url)
    if not url.startswith("sqlite"):
        return
    new_cols = [
        ("dietary_style", "VARCHAR DEFAULT 'any'"),
        ("meal_intent", "VARCHAR DEFAULT 'any'"),
        ("health_goals", "VARCHAR DEFAULT '[]'"),
        ("dish_preferences", "VARCHAR DEFAULT '[]'"),
        ("contact_email", "VARCHAR"),
    ]
    with engine.connect() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(userprofile)"))}
        for col, ddl in new_cols:
            if col in existing:
                continue
            try:
                conn.execute(text(f"ALTER TABLE userprofile ADD COLUMN {col} {ddl}"))
                conn.commit()
            except Exception:
                pass


def _migrate_sqlite_recommendation_venues(engine) -> None:
    url = str(engine.url)
    if not url.startswith("sqlite"):
        return
    with engine.connect() as conn:
        rec_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(recommendationevent)"))}
        if "venues_snapshot_json" not in rec_cols:
            try:
                conn.execute(
                    text("ALTER TABLE recommendationevent ADD COLUMN venues_snapshot_json VARCHAR DEFAULT '[]'")
                )
                conn.commit()
            except Exception:
                pass


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
