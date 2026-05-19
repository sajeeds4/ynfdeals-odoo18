from __future__ import annotations

from datetime import datetime, timezone
import re
import time

from app.services.session_service import get_current_session_stats
from app.services.tiktok_shop_integration_service import get_recent_tiktok_order_line_matches
from server.api import (
    OUR_WHATNOT_ACCOUNT,
    _current_company_session,
    _dupe_research_for_product,
    _live_top_buyers_payload,
    _process_event_side_effects,
    _product_image_url,
    _maybe_ingest_winner_event,
    _resolve_company_session,
    _sync_live_lot_number,
    _tiktok_operator_status,
)
from server.collector_manager import collector_status, collectors_status
from server.company_db import (
    get_company_session,
    get_customer,
    get_current_company_lot,
    get_product_detail,
    get_product,
    get_setting_map,
    inventory_summary,
    list_auction_results,
    list_buyer_groups,
    list_categories,
    list_company_sessions,
    list_inventory_audit_logs,
    list_inventory_movements,
    list_customers,
    list_customer_orders,
    list_customer_reviews,
    list_lot_items,
    list_pending_winner_assignments,
    list_products,
    list_reviews_feed,
    list_sale_orders,
    list_vendors,
    reserve_pending_winner_assignment_items,
    get_product_profit_rows,
    TIKTOK_PRODUCT_FIELDS,
    update_company_session,
    update_pending_winner_assignment_status,
    get_customer_analytics,
    get_customer_by_username,
)
from server.events_db import (
    get_all_streams,
    get_audience_user_profile,
    get_collector_health,
    get_company_stream_detail,
    get_company_stream_history,
    get_events_since,
    get_failed_ingests,
    get_recent_events,
    get_stream_id,
    latest_db_event,
)
from server.postgres_cutover import domain_primary_backend, postgres_available
from server.whatnot_reviews import get_review_sync_status
import json


RUNTIME_STATUS_DOMAINS = (
    "company_sessions",
    "company_lots",
    "company_pending",
    "company_results",
    "company_orders",
    "ingest_streams",
    "ingest_events",
    "ingest_failed",
    "ingest_lots",
    "ingest_users",
)

INVENTORY_LIST_FIELDS = (
    "id", "name", "sku", "barcode", "category_id", "category_name", "product_type",
    "brand", "gender", "supplier_name", "storage_bin", "cost_price", "retail_price",
    "on_hand_qty", "low_stock_threshold", "active", "notes", "notes_verified",
    "notes_verified_at", "note_top", "note_mid", "note_base", "media_url",
    "description", "dupe_inspiration", "dupe_confidence", "dupe_classification",
    "dupe_notes", "times_sold", "sales_revenue", "last_sold_at", "created_at", "updated_at",
    *TIKTOK_PRODUCT_FIELDS,
)


def _postgres_runtime_audit(domains: tuple[str, ...] = RUNTIME_STATUS_DOMAINS) -> dict:
    domain_rows = [
        {"domain": domain, "primary": domain_primary_backend(domain)}
        for domain in domains
    ]
    non_postgres_domains = [
        row["domain"]
        for row in domain_rows
        if row["primary"] != "postgres"
    ]
    available = postgres_available()
    ok = bool(available and not non_postgres_domains)
    reason = None
    if not available:
        reason = "postgres_runtime_unavailable"
    elif non_postgres_domains:
        reason = "postgres_primary_incomplete"
    return {
        "ok": ok,
        "primary": "postgres",
        "postgres_available": available,
        "domains": domain_rows,
        "non_postgres_domains": non_postgres_domains,
        "fail_closed": not ok,
        "reason": reason,
    }


