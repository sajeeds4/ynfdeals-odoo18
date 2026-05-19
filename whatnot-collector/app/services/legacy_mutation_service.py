from __future__ import annotations

from datetime import datetime, timezone
import json
import time

from app.core.ssrf import SSRFValidationError, validate_public_http_url
from app.services.tiktok_shop_integration_service import get_recent_tiktok_order_line_matches
from server.api import (
    MAX_SPECTATOR_STREAMS,
    SPECTATOR_STARTS_ENABLED,
    _append_demo_scan,
    _build_live_item_payload,
    _clear_demo_scan_state,
    _clear_live_obs_scan,
    _clean_product_name,
    _current_company_session,
    _dupe_research_for_product,
    _finalize_released_lot_async,
    _maybe_ingest_winner_event,
    _product_image_url,
    _resolve_company_session,
    _set_live_obs_scan,
    _sync_selected_lot_item,
    TV_PREVIEW_MAX_ITEMS,
    _trim_preview_lot_items,
)
from server.collector_manager import (
    spectator_status,
    start_live_collector,
    start_spectator_batch,
    stop_live_collector,
    stop_spectator,
)
from server.company_db import (
    add_lot_item,
    assign_pending_winner_product,
    confirm_pending_winner_assignment,
    delete_pending_winner_assignment,
    ensure_company_bucket,
    find_product_by_code,
    get_company_session,
    get_current_company_lot,
    get_lot_item,
    get_pending_winner_assignment,
    get_product,
    latest_reusable_lot,
    list_pending_winner_assignments,
    list_lot_items,
    mark_lot_items_status,
    remove_pending_winner_assignment_item,
    rename_company_lot,
    reserve_pending_winner_assignment_items,
    reserved_qty_for_product,
    undo_confirm_pending_winner_assignment,
    update_company_lot,
    update_company_session,
    update_lot_item,
    update_pending_winner_assignment_lot_number,
    update_pending_winner_assignment_status,
)
from server.state import clear_shared_scan_for_session, set_shared_scan_for_session


STREAM_URL_ALLOWED_DOMAINS = ("whatnot.com", "tiktok.com")


def _safe_external_stream_url(stream_url: str) -> str:
    value = str(stream_url or "").strip()
    if value.startswith("tiktok:"):
        return value
    return validate_public_http_url(value, allowed_domains=STREAM_URL_ALLOWED_DOMAINS)


