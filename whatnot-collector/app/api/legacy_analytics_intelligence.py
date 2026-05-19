from __future__ import annotations

from fastapi import APIRouter, Response

from app.services.legacy_analytics_intelligence_service import (
    get_legacy_intelligence_live,
    get_legacy_products_intel,
)


router = APIRouter()


def _respond(payload: dict, response: Response):
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.get("/api/analytics/products_intel")
def legacy_products_intel(response: Response, streamer_name: str | None = None):
    return _respond(get_legacy_products_intel(streamer_name=streamer_name), response)


@router.get("/api/intelligence/live")
def legacy_intelligence_live(
    response: Response,
    stream_id: str | None = None,
    signal_type: str | None = None,
    limit: int = 40,
    refresh: str = "auto",
):
    return _respond(
        get_legacy_intelligence_live(
            stream_id=stream_id,
            signal_type=signal_type,
            limit=limit,
            refresh=refresh,
        ),
        response,
    )
