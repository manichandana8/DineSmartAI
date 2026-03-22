from fastapi import APIRouter

from app.api.deps import SessionDep
from app.models.domain import FeedbackRequest
from app.services.memory import add_feedback

router = APIRouter(prefix="/v1", tags=["feedback"])


@router.post("/feedback")
def post_feedback(body: FeedbackRequest, session: SessionDep) -> dict[str, str]:
    add_feedback(
        session,
        body.user_id,
        body.place_id,
        body.action,
        body.reason_tags,
        body.free_text,
        body.recommendation_id,
    )
    return {"status": "ok"}
