from __future__ import annotations

from fastapi import APIRouter, Response

from app.services.legacy_shop_analytics_service import (
    get_legacy_shop_products,
    get_legacy_shop_scrape_status,
)


router = APIRouter()


def _respond(payload: dict, response: Response):
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.get("/api/analytics/shop_products")
def legacy_shop_products(response: Response, streamer_name: str | None = None):
    return _respond(get_legacy_shop_products(streamer_name=streamer_name), response)


@router.get("/api/analytics/shop_scrape_status")
def legacy_shop_scrape_status(response: Response, streamer_name: str | None = None):
    return _respond(get_legacy_shop_scrape_status(streamer_name=streamer_name), response)