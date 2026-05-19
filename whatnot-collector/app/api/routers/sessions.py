from fastapi import APIRouter

from app.services.session_service import get_current_session, get_current_session_stats, get_session_by_id, list_recent_sessions

router = APIRouter()


@router.get("/current")
def current_session():
    return get_current_session()


@router.get("/current/stats")
def current_session_stats():
    return get_current_session_stats()


@router.get("/{session_id}")
def session_detail(session_id: int):
    return get_session_by_id(session_id)


@router.get("")
def recent_sessions(limit: int = 15):
    return {"ok": True, "rows": list_recent_sessions(limit=limit)}
