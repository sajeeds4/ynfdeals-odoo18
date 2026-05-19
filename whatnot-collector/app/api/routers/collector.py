from fastapi import APIRouter

from app.services.collector_service import get_collector_runtime, get_live_collector_runtime

router = APIRouter()


@router.get("/status")
def collector_status():
    return get_collector_runtime()


@router.get("/live")
def live_collector_status():
    return get_live_collector_runtime()