def _inventory_list_row(row: dict, low_stock: int | float) -> dict:
    compact = {key: row.get(key) for key in INVENTORY_LIST_FIELDS if key in row}
    compact["default_code"] = compact.get("sku")
    compact["standard_price"] = compact.get("cost_price")
    compact["list_price"] = compact.get("retail_price")
    compact["qty_available"] = compact.get("on_hand_qty")
    compact["virtual_available"] = compact.get("on_hand_qty")
    compact["type"] = compact.get("product_type")
    compact["categ_id"] = compact.get("category_id")
    compact["categ_name"] = compact.get("category_name")
    # Keep list payloads light: embedded image_path/base64 can make inventory responses tens of MB.
    compact["image_url"] = compact.get("media_url") or None
    compact["active"] = bool(compact.get("active", True))
    qty = compact.get("qty_available") or 0
    cost = compact.get("standard_price") or 0
    compact["stock_value"] = round(qty * cost, 2)
    compact["low_stock"] = qty <= low_stock and compact.get("type") in ("product", "storable", "consu")
    compact["times_sold"] = int(compact.get("times_sold") or 0)
    compact["sales_revenue"] = round(float(compact.get("sales_revenue") or 0), 2)
    return compact


def get_legacy_stream_status():
    runtime = _postgres_runtime_audit()
    return {
        **collector_status(),
        "ok": runtime["ok"],
        "tiktok_operator": _tiktok_operator_status(),
        "database_runtime": runtime,
    }


def _lot_match_key(value) -> str:
    return str(value or "").strip()


def _tiktok_assignment_payload(row: dict, match: dict[str, object] | None) -> dict:
    if not match:
        row["tiktok_order"] = None
        return row
    status_family = str(match.get("status_family") or "")
    row["tiktok_order"] = {
        "order_id": match.get("order_id"),
        "seller_sku": match.get("seller_sku"),
        "buyer_name": match.get("buyer_name"),
        "buyer_username": match.get("buyer_username"),
        "recipient_name": match.get("recipient_name"),
        "product_name": match.get("product_name"),
        "status": match.get("order_status"),
        "status_family": status_family,
        "quantity": match.get("quantity"),
        "unit_price": match.get("unit_price"),
        "total_price": match.get("total_price"),
        "created_at": match.get("created_at"),
        "paid_at": match.get("paid_at"),
        "updated_at": match.get("updated_at"),
    }
    row["tiktok_order_id"] = match.get("order_id")
    row["tiktok_order_status"] = match.get("order_status")
    row["tiktok_order_status_family"] = status_family
    row["tiktok_buyer_name"] = match.get("buyer_name") or match.get("recipient_name")
    row["tiktok_buyer_username"] = match.get("buyer_username")
    row["tiktok_sale_price"] = float(match.get("total_price") or match.get("unit_price") or 0)
    return row


def _session_is_tiktok_live(session: dict | None) -> bool:
    marker = str((session or {}).get("stream_url") or (session or {}).get("show_id") or "").strip().lower()
    return marker.startswith("tiktok:")


def _enrich_tiktok_assignment_rows(session: dict, rows: list[dict]) -> list[dict]:
    if not _session_is_tiktok_live(session):
        return rows
    try:
        started_at = str((session or {}).get("started_at") or "")
        lower_bound = max(0, int(time.time()) - 24 * 3600)
        if started_at:
            try:
                started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                lower_bound = max(0, int(started_dt.timestamp()) - 4 * 3600)
            except Exception:
                pass
        search_result = get_recent_tiktok_order_line_matches(
            {
                "page_size": 100,
                "max_pages": 5,
                "create_time_ge": lower_bound,
            }
        )
        if not search_result.get("ok"):
            return rows
        matches = search_result.get("matches") or {}
        changed = False
        for row in rows:
            lot_key = _lot_match_key(row.get("lot_number"))
            match = matches.get(lot_key)
            if not match:
                continue
            family = str(match.get("status_family") or "")
            has_items = bool(row.get("assigned_items_count") or row.get("assigned_product_id") or row.get("assigned_items"))
            reserved_total = sum(int(item.get("reserved_qty") or 0) for item in (row.get("assigned_items") or []))
            if family == "cancelled" and row.get("status") != "payment_cancelled":
                updated = update_pending_winner_assignment_status(
                    int(row["id"]),
                    "payment_cancelled",
                    notes="TikTok Seller API cancellation sync",
                )
                if updated:
                    changed = True
                    continue
            if family in {"pending", "confirmed"} and has_items:
                assigned_qty = sum(int(item.get("qty") or 0) for item in (row.get("assigned_items") or []))
                if assigned_qty > reserved_total and row.get("status") != "payment_cancelled":
                    updated = reserve_pending_winner_assignment_items(
                        int(row["id"]),
                        reason_prefix="TikTok Seller pending order reserved",
                    )
                    if updated:
                        changed = True
                        continue
            _tiktok_assignment_payload(row, match)
        if changed:
            refreshed = list_pending_winner_assignments(
                session_id=int(session["id"]),
                statuses=("pending", "assigned", "needs_review", "confirmed", "payment_cancelled"),
                limit=max(len(rows), 200),
            )
            rows = refreshed
            for row in rows:
                match = matches.get(_lot_match_key(row.get("lot_number")))
                _tiktok_assignment_payload(row, match)
            return rows
        for row in rows:
            match = matches.get(_lot_match_key(row.get("lot_number")))
            _tiktok_assignment_payload(row, match)
        return rows
    except Exception:
        return rows


