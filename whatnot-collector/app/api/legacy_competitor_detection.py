from __future__ import annotations

from fastapi import APIRouter, Response


router = APIRouter()


def _retired(response: Response):
    response.status_code = 410
    return {"ok": False, "error": "competitor_monitoring_retired"}


@router.get("/api/competitors/title_quality")
def legacy_competitor_title_quality(response: Response, stream_id: int | None = None):
    return _retired(response)


@router.get("/api/competitors/detection_feed")
def legacy_competitor_detection_feed(response: Response, stream_id: int | None = None):
    return _retired(response)
