from __future__ import annotations

from datetime import datetime, timezone

from server.api import _tracking_url
from server.company_db import (
    add_sale_order_line,
    apply_sale_order_inventory,
    delete_sale_order_line,
    get_auction_result,
    get_sale_order,
    reverse_sale_order_inventory,
    update_auction_result,
    update_sale_order,
    update_sale_order_line,
)


def _with_status(payload: dict, status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def _normalize_sale_order(order):
    if not order:
        return order
    order["name"] = order.get("order_number")
    order["date_order"] = order.get("ordered_at")
    order["partner_id_name"] = order.get("display_name")
    order["whatnot_session_id_name"] = order.get("session_name")
    order["amount_total"] = order.get("total_amount")
    order["amount_untaxed"] = order.get("subtotal")
    order["order_revenue"] = order.get("linked_revenue") or 0
    order["order_cost"] = order.get("linked_cost") or 0
    order["order_fees"] = order.get("linked_fees") or 0
    order["order_profit"] = order.get("linked_profit") or 0
    order["order_margin_pct"] = order.get("linked_margin_pct") or 0
    order["tracking_url"] = _tracking_url(order.get("tracking_carrier"), order.get("tracking_number"))
    return order


def mutate_sale_order_update(payload: dict):
    order_id = payload.get("order_id") or payload.get("id")
    if not order_id:
        return _with_status({"ok": False, "error": "order_id required"}, 400)
    try:
        current = get_sale_order(int(order_id))
        if not current:
            return _with_status({"ok": False, "error": "order_not_found"}, 404)
        vals = {}
        if payload.get("state") is not None:
            vals["state"] = payload.get("state")
        if payload.get("notes") is not None:
            vals["notes"] = payload.get("notes")
        if payload.get("ordered_at") is not None:
            vals["ordered_at"] = payload.get("ordered_at")
        if payload.get("external_order_ref") is not None:
            vals["external_order_ref"] = (payload.get("external_order_ref") or "").strip() or None
        if payload.get("order_source") is not None:
            vals["order_source"] = (payload.get("order_source") or "whatnot").strip().lower()
        if payload.get("whatnot_buyer_username") is not None:
            vals["whatnot_buyer_username"] = (payload.get("whatnot_buyer_username") or "").strip() or None
        if payload.get("customer_id") is not None:
            vals["customer_id"] = int(payload["customer_id"]) if payload.get("customer_id") else None
        if payload.get("fulfillment_status") is not None:
            vals["fulfillment_status"] = payload.get("fulfillment_status")
        if payload.get("payment_status") is not None:
            vals["payment_status"] = payload.get("payment_status")
        if payload.get("tracking_number") is not None:
            vals["tracking_number"] = (payload.get("tracking_number") or "").strip() or None
        if payload.get("tracking_carrier") is not None:
            vals["tracking_carrier"] = (payload.get("tracking_carrier") or "usps").strip().lower()
        if payload.get("tracking_status") is not None:
            vals["tracking_status"] = (payload.get("tracking_status") or "").strip() or None
            vals["tracking_last_checked_at"] = datetime.now(timezone.utc).isoformat()
        if payload.get("tracking_status_detail") is not None:
            vals["tracking_status_detail"] = (payload.get("tracking_status_detail") or "").strip() or None
        if payload.get("tracking_last_checked_at") is not None:
            vals["tracking_last_checked_at"] = payload.get("tracking_last_checked_at")
        if payload.get("delivered_at") is not None:
            vals["delivered_at"] = payload.get("delivered_at")
        if payload.get("packed_at") is not None:
            vals["packed_at"] = payload.get("packed_at")
        if payload.get("shipped_at") is not None:
            vals["shipped_at"] = payload.get("shipped_at")
        if vals.get("tracking_status") == "delivered":
            vals.setdefault("delivered_at", datetime.now(timezone.utc).isoformat())
            vals.setdefault("fulfillment_status", "shipped")
        new_state = vals.get("state")
        if new_state == "cancel":
            vals["fulfillment_status"] = "pending"
            vals["payment_status"] = "unpaid"
        order = update_sale_order(int(order_id), **vals)
        if new_state and current.get("state") != new_state:
            if new_state == "sale":
                apply_sale_order_inventory(int(order_id))
            elif new_state == "cancel":
                reverse_sale_order_inventory(int(order_id))
        return {"ok": bool(order), "order": _normalize_sale_order(order)}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_auction_result_update(payload: dict):
    result_id = payload.get("result_id") or payload.get("id")
    if not result_id:
        return _with_status({"ok": False, "error": "result_id required"}, 400)
    try:
        current = get_auction_result(int(result_id))
        if not current:
            return _with_status({"ok": False, "error": "result_not_found"}, 404)
        vals = {}
        for key in ("lot_number", "winner_username", "product_name", "barcode", "sku", "sold_at"):
            if payload.get(key) is not None:
                vals[key] = payload.get(key)
        if payload.get("customer_id") is not None:
            vals["customer_id"] = int(payload["customer_id"]) if payload.get("customer_id") else None
        for key in ("sale_price", "fees", "cost_price", "products_sold_count"):
            if payload.get(key) is not None:
                vals[key] = float(payload.get(key) or 0)
        result = update_auction_result(int(result_id), **vals)
        return {"ok": bool(result), "result": result}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_sale_order_line_save(payload: dict):
    order_id = payload.get("order_id")
    line_id = payload.get("line_id") or payload.get("id")
    if not order_id and not line_id:
        return _with_status({"ok": False, "error": "order_id or line_id required"}, 400)
    try:
        if line_id:
            line = update_sale_order_line(
                int(line_id),
                product_id=int(payload["product_id"]) if payload.get("product_id") else None,
                description=payload.get("description"),
                qty=float(payload.get("qty") or 0),
                unit_price=float(payload.get("unit_price") or 0),
                inventory_applied=1 if payload.get("inventory_applied") else 0,
            )
        else:
            line = add_sale_order_line(
                int(order_id),
                product_id=int(payload["product_id"]) if payload.get("product_id") else None,
                description=payload.get("description"),
                qty=float(payload.get("qty") or 0),
                unit_price=float(payload.get("unit_price") or 0),
                inventory_applied=1 if payload.get("inventory_applied") else 0,
            )
        return {"ok": bool(line), "line": line}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_sale_order_line_delete(payload: dict):
    line_id = payload.get("line_id") or payload.get("id")
    if not line_id:
        return _with_status({"ok": False, "error": "line_id required"}, 400)
    try:
        ok = delete_sale_order_line(int(line_id))
        return {"ok": ok}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)