def get_legacy_collectors_status():
    runtime = _postgres_runtime_audit()
    return {**collectors_status(), "ok": runtime["ok"], "database_runtime": runtime}


def get_legacy_fee_settings():
    try:
        settings = get_setting_map()
    except Exception:
        settings = {}
    fee_pct = float(settings.get("platform_fee_pct", 10.9))
    fixed_fee = float(settings.get("fixed_fee", 0.50))
    return {
        "ok": True,
        "fee_pct": fee_pct,
        "fixed_fee": fixed_fee,
        "description": f"{fee_pct}% of sale price + ${fixed_fee:.2f} fixed per transaction",
    }


def get_legacy_failed_ingests(include_resolved: bool = False):
    return {"ok": True, "records": get_failed_ingests(include_resolved=include_resolved)}


def get_legacy_session_stats():
    payload = dict(get_current_session_stats())
    payload.pop("ok", None)
    return payload


def get_legacy_session_list():
    rows = []
    for row in list_company_sessions("ynfdeals", limit=200):
        rows.append({
            "id": row["id"],
            "name": row.get("name"),
            "status": row.get("status"),
            "start_time": row.get("started_at"),
            "end_time": row.get("ended_at"),
            "total_revenue": row.get("total_revenue"),
            "total_profit": row.get("total_profit"),
            "total_products_sold": row.get("total_products_sold"),
            "total_lots_sold": row.get("total_lots_sold"),
            "whatnot_account": row.get("whatnot_account"),
            "show_id": row.get("show_id"),
            "stream_url": row.get("stream_url"),
            "streamer_name": row.get("streamer_name"),
        })
    return {"ok": True, "sessions": rows}


def get_legacy_session_history():
    return get_legacy_session_list()


def get_legacy_live_top_buyers():
    status = collector_status()
    if not status.get("running") or not status.get("session_id"):
        return {"buyers": [], "recent_winners": []}
    try:
        company_session = _current_company_session()
    except Exception:
        company_session = None
    if not company_session:
        return {"buyers": [], "recent_winners": []}
    return _live_top_buyers_payload(company_session["id"])


def get_legacy_current_lot_products(session_id: int | None = None):
    session = _current_company_session() if session_id is None else {"id": int(session_id)}
    if session:
        lot = get_current_company_lot(session["id"])
        if not lot:
            return {"ok": True, "rows": [], "selected_item_id": None}
        rows = []
        selected_item_id = None
        for row in list_lot_items(lot["id"]):
            if row.get("status") == "dropped":
                continue
            row["cost"] = row.get("unit_cost")
            row["selected"] = row.get("status") == "active"
            if row["selected"]:
                selected_item_id = row.get("id")
            if row.get("product_id"):
                prod = get_product(int(row["product_id"]))
                row["image_url"] = _product_image_url(prod) if prod else None
                if prod:
                    row["retail_price"] = prod.get("retail_price")
                    row["cost_price"] = prod.get("cost_price")
                    row["note_top"] = prod.get("note_top")
                    row["note_mid"] = prod.get("note_mid")
                    row["note_base"] = prod.get("note_base")
                    row["dupe_research"] = _dupe_research_for_product(prod)
            rows.append(row)
        return {"ok": True, "lot": lot, "rows": rows, "selected_item_id": selected_item_id}
    return {"ok": True, "lot": {}, "rows": [], "selected_item_id": None}


