from fastapi import APIRouter

from app.api.deps import SessionDep
from app.models.domain import RecommendRequest, RecommendResponse
from app.services.recommendation import run_recommendation

router = APIRouter(prefix="/v1", tags=["recommend"])


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(body: RecommendRequest, session: SessionDep) -> RecommendResponse:
    return await run_recommendation(body, session)
