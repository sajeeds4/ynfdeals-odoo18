from fastapi import APIRouter

from app.services.auction_service import list_pending, list_results

router = APIRouter()


@router.get("/results")
def auction_results(session_id: int | None = None, limit: int = 500):
    return list_results(session_id=session_id, limit=limit)


@router.get("/pending")
def pending_winners(session_id: int | None = None, limit: int = 200):
    return list_pending(session_id=session_id, limit=limit)