def get_legacy_collector_health(stream_id: int | None = None):
    health = get_collector_health(stream_id=stream_id)
    now = datetime.now(timezone.utc).isoformat()

    def _age_minutes(ts):
        if not ts:
            return None
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            return round((datetime.now(timezone.utc) - t).total_seconds() / 60, 1)
        except Exception:
            return None

    warnings = []
    for key in ["chat_message", "lot_update", "bid_update"]:
        age = _age_minutes(health.get(key))
        if age is not None and age > 5:
            warnings.append(f"No {key.replace('_', ' ')} for {age} min")
        elif age is None:
            warnings.append(f"No {key.replace('_', ' ')} seen yet")
    return {
        "ok": True,
        "checked_at": now,
        "last_events": health,
        "ages_minutes": {k: _age_minutes(v) for k, v in health.items() if k != "total_events"},
        "warnings": warnings,
        "healthy": len(warnings) == 0,
    }


def get_legacy_spectator_streams():
    return {"ok": True, "streams": [], "spectator_removed": True}


def get_legacy_spectator_status():
    return {"ok": True, "enabled": False, "running": False, "spectator_removed": True}


def get_legacy_inventory(
    low_stock: int = 3,
    active: str = "true",
    limit: int | None = None,
    offset: int = 0,
    compact: bool = False,
):
    active_param = (active or "").strip().lower()
    active_only = active_param in ("true", "1", "active")
    rows = list_products(
        active_only=active_only,
        low_stock_only=False,
        limit=limit,
        offset=offset,
        include_sales_metrics=not compact,
    )
    if active_param in ("false", "0", "inactive"):
        rows = [row for row in rows if not row.get("active")]
    summary = inventory_summary()
    rows = [_inventory_list_row(row, low_stock) for row in rows]
    return {
        "ok": True,
        "rows": rows,
        "total_products": summary["total_products"],
        "total_stock_value": summary["total_stock_value"],
        "low_stock_count": summary["low_stock_count"],
        "out_of_stock_count": summary.get("out_of_stock_count", 0),
        "missing_barcode_count": summary.get("missing_barcode_count", 0),
        "missing_image_count": summary.get("missing_image_count", 0),
        "unverified_notes_count": summary.get("unverified_notes_count", 0),
    }


def get_legacy_inventory_categories():
    return {"ok": True, "rows": list_categories()}


def get_legacy_inventory_vendors():
    return {"ok": True, "rows": list_vendors()}


def get_legacy_events(since: int = 0, limit: int = 500, stream_id: int | None = None, stream_url: str | None = None):
    limit = max(1, min(int(limit), 5000))
    if stream_id:
        effective_stream_id = int(stream_id)
        events = get_events_since(since, stream_id=effective_stream_id, limit=limit)
        status = collector_status()
        collector_stream_id = None
        if status.get("running") and status.get("stream_url") and status.get("stream_mode") == "our_stream":
            collector_stream_id = get_stream_id(status.get("stream_url"))
            company_session_id = status.get("session_id")
            if collector_stream_id is not None and company_session_id:
                try:
                    update_company_session(int(company_session_id), stream_id=int(collector_stream_id))
                except Exception:
                    pass
        if collector_stream_id is not None and effective_stream_id == collector_stream_id:
            _process_event_side_effects(events, stream_id=effective_stream_id)
    elif stream_url:
        effective_stream_id = get_stream_id(stream_url)
        events = get_events_since(since, stream_id=effective_stream_id, limit=limit)
    else:
        status = collector_status()
        if status.get("running") and status.get("stream_url"):
            effective_stream_id = get_stream_id(status.get("stream_url"))
            company_session_id = status.get("session_id")
            if effective_stream_id is not None and company_session_id and status.get("stream_mode") == "our_stream":
                try:
                    update_company_session(int(company_session_id), stream_id=int(effective_stream_id))
                except Exception:
                    pass
        else:
            from server.api import load_collector_state
            saved = load_collector_state()
            saved_url = saved.get("stream_url")
            effective_stream_id = get_stream_id(saved_url) if saved_url else None
        events = get_events_since(since, stream_id=effective_stream_id, limit=limit)
        if effective_stream_id is not None:
            _process_event_side_effects(events, stream_id=effective_stream_id)
    return {"events": events, "has_more": len(events) >= limit}


