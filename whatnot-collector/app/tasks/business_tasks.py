from __future__ import annotations

import asyncio
import time

from app.core.redis import set_runtime_state
from app.core.task_runtime import run_tracked_task
from app.services.inventory_service import (
    get_inventory_overview,
    get_inventory_product_detail,
    list_inventory_categories,
    list_inventory_products,
    list_inventory_vendors,
    list_product_audit,
    list_product_movements,
)
from app.services.legacy_runtime_service import (
    get_legacy_auction_results,
    get_legacy_customer_orders,
    get_legacy_orders,
)
from app.services.tiktok_shop_integration_service import (
    delete_tiktok_products,
    push_missing_image_inventory_to_tiktok_drafts,
)
from app.services.medusa_integration_service import sync_products_to_medusa
from app.workers.celery_app import celery_app
from server.state import load_collector_state


def _live_show_running() -> bool:
    try:
        state = load_collector_state() or {}
    except Exception:
        return False
    return bool(state.get("running") and state.get("stream_url") and not state.get("stopped_at"))


def _store_state(key: str, payload: dict, ttl_seconds: int = 1800) -> dict:
    try:
        set_runtime_state(key, payload, ttl_seconds=ttl_seconds)
    except Exception:
        pass
    return payload


def _inventory_snapshot(active_only: bool = True) -> dict:
    payload = {
        "ok": True,
        "overview": get_inventory_overview(),
        "products": {"ok": True, "rows": list_inventory_products(active_only=active_only)},
        "categories": list_inventory_categories(),
        "vendors": list_inventory_vendors(),
    }
    return _store_state("business:inventory:last", payload)


def _inventory_activity_snapshot(product_id: int | None = None, limit: int = 50) -> dict:
    payload = {
        "ok": True,
        "product_id": product_id,
        "movements": list_product_movements(product_id=product_id, limit=limit),
        "audit": list_product_audit(product_id=product_id, limit=limit),
    }
    suffix = "all" if product_id is None else str(int(product_id))
    return _store_state(f"business:inventory_activity:{suffix}", payload)


def _inventory_product_snapshot(product_id: int) -> dict:
    payload = get_inventory_product_detail(int(product_id))
    return _store_state(f"business:inventory_product:{int(product_id)}", payload)


def _sales_orders_snapshot(session_id: int | None = None, q: str = "") -> dict:
    payload = get_legacy_orders(session_id=session_id, q=q)
    suffix = "current" if session_id is None and not q else f"{session_id or 'current'}:{q or 'all'}"
    return _store_state(f"business:sales_orders:{suffix}", payload)


def _customer_orders_snapshot(partner_id: int) -> dict:
    payload = get_legacy_customer_orders(int(partner_id))
    return _store_state(f"business:customer_orders:{int(partner_id)}", payload)


def _auction_results_snapshot(session_id: int | None = None, scope: str = "", q: str = "", limit: int = 500) -> dict:
    payload = get_legacy_auction_results(session_id=session_id, scope=scope, q=q, limit=limit)
    suffix = f"{session_id or 'current'}:{scope or 'all'}:{q or 'all'}:{int(limit)}"
    return _store_state(f"business:auction_results:{suffix}", payload)


def _tiktok_shop_orders_sync(hours_back: int = 72, page_size: int = 50, max_pages: int = 5) -> dict:
    now = int(time.time())
    payload = {
        "ok": True,
        "disabled": True,
        "orders_seen": 0,
        "pages_fetched": 0,
        "results": [],
        "status_counts": {"disabled": 1},
        "hours_back": max(1, int(hours_back or 72)),
        "page_size": max(1, min(int(page_size or 50), 100)),
        "max_pages": max(1, min(int(max_pages or 5), 20)),
        "synced_at": now,
        "message": "TikTok Shop API order sync is disabled. Use CSV/manual imports for shop sales.",
    }
    return _store_state("business:tiktok_shop_orders:last", payload, ttl_seconds=7200)


@celery_app.task(name="app.tasks.business.refresh_inventory_snapshot")
def refresh_inventory_snapshot(active_only: bool = True):
    if _live_show_running():
        return {"ok": True, "skipped": True, "reason": "live_show_running"}
    return run_tracked_task(
        f"refresh_inventory_snapshot:{int(bool(active_only))}",
        _inventory_snapshot,
        active_only,
        lock_ttl_seconds=120,
    )


