from __future__ import annotations

from fastapi import APIRouter, Response

from app.services.legacy_core_analytics_service import (
    get_legacy_alert_settings,
    get_legacy_alerts,
    get_legacy_analytics_overview,
    get_legacy_chat_signals,
    get_legacy_company_intelligence,
    get_legacy_competitor_prices,
    get_legacy_market_pulse,
    get_legacy_spectator_listings,
    get_legacy_timing,
)


router = APIRouter()


def _respond(payload: dict, response: Response):
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.get("/api/analytics/overview")
def legacy_analytics_overview(response: Response, stream_id: int | None = None):
    return _respond(get_legacy_analytics_overview(stream_id=stream_id), response)


@router.get("/api/analytics/market_pulse")
def legacy_market_pulse(response: Response, running_only: int = 0):
    response.status_code = 410
    return {"ok": False, "error": "competitor_monitoring_retired"}


@router.get("/api/company/intelligence")
def legacy_company_intelligence(response: Response):
    return _respond(get_legacy_company_intelligence(), response)


@router.get("/api/alerts")
def legacy_alerts(response: Response):
    return _respond(get_legacy_alerts(), response)


@router.get("/api/alerts/settings")
def legacy_alert_settings(response: Response):
    return _respond(get_legacy_alert_settings(), response)


@router.get("/api/spectator/listings")
def legacy_spectator_listings(response: Response, stream_id: int | None = None):
    response.status_code = 410
    return {"ok": False, "error": "competitor_monitoring_retired"}


@router.get("/api/analytics/competitor_prices")
def legacy_competitor_prices(response: Response, q: str = "", limit: int = 200):
    response.status_code = 410
    return {"ok": False, "error": "competitor_monitoring_retired"}


@router.get("/api/analytics/chat_signals")
def legacy_chat_signals(response: Response, stream_id: int | None = None):
    return _respond(get_legacy_chat_signals(stream_id=stream_id), response)


@router.get("/api/analytics/timing")
def legacy_timing(response: Response, streamer_name: str | None = None):
    return _respond(get_legacy_timing(streamer_name=streamer_name), response)
