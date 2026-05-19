from __future__ import annotations

from fastapi import APIRouter, Response

from app.services.legacy_runtime_service import (
    get_legacy_current_lot,
    get_legacy_inventory_audit,
    get_legacy_inventory_movements,
    get_legacy_inventory_product_detail,
)


router = APIRouter()


@router.get("/api/current_lot")
def legacy_current_lot(session_id: int | None = None):
    return get_legacy_current_lot(session_id=session_id)


@router.get("/api/inventory/movements")
def legacy_inventory_movements(product_id: int | None = None, limit: int = 50):
    return get_legacy_inventory_movements(product_id=product_id, limit=limit)


@router.get("/api/inventory/audit")
def legacy_inventory_audit(product_id: int | None = None, limit: int = 50):
    return get_legacy_inventory_audit(product_id=product_id, limit=limit)


@router.get("/api/inventory/product_detail")
def legacy_inventory_product_detail(product_id: int, response: Response):
    payload = get_legacy_inventory_product_detail(product_id)
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload
