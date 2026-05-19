from __future__ import annotations

from fastapi import APIRouter

from app.services.legacy_runtime_service import (
    get_legacy_collector_health,
    get_legacy_collectors_status,
    get_legacy_current_lot_products,
    get_legacy_failed_ingests,
    get_legacy_fee_settings,
    get_legacy_live_top_buyers,
    get_legacy_session_stats,
    get_legacy_spectator_status,
    get_legacy_spectator_streams,
    get_legacy_stream_status,
)


router = APIRouter()


@router.get("/api/stream_status")
def legacy_stream_status():
    return get_legacy_stream_status()


@router.get("/api/collectors/status")
def legacy_collectors_status():
    return get_legacy_collectors_status()


@router.get("/api/fee_settings")
def legacy_fee_settings():
    return get_legacy_fee_settings()


@router.get("/api/session_stats")
def legacy_session_stats():
    return get_legacy_session_stats()


@router.get("/api/current_lot/products")
def legacy_current_lot_products(session_id: int | None = None):
    return get_legacy_current_lot_products(session_id=session_id)


@router.get("/api/live_top_buyers")
def legacy_live_top_buyers():
    return get_legacy_live_top_buyers()


@router.get("/api/collector/health")
def legacy_collector_health(stream_id: int | None = None):
    return get_legacy_collector_health(stream_id=stream_id)


@router.get("/api/failed_ingests")
def legacy_failed_ingests(resolved: int = 0):
    return get_legacy_failed_ingests(include_resolved=resolved == 1)


@router.get("/api/spectator/streams")
def legacy_spectator_streams():
    return get_legacy_spectator_streams()


@router.get("/api/spectator/status")
def legacy_spectator_status():
    return get_legacy_spectator_status()
