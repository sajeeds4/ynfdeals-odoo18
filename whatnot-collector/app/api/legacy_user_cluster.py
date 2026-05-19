from __future__ import annotations

from fastapi import APIRouter, Response


router = APIRouter()


def _retired(response: Response):
    response.status_code = 410
    return {"ok": False, "error": "competitor_monitoring_retired"}


@router.get("/api/users/cross_stream")
def legacy_users_cross_stream(response: Response, min_streams: int = 2, limit: int = 500, q: str = ""):
    return _retired(response)


@router.get("/api/users/audience")
def legacy_users_audience(response: Response, min_streams: int = 1, limit: int = 1000, q: str = ""):
    return _retired(response)


@router.get("/api/users/profile")
def legacy_users_profile(response: Response, username: str | None = None):
    return _retired(response)


@router.get("/api/users/target_buyers")
def legacy_target_buyers(
    response: Response,
    sellers: str | None = None,
    min_streamers: int = 2,
    limit: int = 50,
    q: str = "",
):
    return _retired(response)
