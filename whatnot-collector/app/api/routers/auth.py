from fastapi import APIRouter

from app.services.auth_service import auth_runtime_status

router = APIRouter()


@router.get("/status")
def auth_status():
    return auth_runtime_status()

