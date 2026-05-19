from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile

from app.core.redis import get_runtime_state
from app.services.tiktok_shop_integration_service import (
    build_tiktok_shop_auth_url,
    connect_tiktok_shop,
    disconnect_tiktok_shop,
    enrich_inventory_from_tiktok_drafts,
    fetch_tiktok_brands,
    fetch_tiktok_categories,
    fetch_tiktok_category_attributes,
    fetch_tiktok_category_rules,
    fetch_tiktok_package_shipping_document,
    fetch_tiktok_packages,
    fetch_tiktok_products,
    fetch_tiktok_returns,
    fetch_tiktok_warehouses,
    handle_tiktok_webhook,
    list_tracked_tiktok_returns,
    list_recent_tiktok_webhooks,
    list_tiktok_mappings,
    push_missing_image_inventory_to_tiktok_drafts,
    push_product_to_tiktok,
    refresh_tiktok_shop_token,
    save_tiktok_category_mapping,
    sync_tiktok_inventory,
    sync_tiktok_orders,
    sync_tiktok_returns,
    switch_tiktok_shop,
    test_tiktok_shop_connection,
    tiktok_shop_status,
)
from app.services.tiktok_finance_service import (
    get_tiktok_finance_overview,
    import_tiktok_income_workbook,
    sync_tiktok_finance_for_known_orders,
)
from app.tasks.business_tasks import bulk_delete_tiktok_products, bulk_push_tiktok_products

router = APIRouter()


@router.get("/tiktok-shop/status")
def get_tiktok_shop_status():
    return tiktok_shop_status()


@router.post("/tiktok-shop/auth-url")
def get_tiktok_shop_auth_url(payload: dict | None = None):
    return build_tiktok_shop_auth_url(payload or {})


@router.post("/tiktok-shop/connect")
async def post_tiktok_shop_connect(payload: dict):
    return await connect_tiktok_shop(payload or {})


@router.post("/tiktok-shop/refresh")
async def post_tiktok_shop_refresh():
    return await refresh_tiktok_shop_token()


@router.post("/tiktok-shop/test")
async def post_tiktok_shop_test():
    return await test_tiktok_shop_connection()


@router.post("/tiktok-shop/switch")
def post_tiktok_shop_switch(payload: dict):
    return switch_tiktok_shop(str((payload or {}).get("shop_key") or ""))


@router.get("/tiktok-shop/mappings")
def get_tiktok_shop_mappings():
    return list_tiktok_mappings()


@router.get("/tiktok-shop/categories")
async def get_tiktok_shop_categories(parent_id: str | None = None):
    return await fetch_tiktok_categories(parent_id=parent_id)


@router.get("/tiktok-shop/category-rules")
async def get_tiktok_shop_category_rules(category_id: str):
    return await fetch_tiktok_category_rules(category_id)


@router.get("/tiktok-shop/category-attributes")
async def get_tiktok_shop_category_attributes(category_id: str):
    return await fetch_tiktok_category_attributes(category_id)


@router.get("/tiktok-shop/brands")
async def get_tiktok_shop_brands(brand_name: str, category_id: str | None = None):
    return await fetch_tiktok_brands(brand_name=brand_name, category_id=category_id)


@router.get("/tiktok-shop/warehouses")
async def get_tiktok_shop_warehouses():
    return await fetch_tiktok_warehouses()


@router.get("/tiktok-shop/packages")
async def get_tiktok_shop_packages(
    package_status: str | None = None,
    package_id: str | None = None,
    page_size: int = 50,
    max_pages: int = 3,
):
    return await fetch_tiktok_packages({
        "package_status": package_status,
        "package_id": package_id,
        "page_size": page_size,
        "max_pages": max_pages,
    })


@router.post("/tiktok-shop/packages/search")
async def post_tiktok_shop_packages_search(payload: dict | None = None):
    return await fetch_tiktok_packages(payload or {})


@router.get("/tiktok-shop/packages/{package_id}/shipping-document")
async def get_tiktok_shop_package_shipping_document(package_id: str, document_type: str = "SHIPPING_LABEL"):
    return await fetch_tiktok_package_shipping_document(package_id, document_type=document_type)


@router.post("/tiktok-shop/category-map")
async def post_tiktok_shop_category_map(payload: dict):
    return await save_tiktok_category_mapping(payload or {})


@router.post("/tiktok-shop/products/push")
async def post_tiktok_shop_product_push(payload: dict):
    return await push_product_to_tiktok(payload or {})


@router.post("/tiktok-shop/products/push-missing-image-drafts")
async def post_tiktok_shop_products_push_missing_image_drafts(payload: dict | None = None):
    payload = payload or {}
    if payload.get("dry_run"):
        return await push_missing_image_inventory_to_tiktok_drafts(payload)
    bulk_push_tiktok_products.apply_async(args=[payload], queue="business")
    return {"ok": True, "queued": True, "task_key": "tasks:bulk_push_tiktok_products"}


@router.post("/tiktok-shop/products/search")
async def post_tiktok_shop_products_search(payload: dict | None = None):
    payload = payload or {}
    return await fetch_tiktok_products(
        status=payload.get("status") or "DRAFT",
        page_size=payload.get("page_size") or 50,
        max_pages=payload.get("max_pages") or 4,
        include_details=payload.get("include_details", True) is not False,
    )


@router.post("/tiktok-shop/products/enrich-inventory-from-drafts")
async def post_tiktok_shop_products_enrich_inventory_from_drafts(payload: dict | None = None):
    return await enrich_inventory_from_tiktok_drafts(payload or {})


@router.post("/tiktok-shop/inventory/sync")
async def post_tiktok_shop_inventory_sync(payload: dict | None = None):
    payload = payload or {}
    return await sync_tiktok_inventory(product_id=payload.get("product_id"))


@router.post("/tiktok-shop/products/delete")
async def post_tiktok_shop_products_delete(payload: dict | None = None):
    bulk_delete_tiktok_products.apply_async(args=[payload or {}], queue="business")
    return {"ok": True, "queued": True, "task_key": "tasks:bulk_delete_tiktok_products"}


@router.get("/tiktok-shop/task-status/{task_key}")
def get_tiktok_task_status(task_key: str):
    allowed = {"bulk_push_tiktok_products", "bulk_delete_tiktok_products"}
    if task_key not in allowed:
        return {"ok": False, "error": "unknown_task"}
    state = get_runtime_state(f"tasks:{task_key}", default=None)
    if state is None:
        return {"ok": True, "status": "idle"}
    return {"ok": True, **state}


@router.post("/tiktok-shop/orders/sync")
async def post_tiktok_shop_orders_sync(payload: dict | None = None):
    return await sync_tiktok_orders(payload or {})


@router.get("/tiktok-shop/finance/overview")
def get_tiktok_shop_finance_overview(
    session_id: int | None = None,
    q: str | None = None,
    limit: int = 5000,
    session_min: int = 1,
    session_max: int = 20,
    ordered_from: str = "2026-04-17",
):
    return get_tiktok_finance_overview(
        session_id=session_id,
        q=q,
        limit=limit,
        session_min=session_min,
        session_max=session_max,
        ordered_from=ordered_from,
    )


@router.post("/tiktok-shop/finance/sync")
async def post_tiktok_shop_finance_sync(payload: dict | None = None):
    return await sync_tiktok_finance_for_known_orders(payload or {})


@router.post("/tiktok-shop/finance/import-income")
async def post_tiktok_shop_finance_import_income(file: UploadFile = File(...)):
    raw = await file.read()
    return import_tiktok_income_workbook(raw, filename=file.filename)


@router.get("/tiktok-shop/returns")
def get_tiktok_shop_returns(limit: int = 200, processed: bool | None = None, q: str | None = None, monitor_only: bool = True):
    return list_tracked_tiktok_returns(limit=limit, processed=processed, q=q, monitor_only=monitor_only)


@router.post("/tiktok-shop/returns/search")
async def post_tiktok_shop_returns_search(payload: dict | None = None):
    return await fetch_tiktok_returns(payload or {})


@router.post("/tiktok-shop/returns/sync")
async def post_tiktok_shop_returns_sync(payload: dict | None = None):
    return await sync_tiktok_returns(payload or {})


@router.post("/tiktok-shop/webhook")
async def post_tiktok_shop_webhook(request: Request):
    payload = await request.json()
    return await handle_tiktok_webhook(payload, headers=dict(request.headers))


@router.get("/tiktok-shop/webhook-events")
def get_tiktok_shop_webhook_events(limit: int = 100, event_type: str | None = None, processed: bool | None = None):
    return list_recent_tiktok_webhooks(limit=limit, event_type=event_type, processed=processed)


@router.post("/tiktok-shop/disconnect")
def post_tiktok_shop_disconnect():
    return disconnect_tiktok_shop()