def get_legacy_recent(limit: int = 200, stream_id: int | None = None, stream_url: str | None = None):
    if stream_id:
        effective_stream_id = int(stream_id)
    elif stream_url:
        effective_stream_id = get_stream_id(stream_url)
    else:
        status = collector_status()
        if status.get("running") and status.get("stream_url"):
            effective_stream_id = get_stream_id(status.get("stream_url"))
        else:
            from server.api import load_collector_state
            saved = load_collector_state()
            saved_url = saved.get("stream_url")
            effective_stream_id = get_stream_id(saved_url) if saved_url else None
    events = get_recent_events(int(limit), stream_id=effective_stream_id)
    return {"events": events}


def get_legacy_auction_results(session_id: int | None = None, scope: str = "", q: str = "", limit: int = 500):
    if session_id:
        sid = int(session_id)
    elif (scope or "").strip().lower() == "all":
        sid = None
    else:
        current = _current_company_session()
        sid = int(current["id"]) if current else None
    rows = list_auction_results(session_id=sid, limit=int(limit))
    if q:
        ql = q.lower()
        rows = [
            row for row in rows
            if ql in (row.get("winner_username") or "").lower()
            or ql in (row.get("product_name") or "").lower()
            or ql in str(row.get("lot_number") or "").lower()
        ]
    total_revenue = round(sum(row.get("sale_price") or 0 for row in rows), 2)
    total_fees = round(sum(row.get("fees") or 0 for row in rows), 2)
    total_profit = round(sum(row.get("profit") or 0 for row in rows), 2)
    return {"rows": rows, "total": len(rows), "total_revenue": total_revenue, "total_fees": total_fees, "total_profit": total_profit}


def get_legacy_winner_assignment_state(session_id: int | None = None, limit: int = 200):
    session = _resolve_company_session(session_id) or _current_company_session()
    if not session:
        return {"ok": True, "session": None, "rows": []}
    try:
        current_status = collector_status()
        current_stream_url = current_status.get("stream_url")
        current_stream_id = get_stream_id(current_stream_url) if current_stream_url else None
        if (
            current_status.get("running")
            and current_status.get("stream_mode") == "our_stream"
            and current_stream_id is not None
        ):
            related_stream_ids = [int(current_stream_id)]
            show_id = session.get("show_id")
            if show_id:
                try:
                    rows = [
                        row for row in get_all_streams()
                        if f"/live/{show_id}" in str(row.get("stream_url") or "")
                    ][:6]
                    for row in rows:
                        rid = int(row.get("id") or 0)
                        if rid not in related_stream_ids:
                            related_stream_ids.append(rid)
                except Exception:
                    pass
            seen_event_ids = set()
            merged_events = []
            for related_id in related_stream_ids:
                try:
                    event_rows = [
                        row for row in get_recent_events(120, stream_id=related_id)
                        if row.get("event_type") in ("auction_winner", "lot_update")
                    ]
                    for event in event_rows:
                        eid = event.get("id")
                        if eid in seen_event_ids:
                            continue
                        seen_event_ids.add(eid)
                        merged_events.append(event)
                except Exception:
                    for event in get_recent_events(120, stream_id=related_id):
                        if event.get("event_type") not in ("auction_winner", "lot_update"):
                            continue
                        eid = event.get("id")
                        if eid in seen_event_ids:
                            continue
                        seen_event_ids.add(eid)
                        merged_events.append(event)
            if merged_events:
                merged_events.sort(key=lambda event: event.get("created_at") or "")
                for event in merged_events:
                    try:
                        payload = json.loads(event.get("payload") or "{}")
                    except Exception:
                        continue
                    if event.get("event_type") == "lot_update":
                        _sync_live_lot_number(payload, stream_id=event.get("stream_id") or current_stream_id)
                    elif event.get("event_type") == "auction_winner":
                        _maybe_ingest_winner_event(
                            event.get("id"),
                            event.get("created_at"),
                            payload,
                            stream_id=event.get("stream_id") or current_stream_id,
                        )
            latest_winner = latest_db_event("auction_winner", stream_id=current_stream_id)
            latest_winner_event_id = latest_winner.get("_event_id")
            if latest_winner_event_id:
                source_event_id = f"collector_event_{latest_winner_event_id}"
                existing_queue = list_pending_winner_assignments(
                    session_id=int(session["id"]),
                    statuses=("pending", "assigned", "needs_review", "confirmed"),
                    limit=100,
                )
                if not any(row.get("source_event_id") == source_event_id for row in existing_queue):
                    latest_payload = dict(latest_winner)
                    latest_payload.pop("_event_id", None)
                    latest_payload.pop("_created_at", None)
                    _maybe_ingest_winner_event(
                        latest_winner_event_id,
                        latest_winner.get("_created_at"),
                        latest_payload,
                        stream_id=current_stream_id,
                    )
            update_company_session(int(session["id"]), stream_id=int(current_stream_id))
            session = get_company_session(int(session["id"])) or session
    except Exception:
        pass
    rows = list_pending_winner_assignments(
        session_id=int(session["id"]),
        statuses=("pending", "assigned", "needs_review", "confirmed", "payment_cancelled"),
        limit=int(limit),
    )
    rows = _enrich_tiktok_assignment_rows(session, rows)
    confirmed_lot_numbers = {
        str(row.get("lot_number") or "").strip()
        for row in rows
        if row.get("status") == "confirmed" and str(row.get("lot_number") or "").strip()
    }
    if confirmed_lot_numbers:
        rows = [
            row for row in rows
            if not (
                row.get("status") in {"pending", "assigned", "needs_review"}
                and str(row.get("lot_number") or "").strip() in confirmed_lot_numbers
            )
        ]
    return {"ok": True, "session": session, "rows": rows}


