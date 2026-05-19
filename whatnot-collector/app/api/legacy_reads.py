from __future__ import annotations

from fastapi import APIRouter

from app.services.legacy_runtime_service import (
    get_legacy_events,
    get_legacy_inventory,
    get_legacy_inventory_categories,
    get_legacy_inventory_vendors,
    get_legacy_recent,
    get_legacy_session_history,
    get_legacy_session_list,
)


router = APIRouter()


@router.get("/events")
def legacy_events(since: int = 0, limit: int = 500, stream_id: int | None = None, stream_url: str | None = None):
    return get_legacy_events(since=since, limit=limit, stream_id=stream_id, stream_url=stream_url)


@router.get("/recent")
def legacy_recent(limit: int = 200, stream_id: int | None = None, stream_url: str | None = None):
    return get_legacy_recent(limit=limit, stream_id=stream_id, stream_url=stream_url)


@router.get("/api/inventory")
def legacy_inventory(
    low_stock: int = 3,
    active: str = "true",
    limit: int | None = None,
    offset: int = 0,
    compact: int = 0,
):
    return get_legacy_inventory(
        low_stock=low_stock,
        active=active,
        limit=limit,
        offset=offset,
        compact=compact in (1, True),
    )


@router.get("/api/inventory/categories")
def legacy_inventory_categories():
    return get_legacy_inventory_categories()


@router.get("/api/inventory/vendors")
def legacy_inventory_vendors():
    return get_legacy_inventory_vendors()


@router.get("/api/sessions/list")
def legacy_sessions_list():
    return get_legacy_session_list()


@router.get("/api/session_history")
def legacy_session_history():
    return get_legacy_session_history()