@celery_app.task(name="app.tasks.business.refresh_inventory_activity")
def refresh_inventory_activity(product_id: int | None = None, limit: int = 50):
    suffix = "all" if product_id is None else str(int(product_id))
    return run_tracked_task(
        f"refresh_inventory_activity:{suffix}:{int(limit)}",
        _inventory_activity_snapshot,
        product_id,
        limit,
        lock_ttl_seconds=120,
    )


@celery_app.task(name="app.tasks.business.refresh_inventory_product")
def refresh_inventory_product(product_id: int):
    return run_tracked_task(
        f"refresh_inventory_product:{int(product_id)}",
        _inventory_product_snapshot,
        product_id,
        lock_ttl_seconds=120,
    )


@celery_app.task(name="app.tasks.business.refresh_sales_orders_snapshot")
def refresh_sales_orders_snapshot(session_id: int | None = None, q: str = ""):
    if session_id is None and not q and _live_show_running():
        return {"ok": True, "skipped": True, "reason": "live_show_running"}
    suffix = "current" if session_id is None and not q else f"{session_id or 'current'}:{q or 'all'}"
    return run_tracked_task(
        f"refresh_sales_orders_snapshot:{suffix}",
        _sales_orders_snapshot,
        session_id,
        q,
        lock_ttl_seconds=120,
    )


@celery_app.task(name="app.tasks.business.refresh_customer_orders_snapshot")
def refresh_customer_orders_snapshot(partner_id: int):
    return run_tracked_task(
        f"refresh_customer_orders_snapshot:{int(partner_id)}",
        _customer_orders_snapshot,
        partner_id,
        lock_ttl_seconds=120,
    )


@celery_app.task(name="app.tasks.business.refresh_auction_results_snapshot")
def refresh_auction_results_snapshot(session_id: int | None = None, scope: str = "", q: str = "", limit: int = 500):
    suffix = f"{session_id or 'current'}:{scope or 'all'}:{q or 'all'}:{int(limit)}"
    return run_tracked_task(
        f"refresh_auction_results_snapshot:{suffix}",
        _auction_results_snapshot,
        session_id,
        scope,
        q,
        limit,
        lock_ttl_seconds=180,
    )


@celery_app.task(name="app.tasks.business.sync_tiktok_shop_orders")
def sync_tiktok_shop_orders(hours_back: int = 72, page_size: int = 50, max_pages: int = 5):
    return run_tracked_task(
        f"sync_tiktok_shop_orders:{int(hours_back)}:{int(page_size)}:{int(max_pages)}",
        _tiktok_shop_orders_sync,
        hours_back,
        page_size,
        max_pages,
        lock_ttl_seconds=300,
    )


@celery_app.task(name="app.tasks.business.sync_fastapi_products_to_medusa")
def sync_fastapi_products_to_medusa(active_only: bool = True, limit: int | None = None, dry_run: bool = False):
    return run_tracked_task(
        f"sync_fastapi_products_to_medusa:{int(bool(active_only))}:{limit or 'all'}:{int(bool(dry_run))}",
        sync_products_to_medusa,
        active_only,
        limit,
        dry_run,
        lock_ttl_seconds=900,
        state_ttl_seconds=7200,
    )


@celery_app.task(name="app.tasks.business.bulk_push_tiktok_products")
def bulk_push_tiktok_products(payload: dict):
    task_key = "tasks:bulk_push_tiktok_products"

    def _run():
        return asyncio.run(push_missing_image_inventory_to_tiktok_drafts(payload))

    return run_tracked_task(task_key, _run, lock_ttl_seconds=1200, state_ttl_seconds=3600)


@celery_app.task(name="app.tasks.business.bulk_delete_tiktok_products")
def bulk_delete_tiktok_products(payload: dict):
    task_key = "tasks:bulk_delete_tiktok_products"

    def _run():
        return asyncio.run(delete_tiktok_products(payload))

    return run_tracked_task(task_key, _run, lock_ttl_seconds=600, state_ttl_seconds=3600)


@celery_app.task(name="app.tasks.business.refresh_business_snapshots")
def refresh_business_snapshots():
    if _live_show_running():
        return {"ok": True, "skipped": True, "reason": "live_show_running"}

    def _run():
        return {
            "ok": True,
            "inventory": _inventory_snapshot(),
            "inventory_activity": _inventory_activity_snapshot(limit=25),
            "sales_orders": _sales_orders_snapshot(),
            "auction_results": _auction_results_snapshot(limit=250),
        }

    return run_tracked_task("refresh_business_snapshots", _run, lock_ttl_seconds=240)