def get_legacy_orders(session_id: int | None = None, q: str = "", limit: int | None = None, offset: int = 0):
    local_company_session = _current_company_session()
    effective_session_id = session_id or (local_company_session["id"] if local_company_session else None)
    rows = list_buyer_groups(
        session_id=effective_session_id or None,
        q=(q or "").strip().lower() or None,
        limit=limit,
        offset=offset,
    )
    for row in rows:
        row["session_id_id"] = row.get("session_id")
        row["session_id_name"] = row.get("session_name")
        row["partner_id"] = row.get("customer_id")
        row["partner_id_id"] = row.get("customer_id")
        row["partner_id_name"] = row.get("display_name")
        row["sale_order_id_id"] = row.get("sale_order_id")
        row["sale_order_id_name"] = None
    total_revenue = round(sum(row.get("total_revenue") or 0 for row in rows), 2)
    total_profit = round(sum(row.get("total_profit") or 0 for row in rows), 2)
    total_cost = round(sum(row.get("total_cost") or 0 for row in rows), 2)
    avg_margin = round(total_profit / total_revenue * 100.0, 1) if total_revenue else 0.0
    return {
        "ok": True,
        "rows": rows,
        "total_orders": len(rows),
        "total_revenue": total_revenue,
        "total_cost": total_cost,
        "total_profit": total_profit,
        "avg_margin": avg_margin,
    }


def get_legacy_customers(q: str = "", has_orders: bool = False, limit: int | None = None, offset: int = 0):
    rows = list_customers(
        q=(q or "").strip() or None,
        has_orders_only=has_orders,
        limit=limit,
        offset=offset,
    )
    for row in rows:
        row["name"] = row.get("display_name")
    return {"ok": True, "rows": rows}


def get_legacy_current_lot(session_id: int | None = None):
    company_session = _resolve_company_session(session_id)
    if company_session:
        lot = get_current_company_lot(company_session["id"])
        return {"ok": True, "session_id": company_session["id"], "lot": lot or {}}
    return {"ok": True, "session_id": None, "lot": {}}


