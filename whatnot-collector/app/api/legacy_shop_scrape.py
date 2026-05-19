from __future__ import annotations

from fastapi import APIRouter, Response

from app.services.legacy_shop_scrape_service import trigger_legacy_shop_scrape


router = APIRouter()


def _respond(payload: dict, response: Response):
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.post("/api/analytics/scrape_shop")
def legacy_scrape_shop(payload: dict, response: Response):
    return _respond(trigger_legacy_shop_scrape(streamer_name=payload.get("streamer_name")), response)
