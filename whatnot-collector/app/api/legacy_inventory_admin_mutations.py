from __future__ import annotations

from fastapi import APIRouter, Body, Request, Response

from app.services.business_task_dispatcher import enqueue_inventory_refresh
from app.services.legacy_inventory_admin_mutation_service import (
    mutate_inventory_product_delete,
    mutate_inventory_product_update,
)


router = APIRouter()


def _respond(payload: dict, response: Response):
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.post("/api/inventory/product/delete")
def legacy_inventory_product_delete(response: Response, payload: dict | None = Body(default=None)):
    data = payload or {}
    result = mutate_inventory_product_delete(data)
    if result.get("ok"):
        enqueue_inventory_refresh(product_id=data.get("product_id") or data.get("id"))
    return _respond(result, response)


@router.post("/api/inventory/product/update")
def legacy_inventory_product_update(request: Request, response: Response, payload: dict | None = Body(default=None)):
    data = payload or {}
    result = mutate_inventory_product_update(request, data)
    if result.get("ok"):
        product = result.get("product") or {}
        enqueue_inventory_refresh(product_id=product.get("id") or data.get("product_id") or data.get("id"))
    return _respond(result, response)