def get_legacy_inventory_movements(product_id: int | None = None, limit: int = 50):
    rows = list_inventory_movements(product_id=product_id or None, limit=int(limit))
    for row in rows:
        row["name"] = row.get("reason") or row.get("movement_type") or "Stock move"
        row["product_uom_qty"] = abs(float(row.get("qty_delta") or 0))
        row["date"] = row.get("created_at")
        row["location_id_name"] = row.get("reference_type") or "Inventory"
        row["location_dest_id_name"] = "Customer" if float(row.get("qty_delta") or 0) < 0 else "On Hand"
    return {"ok": True, "rows": rows}


def get_legacy_inventory_audit(product_id: int | None = None, limit: int = 50):
    rows = list_inventory_audit_logs(product_id=product_id or None, limit=int(limit))
    return {"ok": True, "rows": rows}


def get_legacy_inventory_product_detail(product_id: int):
    detail = get_product_detail(int(product_id))
    if not detail:
        return {"ok": False, "error": "product_not_found", "_status": 404}
    product = detail["product"]
    product["default_code"] = product.get("sku")
    product["standard_price"] = product.get("cost_price")
    product["list_price"] = product.get("retail_price")
    product["qty_available"] = product.get("on_hand_qty")
    product["virtual_available"] = product.get("on_hand_qty")
    product["type"] = product.get("product_type")
    product["categ_name"] = product.get("category_name")
    product["image_url"] = _product_image_url(product)
    for row in detail.get("movements", []):
        row["name"] = row.get("reason") or row.get("movement_type") or "Stock move"
        row["product_uom_qty"] = abs(float(row.get("qty_delta") or 0))
        row["date"] = row.get("created_at")
        row["location_id_name"] = row.get("reference_type") or "Inventory"
        row["location_dest_id_name"] = "Customer" if float(row.get("qty_delta") or 0) < 0 else "On Hand"
    return {"ok": True, **detail, "product": product}


def get_legacy_products():
    rows = []
    for row in list_products(active_only=False):
        rows.append({
            "id": row.get("id"),
            "name": row.get("name"),
            "barcode": row.get("barcode"),
            "default_code": row.get("sku"),
        })
    return {"rows": rows}


def get_legacy_products_full():
    rows = []
    for row in list_products(active_only=False):
        rows.append({
            "id": row.get("id"),
            "name": row.get("name"),
            "barcode": row.get("barcode"),
            "default_code": row.get("sku"),
            "standard_price": row.get("cost_price"),
            "list_price": row.get("retail_price"),
            "qty_available": row.get("on_hand_qty"),
            "image_url": _product_image_url(row),
        })
    return {"rows": rows}


def get_legacy_customer_review_status(seller_username: str = ""):
    return {"ok": True, "status": get_review_sync_status((seller_username or "").strip() or None)}


def get_legacy_customer_reviews(q: str = "", matched_only: bool = False):
    payload = list_reviews_feed(q=(q or "").strip() or None, matched_only=bool(matched_only))
    return {"ok": True, **payload}


def get_legacy_customer_detail(customer_id: int):
    customer = get_customer(int(customer_id))
    if not customer:
        return {"ok": False, "error": "customer_not_found", "_status": 404}
    customer["name"] = customer.get("display_name")
    analytics = get_customer_analytics(int(customer_id))
    return {"ok": True, "customer": customer, **analytics}


def get_legacy_customer_profile_lookup(customer_id: int | None = None, username: str | None = None):
    clean_username = (username or "").strip()
    if not customer_id and not clean_username:
        return {"ok": False, "error": "customer_id or username required", "_status": 400}
    customer = None
    if customer_id:
        customer = get_customer(int(customer_id))
    if not customer and clean_username:
        customer = get_customer_by_username(clean_username)
    analytics = {"sessions": [], "products": [], "summary": {}}
    orders = []
    if customer:
        customer["name"] = customer.get("display_name")
        analytics = get_customer_analytics(int(customer["id"]))
        orders = list_customer_orders(int(customer["id"]))
        for row in orders:
            row["name"] = row.get("order_number")
            row["date_order"] = row.get("ordered_at")
            row["amount_total"] = row.get("total_amount")
            row["whatnot_session_id"] = row.get("session_id")
            row["whatnot_session_id_name"] = row.get("session_name")
    audience_username = clean_username or (customer.get("whatnot_username") if customer else None)
    audience = get_audience_user_profile(audience_username) if audience_username else None
    if not customer and not audience:
        return {"ok": False, "error": "customer_not_found", "_status": 404}
    if not customer:
        uname = (clean_username or (audience or {}).get("username") or "").strip().lstrip("@")
        customer = {
            "id": None,
            "name": None,
            "display_name": None,
            "whatnot_username": uname or None,
            "sale_order_count": 0,
            "session_count": 0,
            "total_spent": 0,
            "total_profit": 0,
            "total_revenue": 0,
            "purchase_count": 0,
            "last_purchase_at": audience.get("last_seen") if audience else None,
        }
    return {
        "ok": True,
        "customer": customer,
        "sessions": analytics.get("sessions") or [],
        "products": analytics.get("products") or [],
        "summary": analytics.get("summary") or {},
        "orders": orders,
        "audience": audience or {},
    }