def _ok(payload: dict, *, status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def _tiktok_order_match_for_assignment(session: dict | None, assignment: dict | None) -> dict | None:
    if not session or not assignment:
        return None
    session_marker = str((session or {}).get("stream_url") or (session or {}).get("show_id") or "").strip().lower()
    if not session_marker.startswith("tiktok:"):
        return None
    lot_number = str(assignment.get("lot_number") or "").strip()
    if not lot_number:
        return None
    lower_bound = max(0, int(time.time()) - 24 * 3600)
    started_at = str((session or {}).get("started_at") or "")
    if started_at:
        try:
            started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            lower_bound = max(0, int(started_dt.timestamp()) - 4 * 3600)
        except Exception:
            pass
    result = get_recent_tiktok_order_line_matches(
        {
            "page_size": 100,
            "max_pages": 5,
            "create_time_ge": lower_bound,
        }
    )
    if not result.get("ok"):
        return None
    return (result.get("matches") or {}).get(lot_number)


def mutate_current_lot_set(session_id: int | None = None, lot_number: str = ""):
    lot_number = str(lot_number or "").strip()
    company_session = _resolve_company_session(session_id)
    if not company_session:
        return _ok({"ok": False, "error": "no_company_session"}, status=400)
    if not lot_number:
        return _ok({"ok": False, "error": "missing_lot_number"}, status=400)
    lot = ensure_company_bucket(company_session["id"])
    lot = rename_company_lot(lot["id"], lot_number)
    return {"ok": True, "session_id": company_session["id"], "lot": lot}


def mutate_current_lot_select_product(item_id: int | None = None):
    company_session = _current_company_session()
    if not company_session:
        return _ok({"ok": False, "error": "no_company_session"}, status=400)
    lot = get_current_company_lot(company_session["id"])
    if not lot:
        return _ok({"ok": False, "error": "no_current_lot"}, status=400)
    item = get_lot_item(int(item_id)) if item_id else None
    if not item or int(item.get("lot_id") or 0) != int(lot["id"]):
        return _ok({"ok": False, "error": "invalid_lot_item"}, status=400)
    selected = _sync_selected_lot_item(company_session["id"], lot["id"], item["id"])
    return {"ok": True, "active_item": selected}


def mutate_current_lot_remove_candidate(item_id: int | None = None):
    company_session = _current_company_session()
    if not company_session:
        return _ok({"ok": False, "error": "no_company_session"}, status=400)
    lot = get_current_company_lot(company_session["id"])
    if not lot:
        return _ok({"ok": False, "error": "no_current_lot"}, status=400)
    item = get_lot_item(int(item_id)) if item_id else None
    if not item or int(item.get("lot_id") or 0) != int(lot["id"]):
        return _ok({"ok": False, "error": "invalid_lot_item"}, status=400)
    update_lot_item(item["id"], status="dropped")
    selected = _sync_selected_lot_item(company_session["id"], lot["id"])
    return {"ok": True, "active_item": selected}


def mutate_current_lot_drop():
    company_session = _current_company_session()
    if not company_session:
        return _ok({"ok": False, "error": "no_company_session"}, status=400)
    lot = get_current_company_lot(company_session["id"])
    if not lot:
        return _ok({"ok": False, "error": "no_current_lot"}, status=400)
    _clear_live_obs_scan(company_session["id"])
    clear_shared_scan_for_session(company_session["id"])
    _clear_demo_scan_state()
    update_company_lot(lot["id"], status="released", closed_at=datetime.now(timezone.utc).isoformat())
    update_company_session(company_session["id"], current_lot_number=None)
    _finalize_released_lot_async(lot["id"])
    return {"ok": True, "lot": {}}


def mutate_current_lot_reuse():
    company_session = _current_company_session()
    if not company_session:
        return _ok({"ok": False, "error": "no_company_session"}, status=400)
    lot = latest_reusable_lot(company_session["id"])
    if not lot:
        return _ok({"ok": False, "error": "no_current_lot"}, status=400)
    mark_lot_items_status(lot["id"], from_statuses=("dropped",), to_status="open")
    update_company_lot(lot["id"], status="open", closed_at=None)
    update_company_session(company_session["id"], current_lot_number=lot.get("lot_number"))
    clear_shared_scan_for_session(company_session["id"])
    _clear_demo_scan_state()
    return {"ok": True, "lot": get_current_company_lot(company_session["id"])}


def mutate_current_lot_clear():
    company_session = _current_company_session()
    if not company_session:
        return _ok({"ok": False, "error": "no_company_session"}, status=400)
    update_company_session(company_session["id"], current_lot_number=None)
    clear_shared_scan_for_session(company_session["id"])
    _clear_demo_scan_state()
    return {"ok": True}


def mutate_current_lot_awaiting():
    company_session = _current_company_session()
    if not company_session:
        return _ok({"ok": False, "error": "no_company_session"}, status=400)
    lot = get_current_company_lot(company_session["id"])
    if not lot:
        return _ok({"ok": False, "error": "no_current_lot"}, status=400)
    update_company_lot(lot["id"], status="awaiting_auction")
    lot = get_current_company_lot(company_session["id"])
    return {"ok": True, "lot": lot}


def mutate_active_item_status(active_item_id: int | None = None, status: str | None = None):
    if not (active_item_id and status):
        return _ok({"ok": False, "error": "missing_params"}, status=400)
    company_session = _current_company_session()
    if not company_session:
        return _ok({"ok": False, "error": "no_company_session"}, status=400)
    row = update_lot_item(int(active_item_id), status=status)
    if row:
        product = None
        pid = row.get("product_id")
        if pid:
            product = get_product(int(pid))
        elif row.get("barcode"):
            product = find_product_by_code(row["barcode"])
        scan_data = {
            "id": row["id"],
            "product_id": pid,
            "barcode": row.get("barcode"),
            "sku": row.get("sku"),
            "product_name": row.get("product_name"),
            "status": status,
        }
        if product:
            scan_data.update({
                "retail_price": product.get("retail_price"),
                "cost_price": product.get("cost_price"),
                "note_top": product.get("note_top"),
                "note_mid": product.get("note_mid"),
                "note_base": product.get("note_base"),
                "media_url": product.get("media_url"),
            })
        if status in ("sold", "dropped"):
            clear_shared_scan_for_session(company_session["id"])
        else:
            set_shared_scan_for_session(company_session["id"], scan_data)
        _clear_demo_scan_state()
    return {"ok": bool(row)}


def mutate_reassign(auction_result_id: int | None = None, active_item_id: int | None = None):
    if not (auction_result_id and active_item_id):
        return _ok({"ok": False, "error": "missing_params"}, status=400)
    return _ok({"ok": False, "error": "not_supported"}, status=400)


def mutate_scan(barcode: str = ""):
    barcode = str(barcode or "").strip()
    if not barcode:
        return _ok({"ok": False, "error": "missing_barcode"}, status=400)
    company_session = _current_company_session()
    if company_session:
        session_id = int(company_session["id"])
        command = barcode.upper()
        if command in {"RELEASE_BUCKET", "UNDO_RELEASE"}:
            if command == "RELEASE_BUCKET":
                lot = get_current_company_lot(session_id)
                if not lot:
                    return _ok({"ok": False, "error": "no_current_lot"}, status=400)
                _clear_live_obs_scan(company_session["id"])
                clear_shared_scan_for_session(company_session["id"])
                _clear_demo_scan_state()
                update_company_lot(lot["id"], status="released", closed_at=datetime.now(timezone.utc).isoformat())
                update_company_session(company_session["id"], current_lot_number=None)
                _finalize_released_lot_async(lot["id"])
                return {"ok": True, "command": "release_bucket", "lot_id": lot["id"]}
            reusable_lot = latest_reusable_lot(session_id)
            if not reusable_lot:
                return _ok({"ok": False, "error": "no_reusable_lot"}, status=400)
            mark_lot_items_status(reusable_lot["id"], from_statuses=("dropped",), to_status="open")
            update_company_lot(reusable_lot["id"], status="open", closed_at=None)
            update_company_session(company_session["id"], current_lot_number=reusable_lot.get("lot_number"))
            clear_shared_scan_for_session(company_session["id"])
            _clear_live_obs_scan(company_session["id"])
            _clear_demo_scan_state()
            return {"ok": True, "command": "undo_release", "lot": get_current_company_lot(company_session["id"])}

        product = find_product_by_code(barcode)
        if not product:
            return _ok({"ok": False, "error": "product_not_found"}, status=404)
        on_hand = float(product.get("on_hand_qty") or 0)
        reserved = reserved_qty_for_product(session_id, product["id"])
        qty_remaining = on_hand - reserved
        if qty_remaining <= 0:
            return _ok(
                {
                    "ok": False,
                    "error": "out_of_stock",
                    "product_name": product.get("name", barcode),
                    "qty_available": on_hand,
                    "qty_reserved": reserved,
                },
                status=409,
            )
        lot = ensure_company_bucket(session_id)
        if not lot:
            return _ok({"ok": False, "error": "unable_to_open_lot"}, status=500)
        for row in list_lot_items(lot["id"]):
            if row.get("status") == "active":
                update_lot_item(row["id"], status="queued")
        item = add_lot_item(
            lot["id"],
            product_id=product["id"],
            barcode=product.get("barcode"),
            sku=product.get("sku"),
            product_name=product.get("name"),
            unit_cost=float(product.get("cost_price") or 0),
            qty_snapshot=1,
            status="active",
        )
        _trim_preview_lot_items(lot["id"], keep_item_id=item.get("id"), max_items=TV_PREVIEW_MAX_ITEMS)
        active_item = _build_live_item_payload(lot, product, item=item, qty_remaining=qty_remaining - 1)
        _clear_demo_scan_state()
        set_shared_scan_for_session(session_id, active_item)
        _set_live_obs_scan(session_id, active_item)
        return {"ok": True, "result": {"session_id": session_id, "active_item_id": item.get("id")}, "active_item": active_item}

    product = find_product_by_code(barcode)
    if not product:
        return _ok({"ok": False, "error": "product_not_found"}, status=404)
    preview_item = {
        "name": _clean_product_name(product.get("name", "")),
        "product_name": _clean_product_name(product.get("name", "")),
        "product_id": product.get("id"),
        "barcode": product.get("barcode"),
        "sku": product.get("sku"),
        "cost_price": product.get("cost_price"),
        "retail_price": product.get("retail_price"),
        "note_top": product.get("note_top"),
        "note_mid": product.get("note_mid"),
        "note_base": product.get("note_base"),
        "gender": product.get("gender"),
        "notes": product.get("notes"),
        "script": product.get("script"),
        "description": product.get("description"),
        "media_url": product.get("media_url"),
        "image_url": _product_image_url(product),
        "dupe_research": _dupe_research_for_product(product),
    }
    preview_item, tray = _append_demo_scan(preview_item, max_items=TV_PREVIEW_MAX_ITEMS)
    return {"ok": True, "preview": True, "active_item": preview_item, "rows": tray}


def mutate_winner_assignment_scan(barcode: str = "", assignment_id: int | None = None, session_id: int | None = None):
    barcode = str(barcode or "").strip()
    session = _resolve_company_session(session_id) or _current_company_session()
    if not barcode:
        return _ok({"ok": False, "error": "missing_barcode"}, status=400)
    if not session:
        return _ok({"ok": False, "error": "no_company_session"}, status=400)
    product = find_product_by_code(barcode)
    if not product:
        return _ok({"ok": False, "error": "product_not_found"}, status=404)
    if not assignment_id:
        queue_rows = list_pending_winner_assignments(int(session["id"]), statuses=("pending", "assigned"), limit=25)
        target = next((row for row in queue_rows if row.get("status") == "pending"), None) or (queue_rows[0] if queue_rows else None)
        assignment_id = target.get("id") if target else None
    if not assignment_id:
        return _ok({"ok": False, "error": "no_pending_winner"}, status=409)
    try:
        existing = get_pending_winner_assignment(int(assignment_id))
    except Exception:
        existing = None
    if existing and existing.get("status") == "confirmed":
        try:
            undo_confirm_pending_winner_assignment(int(assignment_id))
        except Exception:
            pass
    assigned = assign_pending_winner_product(int(assignment_id), int(product["id"]))
    if not assigned:
        return _ok({"ok": False, "error": "assign_failed"}, status=500)
    matched_order = _tiktok_order_match_for_assignment(session, assigned)
    if matched_order and str(matched_order.get("status_family") or "") in {"pending", "confirmed"}:
        reserved = reserve_pending_winner_assignment_items(
            int(assigned["id"]),
            reason_prefix="TikTok Seller pending order reserved",
        )
        if reserved:
            assigned = reserved
    if matched_order:
        assigned["tiktok_order"] = {
            "order_id": matched_order.get("order_id"),
            "seller_sku": matched_order.get("seller_sku"),
            "buyer_name": matched_order.get("buyer_name"),
            "buyer_username": matched_order.get("buyer_username"),
            "recipient_name": matched_order.get("recipient_name"),
            "status": matched_order.get("order_status"),
            "status_family": matched_order.get("status_family"),
            "quantity": matched_order.get("quantity"),
            "unit_price": matched_order.get("unit_price"),
            "total_price": matched_order.get("total_price"),
            "created_at": matched_order.get("created_at"),
            "updated_at": matched_order.get("updated_at"),
        }
    assigned["image_url"] = _product_image_url(product)
    return {"ok": True, "assignment": assigned}


def mutate_winner_assignment_confirm(assignment_id: int | None = None):
    if not assignment_id:
        return _ok({"ok": False, "error": "assignment_id required"}, status=400)
    confirmed = confirm_pending_winner_assignment(int(assignment_id))
    if not confirmed:
        return _ok({"ok": False, "error": "confirm_failed"}, status=400)
    product = get_product(int(confirmed["assigned_product_id"])) if confirmed.get("assigned_product_id") else None
    confirmed["image_url"] = _product_image_url(product) if product else None
    return {"ok": True, "assignment": confirmed}


def mutate_winner_assignment_undo(assignment_id: int | None = None):
    if not assignment_id:
        return _ok({"ok": False, "error": "assignment_id required"}, status=400)
    assignment = undo_confirm_pending_winner_assignment(int(assignment_id))
    if not assignment:
        return _ok({"ok": False, "error": "undo_failed"}, status=400)
    product = get_product(int(assignment["assigned_product_id"])) if assignment.get("assigned_product_id") else None
    assignment["image_url"] = _product_image_url(product) if product else None
    return {"ok": True, "assignment": assignment}


def mutate_winner_assignment_item_delete(assignment_id: int | None = None, item_id: int | None = None):
    if not assignment_id or not item_id:
        return _ok({"ok": False, "error": "assignment_id and item_id required"}, status=400)
    assignment = remove_pending_winner_assignment_item(int(assignment_id), int(item_id))
    if not assignment:
        return _ok({"ok": False, "error": "remove_failed"}, status=400)
    return {"ok": True, "assignment": assignment}


def mutate_winner_assignment_status(assignment_id: int | None = None, status: str | None = None, notes: str | None = None):
    if not assignment_id or not status:
        return _ok({"ok": False, "error": "assignment_id and status required"}, status=400)
    assignment = update_pending_winner_assignment_status(int(assignment_id), status, notes=notes)
    if not assignment:
        return _ok({"ok": False, "error": "status_update_failed"}, status=400)
    return {"ok": True, "assignment": assignment}


def mutate_winner_assignment_lot(assignment_id: int | None = None, lot_number: str = ""):
    lot_number = str(lot_number or "").strip()
    if not assignment_id or not lot_number:
        return _ok({"ok": False, "error": "assignment_id and lot_number required"}, status=400)
    assignment = update_pending_winner_assignment_lot_number(int(assignment_id), lot_number)
    if not assignment:
        return _ok({"ok": False, "error": "lot_update_failed"}, status=400)
    session_id = assignment.get("session_id")
    session_row = get_company_session(int(session_id)) if session_id else None
    session_stream_url = str(session_row.get("stream_url") or "").strip() if session_row else ""
    next_lot = None
    if session_stream_url.startswith("tiktok:"):
        try:
            next_lot = int(lot_number) + 1
        except Exception:
            next_lot = None
        if next_lot:
            from server.api import load_collector_state, save_collector_state
            state = load_collector_state() or {}
            lot_state = state.get("tiktok_extractor_lot_state") or {}
            if not isinstance(lot_state, dict):
                lot_state = {}
            lot_state[session_stream_url] = {
                "next_lot": next_lot,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            state["tiktok_extractor_lot_state"] = lot_state
            save_collector_state(state)
    return {"ok": True, "assignment": assignment, "tiktok_next_lot": next_lot}


def mutate_winner_assignment_delete(assignment_id: int | None = None):
    if not assignment_id:
        return _ok({"ok": False, "error": "assignment_id required"}, status=400)
    ok = delete_pending_winner_assignment(int(assignment_id))
    if not ok:
        return _ok({"ok": False, "error": "delete_failed"}, status=400)
    return {"ok": True, "deleted_assignment_id": int(assignment_id)}


def mutate_ingest_winner(
    winner_username: str = "",
    lot_number: str = "",
    event_id=None,
    sale_price=None,
    sold_at: str | None = None,
):
    winner_username = str(winner_username or "").strip()
    lot_number = str(lot_number or "").strip()
    if not winner_username or not lot_number or event_id is None:
        return _ok({"ok": False, "error": "missing_params"}, status=400)
    try:
        sale_price = float(sale_price)
    except (TypeError, ValueError):
        return _ok({"ok": False, "error": "invalid_price"}, status=400)
    local_company_session = _current_company_session()
    if not local_company_session:
        return _ok({"ok": False, "error": "no_company_session"}, status=400)
    ok = _maybe_ingest_winner_event(
        event_id,
        sold_at or datetime.now(timezone.utc).isoformat(),
        {
            "winner_username": winner_username,
            "lot_number": lot_number,
            "sale_price": sale_price,
        },
    )
    return {"ok": bool(ok), "result": {"session_id": local_company_session["id"]} if ok else None}


def mutate_stream_start(stream_url: str = "", mode: str = "our_stream"):
    stream_url = str(stream_url or "").strip()
    mode = "our_stream"
    if not stream_url:
        return _ok({"ok": False, "error": "missing_stream_url"}, status=400)
    try:
        stream_url = _safe_external_stream_url(stream_url)
    except SSRFValidationError as exc:
        return _ok({"ok": False, "error": "stream_url_forbidden", "reason": str(exc)}, status=400)
    try:
        status = start_live_collector(stream_url, mode=mode)
        return {"ok": True, **status}
    except Exception as exc:
        return _ok({"ok": False, "error": str(exc)}, status=500)


def mutate_stream_stop():
    status = stop_live_collector()
    return {"ok": True, **status}


def mutate_spectator_start(stream_urls=None, stream_url: str | None = None, replace_all: bool = False):
    if not SPECTATOR_STARTS_ENABLED:
        return _ok({"ok": False, "error": "spectator_starts_disabled"}, status=403)
    urls = list(stream_urls or [])
    if not urls and stream_url:
        urls = [stream_url]
    urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()]
    if not urls:
        return _ok({"ok": False, "error": "stream_urls required"}, status=400)
    safe_urls = []
    for url in urls:
        try:
            safe_urls.append(_safe_external_stream_url(url))
        except SSRFValidationError as exc:
            return _ok(
                {"ok": False, "error": "stream_url_forbidden", "stream_url": url, "reason": str(exc)},
                status=400,
            )
    urls = safe_urls
    if not replace_all:
        merged = []
        seen = set()
        for stream in spectator_status():
            existing_url = (stream.get("stream_url") or "").strip()
            if existing_url and stream.get("running") and existing_url not in seen:
                seen.add(existing_url)
                merged.append(existing_url)
        for url in urls:
            if url not in seen:
                seen.add(url)
                merged.append(url)
        urls = merged
    capped = False
    if len(urls) > MAX_SPECTATOR_STREAMS:
        urls = urls[:MAX_SPECTATOR_STREAMS]
        capped = True
    try:
        pid, _log_path = start_spectator_batch(urls)
        results = [{"stream_url": u, "pid": pid, "running": True, "status": "started"} for u in urls]
        errors = []
        if capped:
            errors.append({"warning": f"limited_to_{MAX_SPECTATOR_STREAMS}_streams"})
    except Exception as exc:
        results = []
        errors = [{"error": str(exc)}]
    return {"ok": len(results) > 0, "started": results, "errors": errors, "streams": spectator_status()}


def mutate_spectator_stop(stream_url: str | None = None):
    stopped = stop_spectator((stream_url or "").strip() or None)
    return {"ok": True, "stopped": stopped, "streams": spectator_status()}
