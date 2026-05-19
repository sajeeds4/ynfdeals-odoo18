from __future__ import annotations

from fastapi import APIRouter, Body, Response

from app.services.business_task_dispatcher import (
    enqueue_auction_results_refresh,
    enqueue_inventory_refresh,
    enqueue_sales_order_refresh,
)
from app.services.legacy_order_mutation_service import (
    mutate_auction_result_update,
    mutate_sale_order_line_delete,
    mutate_sale_order_line_save,
    mutate_sale_order_update,
)


router = APIRouter()


def _respond(payload: dict, response: Response):
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.post("/api/sale_orders/update")
def legacy_sale_orders_update(response: Response, payload: dict | None = Body(default=None)):
    data = payload or {}
    result = mutate_sale_order_update(data)
    if result.get("ok"):
        order = result.get("order") or {}
        enqueue_sales_order_refresh(session_id=order.get("session_id"), customer_id=order.get("customer_id"))
        if data.get("state") in {"sale", "cancel"}:
            enqueue_inventory_refresh()
    return _respond(result, response)


@router.post("/api/auction_results/update")
def legacy_auction_results_update(response: Response, payload: dict | None = Body(default=None)):
    result = mutate_auction_result_update(payload or {})
    if result.get("ok"):
        enqueue_auction_results_refresh(session_id=(result.get("result") or {}).get("stream_id"))
    return _respond(result, response)


@router.post("/api/sale_orders/line/save")
def legacy_sale_orders_line_save(response: Response, payload: dict | None = Body(default=None)):
    data = payload or {}
    result = mutate_sale_order_line_save(data)
    if result.get("ok"):
        enqueue_sales_order_refresh()
        enqueue_inventory_refresh(product_id=data.get("product_id"))
    return _respond(result, response)


@router.post("/api/sale_orders/line/delete")
def legacy_sale_orders_line_delete(response: Response, payload: dict | None = Body(default=None)):
    result = mutate_sale_order_line_delete(payload or {})
    if result.get("ok"):
        enqueue_sales_order_refresh()
        enqueue_inventory_refresh()
    return _respond(result, response)