def get_legacy_customer_orders(partner_id: int):
    if not partner_id:
        return {"ok": False, "error": "partner_id required", "_status": 400}
    orders = list_customer_orders(int(partner_id))
    for row in orders:
        row["name"] = row.get("order_number")
        row["date_order"] = row.get("ordered_at")
        row["amount_total"] = row.get("total_amount")
        row["whatnot_session_id"] = row.get("session_id")
        row["whatnot_session_id_name"] = row.get("session_name")
    total_spent = round(sum(row.get("amount_total") or 0 for row in orders), 2)
    total_profit = round(sum(row.get("order_profit") or 0 for row in orders), 2)
    return {"ok": True, "orders": orders, "total_spent": total_spent, "total_profit": total_profit}


def get_legacy_company_history_sessions(limit: int = 15):
    return {"ok": True, "sessions": get_company_stream_history(OUR_WHATNOT_ACCOUNT, limit=int(limit))}


def get_legacy_company_history_detail(stream_id: int):
    if not stream_id:
        return {"ok": False, "error": "stream_id required", "_status": 400}
    detail = get_company_stream_detail(int(stream_id))
    report_rows = []
    customer_map = {
        (row.get("whatnot_username") or "").strip().lower(): row
        for row in list_customers()
        if (row.get("whatnot_username") or "").strip()
    }
    sale_order_users = {
        (row.get("whatnot_buyer_username") or "").strip().lower()
        for row in list_sale_orders()
        if (row.get("whatnot_buyer_username") or "").strip()
    }
    for idx, row in enumerate(detail.get("winners", []), start=1):
        username = (row.get("winner_username") or "").strip()
        product_name = row.get("product_name") or "(no scan)"
        match = re.search(r"\((\d+)\s+products?\)", product_name, re.IGNORECASE)
        item_count = int(match.group(1)) if match else 1
        partner = customer_map.get(username.lower()) if username else None
        report_rows.append({
            "id": idx,
            "username": username,
            "lot_number": row.get("lot_number") or "—",
            "product_name": product_name,
            "items_sold": item_count,
            "sale_price": row.get("sale_price") or 0,
            "fees": row.get("fees"),
            "profit": row.get("profit"),
            "customer_id": partner.get("id") if partner else None,
            "customer_name": partner.get("display_name") if partner else None,
            "has_sale_order": username.lower() in sale_order_users if username else False,
        })
    return {
        "ok": True,
        "winners": detail.get("winners", []),
        "products": detail.get("products", []),
        "buyers": detail.get("buyers", []),
        "report_rows": report_rows,
        "total_revenue": detail.get("total_revenue") or 0,
        "total_cost": detail.get("total_cost") or 0,
        "total_fees": detail.get("total_fees") or 0,
        "total_profit": detail.get("total_profit") or 0,
        "lots_sold": detail.get("lots_sold") or 0,
        "total_messages": detail.get("total_messages") or 0,
    }


def get_legacy_product_profit_report(session_id: int | None = None, q: str = ""):
    rows = get_product_profit_rows(session_id=session_id or None, q=(q or "").strip() or None)
    for row in rows:
        row["session_id_name"] = row.get("session_name")
    return {"ok": True, "rows": rows}
