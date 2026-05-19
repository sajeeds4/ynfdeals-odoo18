from __future__ import annotations

from fastapi import APIRouter, Response


router = APIRouter()


def _retired(response: Response):
    response.status_code = 410
    return {"ok": False, "error": "competitor_monitoring_retired"}


@router.get("/api/analytics/businesses")
def legacy_analytics_businesses(response: Response):
    return _retired(response)


@router.get("/api/analytics/trends")
def legacy_analytics_trends(response: Response, streamer_name: str | None = None):
    return _retired(response)
