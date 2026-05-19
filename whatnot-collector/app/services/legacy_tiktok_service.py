from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from server.api import (
    _build_sale_order_picklist_payload,
    _clear_tiktok_go_live_session_cache,
    _build_tiktok_order_note,
    _ensure_tiktok_operator_session,
    _get_active_tiktok_go_live_session,
    _latest_tiktok_label_artifact,
    _list_tiktok_go_live_sessions,
    _match_inventory_product,
    _next_tiktok_go_live_sequence,
    _parse_tiktok_float,
    _public_tiktok_label_artifact,
    _tiktok_operator_status,
)
from server.company_db import (
    add_sale_order_line,
    apply_sale_order_inventory,
    apply_tiktok_live_session_inventory,
    create_sale_order,
    end_company_session,
    get_company_session,
    get_product,
    get_sale_order,
    list_products,
    list_sale_order_lines,
    list_sale_orders,
    upsert_customer,
)
from server.events_db import get_latest_id_for_stream, get_stream_id
from server.state import load_collector_state, save_collector_state
from app.services.google_sheets_backup_service import enqueue_tiktok_live_sheet_backup, get_tiktok_live_sheet_backup_status


def _with_status(payload: dict, status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def get_tiktok_extractor_lot_state(stream_url: str | None = None):
    try:
        state = load_collector_state() or {}
        lot_state = state.get("tiktok_extractor_lot_state") or {}
        if not isinstance(lot_state, dict):
            lot_state = {}
        stream_url_value = (stream_url or "").strip() or None
        if stream_url_value:
            entry = lot_state.get(stream_url_value) or {}
            if not isinstance(entry, dict):
                entry = {}
            return {
                "ok": True,
                "stream_url": stream_url_value,
                "next_lot": entry.get("next_lot"),
                "updated_at": entry.get("updated_at"),
            }
        return {"ok": True, "streams": lot_state}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def set_tiktok_extractor_lot_state(stream_url: str | None = None, next_lot=None):
    stream_url_value = str(stream_url or "").strip()
    if not stream_url_value:
        return _with_status({"ok": False, "error": "stream_url_required"}, 400)
    next_lot_value = None
    if next_lot not in (None, "", False):
        try:
            next_lot_value = int(next_lot)
        except Exception:
            return _with_status({"ok": False, "error": "invalid_next_lot"}, 400)
        if next_lot_value <= 0:
            return _with_status({"ok": False, "error": "invalid_next_lot"}, 400)
    try:
        state = load_collector_state() or {}
        lot_state = state.get("tiktok_extractor_lot_state") or {}
        if not isinstance(lot_state, dict):
            lot_state = {}
        if next_lot_value is None:
            lot_state.pop(stream_url_value, None)
        else:
            lot_state[stream_url_value] = {
                "next_lot": next_lot_value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        state["tiktok_extractor_lot_state"] = lot_state
        save_collector_state(state)
        return {"ok": True, "stream_url": stream_url_value, "next_lot": next_lot_value}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def update_tiktok_operator_config(enabled: bool = False, streamer: str | None = None):
    streamer_value = (streamer or "").strip().lstrip("@")
    if enabled and not streamer_value:
        return _with_status({"ok": False, "error": "streamer_required"}, 400)
    stream_url = f"tiktok:{streamer_value}" if streamer_value else None
    try:
        state = load_collector_state() or {}
        if enabled:
            prev_stream_url = (state.get("tiktok_operator_stream_url") or "").strip() or None
            session_id = state.get("tiktok_operator_session_id")
            try:
                session = get_company_session(int(session_id)) if session_id else None
            except Exception:
                session = None
            if session and str(session.get("status") or "").lower() not in {"ended"}:
                try:
                    end_company_session(int(session["id"]))
                except Exception:
                    pass
            session_id = _ensure_tiktok_operator_session(stream_url, streamer=streamer_value)
            state["tiktok_operator_enabled"] = True
            state["tiktok_operator_streamer"] = streamer_value
            state["tiktok_operator_stream_url"] = stream_url
            state["tiktok_operator_session_id"] = int(session_id) if session_id else None
            should_reset_cursor = (
                not state.get("tiktok_operator_last_ingested_event_id")
                or (prev_stream_url and stream_url and prev_stream_url != stream_url)
                or (prev_stream_url is None)
            )
            if should_reset_cursor and stream_url:
                latest_id = 0
                try:
                    sid = get_stream_id(stream_url)
                except Exception:
                    sid = None
                if sid:
                    try:
                        latest_id = int(get_latest_id_for_stream(int(sid)) or 0)
                    except Exception:
                        latest_id = 0
                state["tiktok_operator_last_ingested_event_id"] = int(latest_id)
            else:
                state.setdefault("tiktok_operator_last_ingested_event_id", 0)
            save_collector_state(state)
            return {"ok": True, "tiktok_operator": _tiktok_operator_status()}

        state["tiktok_operator_enabled"] = False
        state["tiktok_operator_streamer"] = streamer_value or state.get("tiktok_operator_streamer")
        state["tiktok_operator_stream_url"] = stream_url or state.get("tiktok_operator_stream_url")
        save_collector_state(state)
        return {"ok": True, "tiktok_operator": _tiktok_operator_status()}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def create_tiktok_shop_order(payload: dict):
    product_id = payload.get("product_id")
    if not product_id:
        return _with_status({"ok": False, "error": "product_id required"}, 400)
    try:
        product = get_product(int(product_id))
        if not product:
            return _with_status({"ok": False, "error": "product_not_found"}, 404)
        qty = max(1.0, float(payload.get("qty") or 1))
        unit_price = float(payload.get("unit_price") or 0)
        buyer_username = (payload.get("buyer_username") or "").strip() or None
        customer = upsert_customer(buyer_username, display_name=buyer_username) if buyer_username else None
        external_order_ref = (payload.get("external_order_ref") or "").strip() or None
        ordered_at = payload.get("ordered_at") or datetime.now(timezone.utc).isoformat()
        notes = (payload.get("notes") or "").strip() or None
        description = (payload.get("description") or product.get("name") or "").strip() or product.get("name")
        order = create_sale_order(
            session_id=None,
            customer_id=customer.get("id") if customer else None,
            buyer_group_id=None,
            whatnot_buyer_username=buyer_username,
            state="sale",
            subtotal=0,
            total_amount=0,
            ordered_at=ordered_at,
            notes=notes,
            order_source="tiktok_shop",
            external_order_ref=external_order_ref,
            fulfillment_status="pending",
            payment_status="paid",
        )
        add_sale_order_line(
            int(order["id"]),
            product_id=int(product["id"]),
            description=description,
            qty=qty,
            unit_price=unit_price,
            inventory_applied=0,
        )
        apply_sale_order_inventory(int(order["id"]))
        _clear_tiktok_go_live_session_cache()
        created = get_sale_order(int(order["id"]))
        lines = list_sale_order_lines(int(order["id"]))
        return {"ok": True, "order": created, "lines": lines}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def create_tiktok_live_order(payload: dict):
    product_id = payload.get("product_id")
    if not product_id:
        return _with_status({"ok": False, "error": "product_id required"}, 400)
    try:
        product = get_product(int(product_id))
        if not product:
            return _with_status({"ok": False, "error": "product_not_found"}, 404)
        session_id = payload.get("session_id") or None
        qty = max(1.0, float(payload.get("qty") or 1))
        unit_price = float(payload.get("unit_price") or 0)
        buyer_username = (payload.get("buyer_username") or "").strip() or None
        external_order_ref = (payload.get("external_order_ref") or "").strip() or None
        ordered_at = payload.get("ordered_at") or datetime.now(timezone.utc).isoformat()
        notes = (payload.get("notes") or "").strip() or "TikTok LIVE order"
        description = (payload.get("description") or product.get("name") or "").strip() or product.get("name")
        order = create_sale_order(
            session_id=int(session_id) if session_id else None,
            customer_id=None,
            buyer_group_id=None,
            whatnot_buyer_username=buyer_username,
            state="sale",
            subtotal=0,
            total_amount=0,
            ordered_at=ordered_at,
            notes=notes,
            order_source="tiktok_live",
            external_order_ref=external_order_ref,
            fulfillment_status="delivered",
            payment_status="paid",
        )
        add_sale_order_line(
            int(order["id"]),
            product_id=int(product["id"]),
            description=description,
            qty=qty,
            unit_price=unit_price,
            inventory_applied=0,
        )
        apply_sale_order_inventory(int(order["id"]))
        if session_id:
            enqueue_tiktok_live_sheet_backup(int(session_id), "order_created")
        _clear_tiktok_go_live_session_cache()
        created = get_sale_order(int(order["id"]))
        lines = list_sale_order_lines(int(order["id"]))
        return {"ok": True, "order": created, "lines": lines}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def import_tiktok_shop_orders(csv_text: str | None = None, commit: bool = False):
    csv_text_value = csv_text or ""
    if not csv_text_value.strip():
        return _with_status({"ok": False, "error": "csv_text required"}, 400)
    try:
        products = list_products(active_only=False, low_stock_only=False)
        existing_refs = {
            (row.get("external_order_ref") or "").strip()
            for row in list_sale_orders(order_source="tiktok_shop")
            if (row.get("external_order_ref") or "").strip()
        }
        reader = csv.DictReader(io.StringIO(csv_text_value))
        preview_rows = []
        imported = []
        for idx, row in enumerate(reader, start=2):
            product_name = (row.get("Combined Listing") or row.get("Product Name") or "").strip()
            external_order_ref = (row.get("Order ID") or "").strip()
            buyer_username = (row.get("Buyer Username") or "").strip() or None
            qty = max(1.0, _parse_tiktok_float(row.get("Quantity"), 1))
            unit_price = _parse_tiktok_float(row.get("SKU Unit Original Price"), 0)
            subtotal = _parse_tiktok_float(row.get("SKU Subtotal Before Discount"), unit_price * qty)
            if unit_price <= 0 and qty > 0:
                unit_price = round(subtotal / qty, 2)
            product, score = _match_inventory_product(products, product_name)
            status = "ready"
            if external_order_ref and external_order_ref in existing_refs:
                status = "duplicate"
            elif not product:
                status = "unmatched"
            preview = {
                "row_number": idx,
                "external_order_ref": external_order_ref,
                "buyer_username": buyer_username,
                "product_name": product_name,
                "qty": qty,
                "unit_price": unit_price,
                "subtotal": subtotal,
                "matched_product_id": product.get("id") if product else None,
                "matched_inventory_name": product.get("name") if product else None,
                "match_score": score,
                "status": status,
            }
            preview_rows.append(preview)
            if commit and status == "ready":
                customer = upsert_customer(buyer_username, display_name=buyer_username) if buyer_username else None
                order = create_sale_order(
                    session_id=None,
                    customer_id=customer.get("id") if customer else None,
                    buyer_group_id=None,
                    whatnot_buyer_username=buyer_username,
                    state="sale",
                    subtotal=0,
                    total_amount=0,
                    ordered_at=datetime.now(timezone.utc).isoformat(),
                    notes=_build_tiktok_order_note(row),
                    order_source="tiktok_shop",
                    external_order_ref=external_order_ref or None,
                    fulfillment_status="pending",
                    payment_status="paid",
                )
                add_sale_order_line(
                    int(order["id"]),
                    product_id=int(product["id"]),
                    description=product_name or product.get("name"),
                    qty=qty,
                    unit_price=unit_price,
                    inventory_applied=0,
                )
                apply_sale_order_inventory(int(order["id"]))
                imported.append(
                    {
                        "order_id": order["id"],
                        "order_number": order["order_number"],
                        "external_order_ref": external_order_ref,
                    }
                )
                if external_order_ref:
                    existing_refs.add(external_order_ref)
        summary = {
            "total_rows": len(preview_rows),
            "ready_rows": sum(1 for row in preview_rows if row["status"] == "ready"),
            "duplicate_rows": sum(1 for row in preview_rows if row["status"] == "duplicate"),
            "unmatched_rows": sum(1 for row in preview_rows if row["status"] == "unmatched"),
            "imported_rows": len(imported),
        }
        return {"ok": True, "rows": preview_rows, "summary": summary, "imported": imported}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_tiktok_live_picklist(session_id):
    if not session_id:
        return _with_status({"ok": False, "error": "session_id required"}, 400)
    try:
        return _build_sale_order_picklist_payload(int(session_id), order_source="tiktok_live")
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_tiktok_live_sessions(limit=80, summary=False):
    try:
        include_rows = not bool(summary)
        return {"ok": True, "rows": _list_tiktok_go_live_sessions(limit=int(limit or 80), include_rows=include_rows)}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_tiktok_live_session_active():
    try:
        return {"ok": True, "session": _get_active_tiktok_go_live_session()}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_tiktok_live_next_sequence():
    try:
        return {"ok": True, "sequence": _next_tiktok_go_live_sequence()}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_tiktok_live_google_sheet_backup_status(session_id):
    if not session_id:
        return _with_status({"ok": False, "error": "session_id required"}, 400)
    try:
        return get_tiktok_live_sheet_backup_status(int(session_id))
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_tiktok_live_label_artifact(session_key=None):
    try:
        artifact = _public_tiktok_label_artifact(_latest_tiktok_label_artifact(session_key or ""))
        return {"ok": True, "artifact": artifact}
    except Exception as exc:
        print(f"[tiktok_live_labels] artifact lookup failed for {session_key!r}: {exc}")
        return {"ok": True, "artifact": None, "warning": "artifact_lookup_unavailable"}


def apply_tiktok_live_session_inventory_service(session_id):
    if not session_id:
        return _with_status({"ok": False, "error": "session_id required"}, 400)
    try:
        result = apply_tiktok_live_session_inventory(int(session_id))
        _clear_tiktok_go_live_session_cache()
        return result
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)
