from fastapi import APIRouter, Request

from app.services.database_status_service import get_database_status
from app.services.diagnostics_service import get_deep_runtime_diagnostics, get_runtime_diagnostics
from app.services.frontend_error_service import list_frontend_errors, record_frontend_error

router = APIRouter()


@router.get("/runtime")
def runtime_diagnostics():
    return get_runtime_diagnostics()


@router.get("/runtime/deep")
def deep_runtime_diagnostics():
    return get_deep_runtime_diagnostics()


@router.get("/database")
def database_diagnostics():
    return get_database_status()


@router.post("/frontend-error")
async def frontend_error(request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        payload = {
            "source": "frontend_error_ingest",
            "message": "Invalid JSON frontend error payload",
            "metadata": {"error": str(exc)},
        }
    if not isinstance(payload, dict):
        payload = {"message": "Invalid frontend error payload", "metadata": {"raw": payload}}
    return record_frontend_error(payload)


@router.get("/frontend-errors")
def frontend_errors(limit: int = 100):
    return list_frontend_errors(limit=limit)
