from fastapi import APIRouter

from app.services.health_service import get_health_snapshot

router = APIRouter()


@router.get("/health")
def health():
    return get_health_snapshot()


@router.get("/ready")
def ready():
    return {"ok": True, "ready": True}

