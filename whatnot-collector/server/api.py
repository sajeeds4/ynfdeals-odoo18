"""
HTTP API handler — all REST endpoints for the dashboard.
Serves JSON API + static files from Vite build.
"""

import csv
import base64
import cgi
import copy
import io
import json
import mimetypes
import os
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from .config import (
    DB_PATH, VITE_DIST_PATH, COLLECTOR_COOKIES_PATH, API_SECRET_KEY,
    ODOO_URL, ODOO_DB, ODOO_USER, ODOO_API_KEY, MAX_SPECTATOR_STREAMS,
    DASHBOARD_HTTPS_ONLY, DASHBOARD_HSTS_ENABLED, DASHBOARD_CSP,
    dashboard_origin_allowed,
    SPECTATOR_STARTS_ENABLED,
    POSTGRES_SIDECAR_SCHEMA,
)
from .auth import (
    auth_enabled, authenticate_user, begin_totp_setup, confirm_totp_setup,
    csrf_header_name, destroy_session, disable_totp, get_mfa_status,
    get_session, get_user_public_profile, session_cookie_name,
    list_active_sessions, revoke_user_sessions, list_auth_users_public,
    upsert_auth_user, change_password, issue_login_challenge,
    consume_login_challenge,
    list_auth_activity, lookup_auth_user,
)
from .events_db import (
    get_latest_id, get_events_since, get_recent_events, latest_db_event, get_stream_id,
    get_all_streams, get_spectator_insights, get_competitor_listings,
    get_stream_users, get_user_purchases, get_competitor_businesses,
    save_failed_ingest, get_failed_ingests, mark_failed_ingest_resolved,
    increment_retry_count, get_collector_health,
    get_analytics_trends, get_analytics_buyer_overlap,
    get_company_stream_history, get_company_stream_detail, get_event_by_id,
    get_stream_event_summary, get_audience_users, get_audience_user_profile, get_target_buyers,
    get_stream_title_quality, get_stream_detection_feed, resolve_stream_sold_products,
    get_stream_reconciled_state,
    get_analytics_chat_signals, get_analytics_timing, get_analytics_products_intel,
    get_streamer_name_for_stream,
    get_cross_stream_users, get_competitor_price_products,
)
from .state import (
    load_collector_state, save_collector_state,
    shared_scan_for_session, set_shared_scan_for_session,
    clear_shared_scan_for_session,
)
from .collector_manager import (
    collector_status, live_collector_status, collectors_status,
    start_collector, start_live_collector, stop_collector, stop_live_collector,
    spectator_status, start_spectator, stop_spectator, start_spectator_batch,
    priority_spectator_status, start_priority_spectator_batch, stop_priority_spectator,
)
from .company_db import list_company_sessions, get_company_session, update_company_session
from .company_db import (
    list_buyer_groups, list_sale_orders, list_sale_orders_fast, sale_order_list_summary, list_sale_order_lines,
    list_sale_order_lines_bulk,
    list_customers, list_customer_orders, get_product_profit_rows,
    list_products, inventory_summary, list_categories, get_product_detail,
    list_inventory_movements, set_product_details, get_product, record_inventory_movement,
    ensure_category, upsert_product, get_setting_map, upsert_setting,
    create_sale_order, create_company_session, find_product_by_code,
    reserved_qty_for_product, ensure_company_bucket, get_current_company_lot,
    create_company_lot,
    rename_company_lot, mark_lot_items_status, latest_reusable_lot,
    add_lot_item, replace_lot_items_for_scan, list_lot_items, get_lot_item, update_lot_item,
    record_auction_result, update_company_lot, create_buyer_group,
    list_auction_results, list_buyer_group_lines, list_company_lots,
    upsert_customer, get_company_session_for_stream, get_company_lot_by_number,
    get_sale_order, update_sale_order, update_sale_order_line, delete_sale_order_line,
    get_customer, update_customer, add_sale_order_line, bulk_update_sale_orders,
    get_customer_by_username,
    get_inventory_prep_overview, end_company_session,
    delete_company_session_tree,
    get_or_create_buyer_sale_order, add_sale_order_line_for_item,
    apply_sale_order_inventory, reverse_sale_order_inventory,
    delete_category, delete_product, list_vendors,
    get_auction_result_by_source_event_id, get_auction_result, update_auction_result,
    queue_pending_winner_assignment, list_pending_winner_assignments,
    assign_pending_winner_product, confirm_pending_winner_assignment,
    update_pending_winner_assignment_status, undo_confirm_pending_winner_assignment,
    remove_pending_winner_assignment_item, update_pending_winner_assignment_lot_number,
    delete_pending_winner_assignment,
    sync_pending_winner_assignment_items_from_lot,
    create_pick_list, add_pick_list_item, list_pick_lists,
    get_pick_list, list_pick_list_items, find_existing_sale_order,
    get_customer_analytics, deduct_inventory_for_lot,
    list_inventory_audit_logs,
    get_inventory_integrity_audit,
    get_inventory_movement_reference_totals,
    apply_tiktok_live_session_inventory,
    replace_tiktok_live_lot_product,
    approve_payments_from_picklist_lots,
    create_in_house_sale, list_in_house_sales, in_house_sales_summary, list_employee_accounts,
    create_employee_pos_token, get_employee_pos_token, list_internal_pos_products,
    create_in_house_order, list_in_house_orders, get_in_house_order, in_house_orders_summary,
    approve_in_house_order, reject_in_house_order, cancel_in_house_order,
    complete_in_house_checkout, update_in_house_order, split_in_house_order,
    list_in_house_buyer_profiles, merge_in_house_orders, update_employee_account_settings,
    get_mega_dashboard_summary, list_reviews_feed, TIKTOK_PRODUCT_FIELDS,
    list_purchase_orders, get_purchase_order_detail, create_purchase_order, update_purchase_order, delete_purchase_order,
    receive_purchase_order, create_bargain_session, get_bargain_sessions_for_order, accept_bargain, reject_bargain,
)
from .ingest_cutover import ensure_ingest_stream
from .analytics import get_analytics_overview, get_company_livestream_intelligence, get_spectator_market_pulse
from .packing_slip import parse_packing_slip_pdf, match_lots_to_products, _parse_slip_page
from .whatnot_reviews import get_review_sync_status, sync_seller_reviews
from app.services.google_sheets_backup_service import (
    enqueue_tiktok_live_sheet_backup,
    get_full_workbook_backup_status,
    get_tiktok_live_sheet_backup_status,
    sync_full_workbook_backup_to_google_sheet,
)
from app.services.tiktok_shop_integration_service import get_recent_tiktok_order_line_matches, list_tracked_tiktok_returns
from app.services.purchases_service import build_purchase_pdf, get_bargain_by_token, submit_bargain_quote
from .sidecar_read import (
    sidecar_status as get_sidecar_status,
    get_overview_summary as get_sidecar_overview_summary,
    get_active_session_summary as get_sidecar_active_session_summary,
    get_pending_winners_summary as get_sidecar_pending_winners_summary,
    get_auction_results_summary as get_sidecar_auction_results_summary,
    get_inventory_summary as get_sidecar_inventory_summary,
    get_parity_report as get_sidecar_parity_report,
)
from .reconciler import (
    materialize_recent_stream_facts,
    materialize_stream_facts,
    materialize_streamer_facts,
    list_fact_lots,
    materialize_recent_stream_buyer_facts,
    materialize_stream_buyer_facts,
    materialize_streamer_buyer_facts,
    list_fact_buyers,
    materialize_recent_stream_product_facts,
    materialize_stream_product_facts,
    materialize_streamer_product_facts,
    list_fact_products,
    materialize_stream_intelligence,
    list_intelligence_signals,
)
from .postgres_cutover import _pg_connect, ensure_wave1_postgres_schema, postgres_available, sql


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

OUR_WHATNOT_ACCOUNT = "ynfdeals"
API_PERF_LOG_PATH = os.path.join(os.path.dirname(DB_PATH), "api_perf_requests.jsonl")
API_PERF_SLOW_MS = 400
API_PERF_LARGE_BYTES = 300_000
TARGET_COMPETITOR_WATCHLIST = [
    "perfumeastore",
    "giftexpress",
    "zeniausa",
    "tripletraders",
    "savvyscoop",
    "trendingfragrances",
]


def _append_api_perf_event(event):
    try:
        with open(API_PERF_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=True) + "\n")
    except Exception:
        pass

_TIKTOK_GO_LIVE_SHEET_SYNC_PREFIX = "tiktok_go_live_sheet_sync:"
_TIKTOK_GO_LIVE_SYNC_STATE: dict[int, dict] = {}
_TIKTOK_GO_LIVE_SYNC_LOCK = threading.Lock()
_TIKTOK_GO_LIVE_LIVE_ORDER_LOOKBACK_SECONDS = 3600


def _tiktok_go_live_sheet_sync_key(session_id):
    return f"{_TIKTOK_GO_LIVE_SHEET_SYNC_PREFIX}{int(session_id)}"


def _get_tiktok_go_live_sheet_sync(session_id):
    if not session_id:
        return None
    settings = get_setting_map() or {}
    raw = settings.get(_tiktok_go_live_sheet_sync_key(session_id))
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _set_tiktok_go_live_sheet_sync(session_id, payload):
    clean = dict(payload or {})
    clean["enabled"] = bool(clean.get("enabled", True))
    clean["sheet_url"] = str(clean.get("sheet_url") or "").strip()
    clean["manualOrdersOnly"] = bool(clean.get("manualOrdersOnly", False))
    clean["updated_at"] = datetime.now(timezone.utc).isoformat()
    upsert_setting(_tiktok_go_live_sheet_sync_key(session_id), json.dumps(clean, sort_keys=True))
    with _TIKTOK_GO_LIVE_SYNC_LOCK:
        _TIKTOK_GO_LIVE_SYNC_STATE.pop(int(session_id), None)
    return clean


def _get_tiktok_go_live_sheet_sync_state(session_id):
    if not session_id:
        return {}
    with _TIKTOK_GO_LIVE_SYNC_LOCK:
        return dict(_TIKTOK_GO_LIVE_SYNC_STATE.get(int(session_id)) or {})


_DUPE_RESEARCH_CACHE = None
_ENRICHMENT_RESEARCH_CACHE = None
_live_obs_session_id = None


def _latest_stream_rows_by_url(stream_urls):
    wanted = {str(url or "").strip() for url in (stream_urls or []) if str(url or "").strip()}
    if not wanted:
        return {}
    latest = {}
    for row in get_all_streams():
        url = str(row.get("stream_url") or "").strip()
        if not url or url not in wanted or url in latest:
            continue
        latest[url] = dict(row)
    return latest


def _get_stream_row_by_id(stream_id):
    try:
        target = int(stream_id)
    except Exception:
        return None
    for row in get_all_streams():
        try:
            if int(row.get("id") or 0) == target:
                return dict(row)
        except Exception:
            continue
    return None


def _tiktok_lot_number_from_external_ref(external_ref):
    parts = str(external_ref or "").split(":")
    if len(parts) >= 3 and parts[-1].strip().isdigit():
        return parts[-1].strip()
    return None


def _build_sale_order_picklist_payload(session_id=None, order_source="whatnot", ordered_date=None):
    rows = [
        row for row in (list_sale_orders(session_id=session_id or None, order_source=order_source) or [])
        if row.get("state") != "cancel"
        and not str(row.get("external_order_ref") or "").startswith("archived_duplicate:")
    ]
    if ordered_date:
        rows = [
            row for row in rows
            if str(row.get("ordered_at") or row.get("created_at") or "")[:10] == str(ordered_date)
        ]
    shipments_by_buyer = {}
    total_revenue = 0.0
    total_units = 0
    order_ids = [int(row["id"]) for row in rows if row.get("id")]
    line_rows = list_sale_order_lines_bulk(order_ids) if order_ids else []
    lines_by_order = {}
    for line in line_rows:
        try:
            lines_by_order.setdefault(int(line.get("sale_order_id")), []).append(line)
        except Exception:
            continue

    products_by_id = {}
    products_by_barcode = {}
    products_by_sku = {}
    products_by_name = {}
    try:
        product_rows = list_products(active_only=False, low_stock_only=False) or []
    except Exception:
        product_rows = []
    for product in product_rows:
        if product.get("id") is not None:
            try:
                products_by_id[int(product["id"])] = product
            except Exception:
                pass
        barcode = str(product.get("barcode") or "").strip()
        sku = str(product.get("sku") or "").strip()
        name = str(product.get("name") or "").strip()
        if barcode:
            products_by_barcode[barcode] = product
        if sku:
            products_by_sku[sku.lower()] = product
        if name:
            products_by_name[name.lower()] = product

    for order in rows:
        lines = lines_by_order.get(int(order["id"])) or []
        items = []
        shipment_total = 0.0
        shipment_units = 0
        for line in lines:
            qty_value = float(line.get("qty") or 1)
            qty = int(qty_value) if float(qty_value).is_integer() else max(1, int(round(qty_value)))
            qty = max(1, qty)
            description = (
                line.get("description")
                or line.get("buyer_line_product_name")
                or line.get("product_name")
                or "Unassigned item"
            )
            product_name = str(description or "").strip() or "Unassigned item"
            product_meta = None
            if line.get("product_id"):
                try:
                    product_meta = products_by_id.get(int(line.get("product_id")))
                except Exception:
                    product_meta = None
            if not product_meta:
                line_barcode = str(line.get("barcode") or "").strip()
                if line_barcode:
                    product_meta = products_by_barcode.get(line_barcode)
            if not product_meta:
                line_sku = str(line.get("sku") or "").strip().lower()
                if line_sku:
                    product_meta = products_by_sku.get(line_sku)
            if not product_meta:
                product_meta = products_by_name.get(product_name.lower())
            barcode = str(line.get("barcode") or (product_meta or {}).get("barcode") or "").strip() or None
            sku = str(line.get("sku") or (product_meta or {}).get("sku") or "").strip() or None
            price = float(line.get("subtotal") or (float(line.get("unit_price") or 0) * qty) or 0)
            shipment_total += price
            shipment_units += qty
            total_units += qty
            line_lot_number = (
                str(line.get("lot_number") or "").strip()
                or _tiktok_lot_number_from_external_ref(order.get("external_order_ref"))
            )
            items.append({
                "lot_number": line_lot_number or None,
                "product_name": product_name,
                "price": price,
                "sale_price": price,
                "qty": qty,
                "barcode": barcode,
                "sku": sku,
                "matched": True,
                "order_id": order["id"],
                "external_order_ref": order.get("external_order_ref"),
                "order_number": order.get("order_number"),
            })
        if not items:
            continue
        total_revenue += shipment_total
        buyer_username = str(order.get("whatnot_buyer_username") or "").strip()
        buyer_name = str(order.get("display_name") or "").strip()
        buyer_key = (buyer_username or buyer_name or f"customer:{order.get('customer_id') or order['id']}").lower()
        shipment = shipments_by_buyer.get(buyer_key)
        if not shipment:
            shipment = {
                "username": buyer_username or None,
                "buyer_name": buyer_name or buyer_username or None,
                "tracking_number": order.get("tracking_number"),
                "shipping_method": order.get("tracking_carrier"),
                "customer_id": order.get("customer_id"),
                "sale_order_id": order["id"],
                "order_number": order.get("order_number"),
                "order_numbers": [],
                "items": [],
                "total_items": 0,
                "total_lines": 0,
                "total_price": 0.0,
                "order_count": 0,
            }
            shipments_by_buyer[buyer_key] = shipment

        shipment["items"].extend(items)
        shipment["total_items"] += shipment_units
        shipment["total_lines"] += len(items)
        shipment["total_price"] += shipment_total
        shipment["order_count"] += 1
        if order.get("order_number"):
            shipment["order_numbers"].append(order.get("order_number"))
        if not shipment.get("tracking_number") and order.get("tracking_number"):
            shipment["tracking_number"] = order.get("tracking_number")
        if not shipment.get("shipping_method") and order.get("tracking_carrier"):
            shipment["shipping_method"] = order.get("tracking_carrier")

    shipments = list(shipments_by_buyer.values())
    for ship in shipments:
        ship["items"].sort(
            key=lambda item: (
                int(item["lot_number"]) if str(item.get("lot_number") or "").isdigit() else 10**9,
                str(item.get("lot_number") or ""),
                str(item.get("product_name") or "").lower(),
            )
        )
        ship["order_numbers"] = [value for value in ship.get("order_numbers", []) if value]

    shipments.sort(key=lambda ship: ((ship.get("username") or ship.get("buyer_name") or "").lower(), ship.get("sale_order_id") or 0))
    return {
        "ok": True,
        "shipments": shipments,
        "summary": {
            "session_id": int(session_id) if session_id else None,
            "ordered_date": ordered_date or None,
            "total_shipments": len(shipments),
            "total_lots": sum(len(ship.get("items") or []) for ship in shipments),
            "total_units": total_units,
            "matched": sum(len(ship.get("items") or []) for ship in shipments),
            "unmatched": 0,
            "total_revenue": round(total_revenue, 2),
            "orders_synced": len(shipments),
        },
    }
TV_PREVIEW_MAX_ITEMS = 4
_live_obs_product = None
_live_obs_trays = {}


def _normalize_username(value):
    return str(value or "").strip().lstrip("@").lower()


def _parse_tracked_usernames(value):
    raw = str(value or "").strip()
    if not raw:
        return []
    seen = set()
    items = []
    for part in raw.replace("\n", ",").split(","):
        username = _normalize_username(part)
        if not username or username in seen:
            continue
        seen.add(username)
        items.append(username)
    return items


def _tracked_spectator_alerts(usernames, max_events=500):
    usernames = [_normalize_username(name) for name in (usernames or []) if _normalize_username(name)]
    if not usernames:
        return []

    active_urls = [
        str(row.get("stream_url") or "").strip()
        for row in spectator_status() + priority_spectator_status()
        if row.get("running") and str(row.get("stream_url") or "").strip()
    ]
    if not active_urls:
        return []

    stream_rows = _latest_stream_rows_by_url(active_urls)
    stream_map = {
        int(row["id"]): {
            "id": int(row["id"]),
            "stream_url": row.get("stream_url"),
            "streamer_name": row.get("streamer_name") or row.get("title") or row.get("stream_url"),
        }
        for row in stream_rows.values()
        if row.get("id")
    }
    stream_ids = list(stream_map.keys())
    if not stream_ids:
        return []

    event_rows = []
    for stream_id in stream_ids:
        try:
            stream_events = get_recent_events(max(50, int(max_events or 500)), stream_id=stream_id)
        except Exception:
            stream_events = []
        for row in stream_events:
            if row.get("event_type") not in ("chat_message", "bid_event", "auction_winner"):
                continue
            event_rows.append({
                "stream_id": int(stream_id),
                "event_type": row.get("event_type"),
                "payload": row.get("payload"),
                "created_at": row.get("created_at"),
            })
    event_rows.sort(key=lambda row: (str(row.get("created_at") or ""), int(row.get("stream_id") or 0)), reverse=True)
    event_rows = event_rows[: max(50, int(max_events or 500))]

    matched = {}
    for row in event_rows:
        payload_raw = row["payload"]
        try:
            payload = json.loads(payload_raw or "{}")
        except Exception:
            payload = {}
        event_type = str(row["event_type"] or "")
        if event_type == "chat_message":
            event_user = _normalize_username(payload.get("username") or payload.get("user"))
        elif event_type == "bid_event":
            event_user = _normalize_username(payload.get("username") or payload.get("user") or payload.get("bidder"))
        else:
            event_user = _normalize_username(
                payload.get("winner") or payload.get("winner_username") or payload.get("username")
            )
        if event_user not in usernames:
            continue

        bucket = matched.setdefault(event_user, {
            "username": event_user,
            "streams": set(),
            "chat_messages": 0,
            "bids": 0,
            "wins": 0,
            "latest_chat": None,
            "latest_bid": None,
            "latest_win": None,
            "latest_seen_at": row["created_at"],
        })
        stream_meta = stream_map.get(int(row["stream_id"])) or {}
        bucket["streams"].add(stream_meta.get("streamer_name") or stream_meta.get("stream_url") or f"stream:{row['stream_id']}")
        if not bucket["latest_seen_at"] or str(row["created_at"] or "") > str(bucket["latest_seen_at"] or ""):
            bucket["latest_seen_at"] = row["created_at"]

        if event_type == "chat_message":
            bucket["chat_messages"] += 1
            if bucket["latest_chat"] is None:
                bucket["latest_chat"] = {
                    "streamer_name": stream_meta.get("streamer_name"),
                    "stream_url": stream_meta.get("stream_url"),
                    "message": payload.get("message") or payload.get("text") or "",
                    "created_at": row["created_at"],
                }
        elif event_type == "bid_event":
            bucket["bids"] += 1
            if bucket["latest_bid"] is None:
                bucket["latest_bid"] = {
                    "streamer_name": stream_meta.get("streamer_name"),
                    "stream_url": stream_meta.get("stream_url"),
                    "amount": payload.get("amount"),
                    "raw_amount": payload.get("raw_amount"),
                    "lot_number": payload.get("lot_number"),
                    "created_at": row["created_at"],
                }
        elif event_type == "auction_winner":
            bucket["wins"] += 1
            if bucket["latest_win"] is None:
                bucket["latest_win"] = {
                    "streamer_name": stream_meta.get("streamer_name"),
                    "stream_url": stream_meta.get("stream_url"),
                    "price": payload.get("price") or payload.get("price_value") or payload.get("winning_price"),
                    "lot_number": payload.get("lot_number"),
                    "created_at": row["created_at"],
                }

    alerts = []
    for username, info in matched.items():
        fragments = []
        if info["chat_messages"]:
            chat = info.get("latest_chat") or {}
            msg = str(chat.get("message") or "").strip()
            fragments.append(f"{info['chat_messages']} chat")
            if msg:
                fragments.append(f'latest chat: "{msg[:80]}"')
        if info["bids"]:
            bid = info.get("latest_bid") or {}
            amount = bid.get("raw_amount") or bid.get("amount")
            fragments.append(f"{info['bids']} bid")
            if amount:
                fragments.append(f"latest bid {amount}")
        if info["wins"]:
            win = info.get("latest_win") or {}
            fragments.append(f"{info['wins']} win")
            if win.get("price"):
                fragments.append(f"latest win {win.get('price')}")
        alerts.append({
            "type": "tracked_buyer_activity",
            "severity": "warning",
            "username": username,
            "streams": sorted(info["streams"]),
            "latest_seen_at": info["latest_seen_at"],
            "chat_messages": info["chat_messages"],
            "bids": info["bids"],
            "wins": info["wins"],
            "latest_chat": info.get("latest_chat"),
            "latest_bid": info.get("latest_bid"),
            "latest_win": info.get("latest_win"),
            "message": f"Tracked buyer @{username} active in {len(info['streams'])} stream(s): " + ", ".join(fragments),
        })
    alerts.sort(key=lambda item: str(item.get("latest_seen_at") or ""), reverse=True)
    return alerts


def _safe_file_stats(path):
    try:
        if not path or not os.path.exists(path):
            return {"path": path, "exists": False, "size_bytes": 0, "modified_at": None}
        stat = os.stat(path)
        return {
            "path": path,
            "exists": True,
            "size_bytes": int(stat.st_size),
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        }
    except Exception:
        return {"path": path, "exists": False, "size_bytes": 0, "modified_at": None}


def _tail_log_lines(path, limit=200):
    limit = max(1, min(int(limit or 200), 1000))
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-limit:]
    except Exception:
        return []
    return [line.rstrip("\n") for line in lines]


def _classify_log_level(line):
    text = str(line or "").lower()
    if any(token in text for token in ("traceback", "exception", "error", "failed", "epipe", "fatal")):
        return "error"
    if any(token in text for token in ("warning", "warn", "degraded", "stalled", "timeout", "challenge")):
        return "warning"
    return "info"


def _diagnostic_log_entries(path, source, limit=200):
    entries = []
    for idx, line in enumerate(_tail_log_lines(path, limit=limit)):
        entries.append({
            "id": f"{source}:{idx}",
            "source": source,
            "level": _classify_log_level(line),
            "message": line,
        })
    return entries


def _resolve_our_stream_context(*, running_only=False):
    our_urls = set()
    status = collector_status()
    if status.get("stream_url"):
        our_urls.add(status["stream_url"])
    saved = load_collector_state()
    if saved.get("stream_url"):
        our_urls.add(saved["stream_url"])
    our_base_urls = {u.split("?")[0] for u in our_urls if u}
    our_streamer_names = set()
    for url in our_urls | our_base_urls:
        sid = get_stream_id(url)
        if not sid:
            continue
        streamer_name = (get_streamer_name_for_stream(sid) or "").strip()
        if streamer_name:
            our_streamer_names.add(streamer_name)

    allowed_stream_ids = None
    if running_only:
        running_urls = {
            (s.get("stream_url") or "").split("?")[0]
            for s in spectator_status()
            if s.get("running") and s.get("stream_url")
        }
        if running_urls:
            allowed_stream_ids = [
                int(row.get("id"))
                for row in get_all_streams()
                if int(row.get("id") or 0) > 0
                and ((row.get("stream_url") or "").split("?")[0] in running_urls)
            ]
        else:
            allowed_stream_ids = []

    return {
        "our_urls": our_urls,
        "our_base_urls": our_base_urls,
        "our_streamer_names": our_streamer_names,
        "allowed_stream_ids": allowed_stream_ids,
    }


def _db_table_health(limit_tables=25):
    tables = []
    try:
        if postgres_available():
            ensure_wave1_postgres_schema()
            with _pg_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT tablename
                        FROM pg_catalog.pg_tables
                        WHERE schemaname = %s
                        ORDER BY tablename
                        """,
                        (POSTGRES_SIDECAR_SCHEMA,),
                    )
                    table_rows = [row[0] for row in cur.fetchall()]
                    for name in table_rows[: max(1, int(limit_tables or 25))]:
                        identifier = sql.Identifier(POSTGRES_SIDECAR_SCHEMA, name)
                        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(identifier))
                        count_row = cur.fetchone()
                        tables.append({"name": name, "row_count": int((count_row or [0])[0] or 0)})
        else:
            tables.append({"name": "postgres_unavailable", "row_count": 0, "error": "Postgres diagnostics unavailable"})
    except Exception as exc:
        tables.append({"name": "db_error", "row_count": 0, "error": str(exc)})
    return tables


def _build_system_diagnostics(log_limit=200):
    stream = live_collector_status()
    stream_id = stream.get("stream_id")
    health = get_collector_health(stream_id=stream_id if stream_id else None)
    failed_records = get_failed_ingests(include_resolved=True)
    unresolved = [row for row in failed_records if not row.get("resolved")]
    needs_review = [row for row in unresolved if row.get("needs_review")]

    dashboard_log = os.path.join(os.path.dirname(DB_PATH), "dashboard_server.log")
    collector_log = os.path.join(os.path.dirname(DB_PATH), "collector.log")
    data_dir = os.path.dirname(DB_PATH)
    db_files = [
        DB_PATH,
        os.path.join(data_dir, "whatnot_events.sqlite"),
        os.path.join(data_dir, "whatnot_company.sqlite"),
    ]

    log_entries = (
        _diagnostic_log_entries(dashboard_log, "api", limit=log_limit)
        + _diagnostic_log_entries(collector_log, "collector", limit=log_limit)
    )
    log_entries.sort(key=lambda item: item["id"], reverse=True)
    log_counts = {"error": 0, "warning": 0, "info": 0}
    for row in log_entries:
        log_counts[row["level"]] = log_counts.get(row["level"], 0) + 1

    status_flags = []
    if unresolved:
        status_flags.append({"level": "warning", "message": f"{len(unresolved)} unresolved failed ingests"})
    if needs_review:
        status_flags.append({"level": "error", "message": f"{len(needs_review)} failed ingests need review"})
    for key in ("chat_message", "lot_update", "bid_update", "auction_winner"):
        ts = health.get(key)
        if not ts:
            status_flags.append({"level": "warning", "message": f"No {key.replace('_', ' ')} seen yet"})

    process_started_at = None
    try:
        proc_stat = os.stat(f"/proc/{os.getpid()}")
        process_started_at = datetime.fromtimestamp(proc_stat.st_ctime, timezone.utc).isoformat()
    except Exception:
        pass

    live_session = None
    live_lot = None
    pending_rows = []
    confirmed_rows = []
    duplicate_lot_rows = []
    timeline = []
    try:
        live_session = _current_company_session()
        if live_session:
            live_lot = get_current_company_lot(int(live_session["id"]))
            pending_rows = list_pending_winner_assignments(int(live_session["id"]), statuses=("pending", "assigned", "needs_review"), limit=200)
            confirmed_rows = list_pending_winner_assignments(int(live_session["id"]), statuses=("confirmed",), limit=25)
            latest_results = list_auction_results(session_id=int(live_session["id"]), limit=20)
            duplicate_sources = [
                ("auction_results", latest_results),
                ("winner_queue", pending_rows),
            ]
            for source_name, source_rows in duplicate_sources:
                grouped = {}
                for row in source_rows:
                    lot_number = str(row.get("lot_number") or "").strip()
                    if not lot_number:
                        continue
                    grouped.setdefault(lot_number, []).append(row)
                for lot_number, grouped_rows in grouped.items():
                    if len(grouped_rows) <= 1:
                        continue
                    duplicate_lot_rows.append({
                        "source": source_name,
                        "lot_number": lot_number,
                        "dup_count": len(grouped_rows),
                        "row_ids": ",".join(str(row.get("id")) for row in grouped_rows if row.get("id")),
                        "prices": ",".join(str(float(row.get("sale_price") or 0)) for row in grouped_rows),
                    })
            duplicate_lot_rows.sort(key=lambda item: (str(item.get("lot_number") or ""), str(item.get("source") or "")))
            for row in latest_results[:12]:
                timeline.append({
                    "kind": "auction_result",
                    "at": row.get("sold_at"),
                    "lot_number": row.get("lot_number"),
                    "winner_username": row.get("winner_username"),
                    "label": f"Lot {row.get('lot_number') or '—'} sold to @{row.get('winner_username') or 'unknown'}",
                    "detail": row.get("product_name") or "No product assigned",
                    "level": "info",
                })
            for row in pending_rows[:12]:
                timeline.append({
                    "kind": "winner_queue",
                    "at": row.get("detected_at") or row.get("updated_at") or row.get("created_at"),
                    "lot_number": row.get("lot_number"),
                    "winner_username": row.get("winner_username"),
                    "label": f"Queue {str(row.get('status') or 'pending').upper()} · lot {row.get('lot_number') or '—'}",
                    "detail": f"@{row.get('winner_username') or 'unknown'} · ${float(row.get('sale_price') or 0):.2f}",
                    "level": "warning" if row.get("status") == "needs_review" else "info",
                })
        for row in unresolved[:10]:
            timeline.append({
                "kind": "failed_ingest",
                "at": row.get("created_at"),
                "lot_number": row.get("lot_number"),
                "winner_username": row.get("winner_username"),
                "label": f"Failed ingest · lot {row.get('lot_number') or '—'}",
                "detail": row.get("error_message") or "winner sync failed",
                "level": "error" if row.get("needs_review") else "warning",
            })
    except Exception as exc:
        status_flags.append({"level": "warning", "message": f"Diagnostics partial failure: {exc}"})

    timeline.sort(key=lambda item: str(item.get("at") or ""), reverse=True)

    latest_pending = pending_rows[0] if pending_rows else None
    latest_confirmed = confirmed_rows[0] if confirmed_rows else None
    safety = {
        "session_id": live_session.get("id") if live_session else None,
        "session_name": live_session.get("name") if live_session else None,
        "current_lot_number": live_lot.get("lot_number") if live_lot else None,
        "pending_queue_depth": len([row for row in pending_rows if row.get("status") == "pending"]),
        "assigned_queue_depth": len([row for row in pending_rows if row.get("status") == "assigned"]),
        "needs_review_depth": len([row for row in pending_rows if row.get("status") == "needs_review"]),
        "latest_pending": latest_pending,
        "latest_confirmed": latest_confirmed,
        "duplicate_lot_count": len(duplicate_lot_rows),
        "safe": len(duplicate_lot_rows) == 0 and len(needs_review) == 0,
    }

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api": {
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "started_at": process_started_at,
            "uptime_seconds": max(0, int(time.time() - os.stat(f"/proc/{os.getpid()}").st_ctime)) if os.path.exists(f"/proc/{os.getpid()}") else None,
        },
        "stream": stream,
        "collector_health": health,
        "failed_ingests": {
            "unresolved_count": len(unresolved),
            "needs_review_count": len(needs_review),
            "recent": unresolved[:25],
        },
        "database": {
            "path": DB_PATH,
            "files": [_safe_file_stats(path) for path in db_files],
            "tables": _db_table_health(limit_tables=40),
        },
        "logs": {
            "counts": log_counts,
            "entries": log_entries[: max(1, min(int(log_limit or 200), 300))],
            "files": {
                "api": _safe_file_stats(dashboard_log),
                "collector": _safe_file_stats(collector_log),
            },
        },
        "live_safety": safety,
        "duplicates": duplicate_lot_rows,
        "timeline": timeline[:30],
        "flags": status_flags,
    }


def _load_dupe_research():
    global _DUPE_RESEARCH_CACHE
    if _DUPE_RESEARCH_CACHE is not None:
        return _DUPE_RESEARCH_CACHE
    path = os.path.join(os.path.dirname(DB_PATH), "exports", "inventory_dupe_research_full.csv")
    if not os.path.exists(path):
        alt = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports", "inventory_dupe_research_full.csv")
        path = alt
    rows = {}
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                product_id = str(row.get("product_id") or "").strip()
                if product_id:
                    rows[product_id] = row
    _DUPE_RESEARCH_CACHE = rows
    return _DUPE_RESEARCH_CACHE


def _dupe_research_for_product(product):
    if not product:
        return None
    manual = _normalize_dupe_research_item({
        "inspiration_fragrance": product.get("dupe_inspiration"),
        "confidence": product.get("dupe_confidence"),
        "classification": product.get("dupe_classification"),
        "notes": product.get("dupe_notes"),
    })
    if manual and any(manual.get(key) for key in ("inspiration_fragrance", "confidence", "classification", "notes")):
        return manual
    rows = _load_dupe_research()
    item = rows.get(str(product.get("id") or "").strip())
    dupe = _normalize_dupe_research_item(item) if item else None
    if dupe and dupe.get("inspiration_fragrance"):
        return dupe
    enrichment = _enrichment_research_for_product(product)
    if enrichment and enrichment.get("inspiration_fragrance"):
        return enrichment
    return dupe or enrichment


def _clean_dupe_text(value):
    text = str(value or "").strip()
    return "" if text.lower() in {"", "unknown", "none", "null", "n/a", "na"} else text


def _normalize_dupe_research_item(item):
    if not item:
        return None
    return {
        "inspiration_fragrance": _clean_dupe_text(item.get("inspiration_fragrance")),
        "inspiration_brand": _clean_dupe_text(item.get("inspiration_brand")),
        "similarity_pct": _clean_dupe_text(item.get("similarity_pct")),
        "similarity_level": _clean_dupe_text(item.get("similarity_level")),
        "confidence": _clean_dupe_text(item.get("confidence")),
        "classification": _clean_dupe_text(item.get("classification")),
        "needs_smell_test": _clean_dupe_text(item.get("needs_smell_test")),
        "notes": _clean_dupe_text(item.get("notes") or item.get("inspiration_analysis")),
    }


def _load_enrichment_research():
    global _ENRICHMENT_RESEARCH_CACHE
    if _ENRICHMENT_RESEARCH_CACHE is not None:
        return _ENRICHMENT_RESEARCH_CACHE

    exports_dir = os.path.join(os.path.dirname(DB_PATH), "exports")
    candidates = [
        os.path.join(exports_dir, "inventory_enrichment_web.csv"),
        os.path.join(exports_dir, "inventory_enrichment_master.csv"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports", "inventory_enrichment_web.csv"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports", "inventory_enrichment_master.csv"),
    ]

    rows = {"by_product_id": {}, "by_barcode": {}, "by_name": {}}
    path = next((candidate for candidate in candidates if os.path.exists(candidate)), None)
    if path:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                product_id = str(row.get("product_id") or row.get("inventory_id") or "").strip()
                barcode = str(row.get("barcode") or row.get("sku") or "").strip()
                name = _clean_product_name(row.get("product_name") or row.get("name") or "")
                if product_id:
                    rows["by_product_id"][product_id] = row
                if barcode:
                    rows["by_barcode"][barcode] = row
                if name:
                    rows["by_name"][name.lower()] = row
    _ENRICHMENT_RESEARCH_CACHE = rows
    return _ENRICHMENT_RESEARCH_CACHE


def _enrichment_research_for_product(product):
    if not product:
        return None
    rows = _load_enrichment_research()
    product_id = str(product.get("id") or "").strip()
    barcode = str(product.get("barcode") or product.get("sku") or "").strip()
    name = _clean_product_name(product.get("name") or "").lower()
    item = (
        rows["by_product_id"].get(product_id)
        or rows["by_barcode"].get(barcode)
        or rows["by_name"].get(name)
    )
    return _normalize_dupe_research_item(item) if item else None


def _set_live_obs_scan(session_id, product):
    global _live_obs_session_id, _live_obs_product
    _live_obs_session_id = int(session_id) if session_id else None
    _live_obs_product = dict(product) if isinstance(product, dict) else None


def _set_live_obs_tray(session_id, rows):
    key = int(session_id) if session_id else None
    if not key:
        return
    _live_obs_trays[key] = [dict(row) for row in (rows or [])]


def _clear_live_obs_tray(session_id=None):
    if session_id is None:
        _live_obs_trays.clear()
        return
    try:
        _live_obs_trays.pop(int(session_id), None)
    except Exception:
        return


def _clear_live_obs_scan(session_id=None):
    global _live_obs_session_id, _live_obs_product
    if session_id is None or _live_obs_session_id == int(session_id):
        _live_obs_session_id = None
        _live_obs_product = None
    if session_id is None:
        _clear_live_obs_tray()
    else:
        _clear_live_obs_tray(session_id)


def _build_live_obs_tray_item(row):
    item = dict(row or {})
    product = None
    try:
        if item.get("product_id"):
            product = get_product(int(item["product_id"]))
    except Exception:
        product = None
    if not product:
        code = item.get("barcode") or item.get("sku")
        if code:
            product = find_product_by_code(code)
    if product:
        item.update(_build_live_item_payload({"id": item.get("lot_id"), "lot_number": item.get("lot_number")}, product, item=item))
        item["dupe_research"] = _dupe_research_for_product(product)
    item["selected"] = item.get("status") == "active"
    item["product_name"] = _clean_product_name(item.get("product_name") or item.get("name") or item.get("linked_product_name") or "")
    item["name"] = item.get("product_name")
    item["image_url"] = item.get("image_url") or (_product_image_url(product) if product else None)
    return item


def _rebuild_live_obs_tray(session_id, lot_id):
    rows = [
        row for row in list_lot_items(lot_id)
        if row.get("status") in ("open", "active", "queued")
    ]
    rows = rows[-TV_PREVIEW_MAX_ITEMS:]
    tray = []
    for row in rows:
        row["selected"] = row.get("status") == "active"
        tray.append(_build_live_obs_tray_item(row))
    _set_live_obs_tray(session_id, tray)
    return tray


def _get_live_obs_tray(session_id=None, lot_id=None):
    key = int(session_id) if session_id else None
    if key and key in _live_obs_trays:
        return [dict(row) for row in (_live_obs_trays.get(key) or [])]
    if key and lot_id:
        return _rebuild_live_obs_tray(key, lot_id)
    return []


def _safe_positive_float(value):
    try:
        number = float(value or 0)
    except Exception:
        return 0.0
    return number if number > 0 else 0.0


def _product_pricing_ladder(product):
    product = product or {}
    cost = _safe_positive_float(product.get("cost_price"))
    raw = _safe_positive_float(product.get("raw_cost")) or cost
    return {
        "raw_cost": raw,
        "cost_plus_12": _safe_positive_float(product.get("cost_plus_12")) or (round(raw * 1.12, 2) if raw else 0.0),
        "cost_plus_20": _safe_positive_float(product.get("cost_plus_20")) or (round(raw * 1.2, 2) if raw else 0.0),
    }


def _finalize_released_lot_async(lot_id):
    def worker():
        try:
            mark_lot_items_status(lot_id, to_status="dropped")
        except Exception as exc:
            print(f"[release] failed to finalize lot {lot_id}: {exc}")

    threading.Thread(target=worker, daemon=True).start()


def _persist_live_scan_async(session_id, lot_id, product, active_item):
    def worker():
        try:
            item = add_lot_item(
                lot_id,
                product_id=product["id"],
                barcode=product.get("barcode"),
                sku=product.get("sku"),
                product_name=product.get("name"),
                unit_cost=float(product.get("cost_price") or 0),
                qty_snapshot=1,
                status="open",
            )
            persisted = dict(active_item)
            persisted["id"] = item.get("id")
            persisted["barcode"] = item.get("barcode")
            persisted["sku"] = item.get("sku")
            persisted["scanned_at"] = item.get("scanned_at")
            _set_live_obs_scan(session_id, persisted)
            _rebuild_live_obs_tray(session_id, lot_id)
            set_shared_scan_for_session(session_id, persisted)
        except Exception as exc:
            print(f"[scan] failed to persist live item for session {session_id}: {exc}")
            _clear_live_obs_scan(session_id)
            clear_shared_scan_for_session(session_id)

    threading.Thread(target=worker, daemon=True).start()


def _build_live_item_payload(lot, product, item=None, qty_remaining=None, scanned_qty=None, qty_reserved=None):
    item_id = item.get("id") if item else None
    scan_qty = int(scanned_qty if scanned_qty is not None else (item.get("qty_snapshot") if item else 1) or 1)
    return {
        "id": item_id,
        "lot_id": lot.get("id"),
        "lot_number": lot.get("lot_number"),
        "product_id": product.get("id"),
        "barcode": (item.get("barcode") if item else None) or product.get("barcode"),
        "sku": (item.get("sku") if item else None) or product.get("sku"),
        "name": _clean_product_name(product.get("name")),
        "product_name": _clean_product_name(product.get("name")),
        "cost_price": product.get("cost_price"),
        **_product_pricing_ladder(product),
        "retail_price": product.get("retail_price"),
        "note_top": product.get("note_top"),
        "note_mid": product.get("note_mid"),
        "note_base": product.get("note_base"),
        "media_url": product.get("media_url"),
        "script": product.get("script"),
        "description": product.get("description"),
        "qty_available": product.get("on_hand_qty"),
        "qty_reserved": qty_reserved,
        "scanned_qty": scan_qty,
        "qty_remaining": qty_remaining,
        "scanned_at": (item.get("scanned_at") if item else None) or datetime.now(timezone.utc).isoformat(),
        "status": (item.get("status") if item else None) or "active",
        "image_url": _product_image_url(product),
    }


def _sync_selected_lot_item(session_id, lot_id, item_id=None):
    items = [row for row in list_lot_items(lot_id) if row.get("status") in ("open", "active", "queued")]
    selected = None
    if item_id:
        for row in items:
            if int(row.get("id") or 0) == int(item_id):
                selected = row
                break
    if not selected:
        selected = next((row for row in items if row.get("status") == "active"), None)
    if not selected:
        selected = items[-1] if items else None

    if not selected:
        clear_shared_scan_for_session(session_id)
        _clear_live_obs_scan(session_id)
        _set_demo_scan(None)
        return None

    for row in items:
        target_status = "active" if int(row.get("id") or 0) == int(selected.get("id") or 0) else "queued"
        if row.get("status") != target_status:
            update_lot_item(row["id"], status=target_status)
            row["status"] = target_status

    product = get_product(int(selected["product_id"])) if selected.get("product_id") else find_product_by_code(selected.get("barcode") or selected.get("sku"))
    if not product:
        payload = dict(selected)
    else:
        scanned_qty = int(selected.get("qty_snapshot") or 1)
        reserved_elsewhere = reserved_qty_for_product(session_id, product["id"], exclude_lot_id=lot_id) if product.get("id") else None
        on_hand = float(product.get("on_hand_qty") or 0)
        available_qty = None if reserved_elsewhere is None else max(on_hand - reserved_elsewhere, 0)
        qty_remaining = None if available_qty is None else max(available_qty - max(scanned_qty - 1, 0), 0)
        payload = _build_live_item_payload(
            get_current_company_lot(session_id) or {"id": lot_id},
            product,
            item=selected,
            qty_remaining=qty_remaining,
            scanned_qty=scanned_qty,
            qty_reserved=(reserved_elsewhere + scanned_qty) if reserved_elsewhere is not None else None,
        )
        payload["status"] = "active"
    set_shared_scan_for_session(session_id, payload)
    _set_live_obs_scan(session_id, payload)
    _rebuild_live_obs_tray(session_id, lot_id)
    _set_demo_scan(None)
    return payload


def _normalize_obs_product(product):
    if not isinstance(product, dict):
        return None
    normalized = dict(product)
    db_product = None
    product_id = normalized.get("product_id") or normalized.get("id")
    try:
        if product_id:
            db_product = get_product(int(product_id))
    except Exception:
        db_product = None
    if not db_product:
        code = normalized.get("barcode") or normalized.get("sku")
        if code:
            db_product = find_product_by_code(code)
    if db_product:
        normalized.setdefault("cost_price", db_product.get("cost_price"))
        normalized.setdefault("raw_cost", db_product.get("raw_cost"))
        normalized.setdefault("cost_plus_12", db_product.get("cost_plus_12"))
        normalized.setdefault("cost_plus_20", db_product.get("cost_plus_20"))
        normalized.setdefault("retail_price", db_product.get("retail_price"))
        normalized.setdefault("note_top", db_product.get("note_top"))
        normalized.setdefault("note_mid", db_product.get("note_mid"))
        normalized.setdefault("note_base", db_product.get("note_base"))
        normalized.setdefault("notes", db_product.get("notes"))
        normalized.setdefault("script", db_product.get("script"))
        normalized.setdefault("description", db_product.get("description"))
        normalized.setdefault("media_url", db_product.get("media_url"))
        normalized.setdefault("image_url", _product_image_url(db_product))
        normalized["dupe_research"] = _dupe_research_for_product(db_product)
    ladder = _product_pricing_ladder(normalized)
    normalized["raw_cost"] = ladder["raw_cost"]
    normalized["cost_plus_12"] = ladder["cost_plus_12"]
    normalized["cost_plus_20"] = ladder["cost_plus_20"]
    normalized["name"] = _clean_product_name(
        normalized.get("name")
        or normalized.get("product_name")
        or ""
    )
    return normalized


def _product_image_url(row):
    """Return the best available image URL for a product row.
    Priority: base64 image_path > media_url > None
    """
    if row.get("image_path"):
        return f"data:image/png;base64,{row['image_path']}"
    if row.get("media_url"):
        return row["media_url"]
    return None


def _download_image_as_base64(url):
    """Download a remote image and return its base64 payload for local storage."""
    candidate = str(url or "").strip()
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        return None
    request = Request(
        candidate,
        headers={
            "User-Agent": "YNFDealsInventory/1.0",
            "Accept": "image/*,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=12) as response:
        content_type = str(response.headers.get("Content-Type") or "").lower()
        if content_type and not content_type.startswith("image/"):
            return None
        payload = response.read(8 * 1024 * 1024 + 1)
        if not payload or len(payload) > 8 * 1024 * 1024:
            return None
        return base64.b64encode(payload).decode("ascii")


def _save_product_sds_pdf(product_id, pdf_base64, filename=None):
    raw = base64.b64decode(str(pdf_base64 or ""), validate=True)
    if not raw or not raw.startswith(b"%PDF"):
        raise ValueError("invalid_sds_pdf")
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("sds_pdf_too_large")
    safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "", str(filename or "").strip()) or f"product-{int(product_id)}-sds.pdf"
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    target_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "product_uploads", "sds", str(int(product_id))))
    os.makedirs(target_dir, exist_ok=True)
    stored_name = f"{stamp}-{safe_name}"
    target_path = os.path.join(target_dir, stored_name)
    with open(target_path, "wb") as handle:
        handle.write(raw)
    return target_path


INVENTORY_LIST_FIELDS = (
    "id", "name", "sku", "barcode", "category_id", "category_name", "product_type",
    "brand", "gender", "supplier_name", "storage_bin", "cost_price", "raw_cost", "cost_plus_12", "cost_plus_20", "retail_price",
    "on_hand_qty", "low_stock_threshold", "active", "notes", "notes_verified",
    "notes_verified_at", "note_top", "note_mid", "note_base", "media_url",
    "description", "size_oz", "size_ml", "volume_oz", "volume_ml", "dupe_inspiration", "dupe_confidence", "dupe_classification",
    "dupe_notes", "similar_to", "image_gallery_urls", "source_fragrantica_url",
    "source_jomashop_url", "source_parfumo_url", "source_official_url", "fragrance_research", "fragrance_research_sources", "times_sold", "sales_revenue",
    "last_sold_at", "created_at", "updated_at",
    *TIKTOK_PRODUCT_FIELDS,
)


def _inventory_list_row(row, low_stock_threshold):
    compact = {key: row.get(key) for key in INVENTORY_LIST_FIELDS if key in row}
    compact["default_code"] = compact.get("sku")
    compact["standard_price"] = compact.get("cost_price")
    compact["raw_cost"] = compact.get("raw_cost")
    compact["cost_plus_12"] = compact.get("cost_plus_12")
    compact["cost_plus_20"] = compact.get("cost_plus_20")
    compact["list_price"] = compact.get("retail_price")
    compact["qty_available"] = compact.get("on_hand_qty")
    compact["virtual_available"] = compact.get("on_hand_qty")
    compact["type"] = compact.get("product_type")
    compact["categ_id"] = compact.get("category_id")
    compact["categ_name"] = compact.get("category_name")
    # Inventory list responses must stay lightweight; image_path/base64 belongs on detail reads.
    compact["image_url"] = compact.get("media_url") or None
    compact["active"] = bool(compact.get("active", True))
    qty = compact.get("qty_available") or 0
    cost = compact.get("standard_price") or 0
    compact["stock_value"] = round(qty * cost, 2)
    compact["low_stock"] = qty <= low_stock_threshold and compact.get("type") in ("product", "storable", "consu")
    compact["times_sold"] = int(compact.get("times_sold") or 0)
    compact["sales_revenue"] = round(float(compact.get("sales_revenue") or 0), 2)
    return compact


def _inventory_compact_rows(active_only=True, include_inactive=False):
    rows = list_products(active_only=bool(active_only), low_stock_only=False)
    if include_inactive and not active_only:
        rows = [row for row in (rows or []) if not bool(row.get("active", True))]
    return rows or []


def _dedupe_auction_result_rows(rows):
    deduped = []
    seen = set()
    for row in rows or []:
        lot_number = str(row.get("lot_number") or "").strip()
        winner_username = (row.get("winner_username") or "").strip().lower()
        sale_price = round(float(row.get("sale_price") or 0), 2)
        source_event_id = str(row.get("source_event_id") or "").strip()
        key = None
        if lot_number:
            key = ("lot", lot_number)
        elif source_event_id:
            key = ("src", source_event_id)
        else:
            sold_at = str(row.get("sold_at") or "").strip()
            product_name = str(row.get("product_name") or "").strip()
            key = ("fallback", winner_username, sale_price, product_name, sold_at)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _live_top_buyers_payload(session_id):
    results = _dedupe_auction_result_rows(list_auction_results(session_id=session_id, limit=2000))
    buyer_map = {}
    for row in results:
        username = (row.get("winner_username") or row.get("display_name") or row.get("whatnot_username") or "?").strip() or "?"
        bucket = buyer_map.setdefault(username, {"username": username, "lots_won": 0, "total_spent": 0.0})
        bucket["lots_won"] += 1
        bucket["total_spent"] += float(row.get("sale_price") or 0)
    buyers = sorted(buyer_map.values(), key=lambda b: (-b["total_spent"], -b["lots_won"], b["username"].lower()))[:10]
    recent_winners = []
    for row in results[:5]:
        recent_winners.append({
            "username": row.get("winner_username") or "?",
            "price": row.get("sale_price") or 0,
            "lot_number": row.get("lot_number"),
            "sold_at": row.get("sold_at"),
        })
    return {"buyers": buyers, "recent_winners": recent_winners}

# In-memory demo scan state (resets on server restart — intentional for demo use)
# Scope the tray per partner/user so multiple scanner operators do not overwrite
# each other during the same shift.
_demo_scan_products = {}
_demo_scan_trays = {}


def _demo_scope_key(scope=None):
    value = str(scope or "global").strip()
    return value or "global"


def _get_demo_scan(scope=None):
    row = _demo_scan_products.get(_demo_scope_key(scope))
    return dict(row) if isinstance(row, dict) else row


def _set_demo_scan(product, scope=None):
    key = _demo_scope_key(scope)
    if product:
        _demo_scan_products[key] = dict(product)
    else:
        _demo_scan_products.pop(key, None)


def _clear_demo_scan_state(scope=None):
    _set_demo_scan(None, scope=scope)
    _set_demo_scan_tray([], scope=scope)


def _get_demo_scan_tray(scope=None):
    return [dict(item) for item in (_demo_scan_trays.get(_demo_scope_key(scope)) or [])]


def _set_demo_scan_tray(rows, scope=None):
    key = _demo_scope_key(scope)
    _demo_scan_trays[key] = [dict(item) for item in (rows or [])]


def _append_demo_scan(product, max_items=TV_PREVIEW_MAX_ITEMS, scope=None):
    tray = _get_demo_scan_tray(scope=scope)
    entry = dict(product or {})
    entry["status"] = "active"
    entry["selected"] = True
    entry["scanned_at"] = datetime.now(timezone.utc).isoformat()
    for row in tray:
        row["status"] = "queued"
        row["selected"] = False
    tray.append(entry)
    if len(tray) > max_items:
        tray = tray[-max_items:]
    if tray:
        tray[-1]["status"] = "active"
        tray[-1]["selected"] = True
        _set_demo_scan(tray[-1], scope=scope)
    else:
        _set_demo_scan(None, scope=scope)
    _set_demo_scan_tray(tray, scope=scope)
    return entry, tray


def _trim_preview_lot_items(lot_id, keep_item_id=None, max_items=TV_PREVIEW_MAX_ITEMS):
    active_rows = [
        row for row in list_lot_items(lot_id)
        if row.get("status") in ("open", "active", "queued")
    ]
    if len(active_rows) <= max_items:
        return
    for row in active_rows[:-max_items]:
        if keep_item_id and int(row.get("id") or 0) == int(keep_item_id):
            continue
        update_lot_item(row["id"], status="dropped")


def _infer_price_source(payload):
    if payload.get("footer_text"):
        return "footer_fallback"
    if payload.get("price"):
        return "sold_or_live_bid"
    return "missing"


def _get_spectator_diagnostics(stream_id, limit=25):
    event_rows = [
        row for row in get_recent_events(800, stream_id=int(stream_id))
        if row.get("event_type") in ("lot_update", "bid_update", "auction_winner", "auction_state")
    ]
    stream_row = _get_stream_row_by_id(stream_id)

    events = []
    for row in event_rows:
        try:
            payload = json.loads(row.get("payload") or "{}")
        except Exception:
            payload = {}
        events.append({
            "id": row["id"],
            "created_at": row["created_at"],
            "event_type": row["event_type"],
            "payload": payload,
        })

    lots = []
    active = None
    for event in events:
        payload = event["payload"]
        if event["event_type"] == "lot_update":
            active = {
                "event_id": event["id"],
                "shown_at": event["created_at"],
                "lot_number": str(payload.get("lot_number") or "—"),
                "product_name": payload.get("product_name") or payload.get("title") or "Unknown",
                "last_bid": None,
                "last_bid_at": None,
                "winner": None,
                "winner_at": None,
                "final_price": None,
                "price_source": "missing",
                "auction_state": None,
                "notes": [],
            }
            lots.append(active)
            continue
        if not active:
            continue
        if event["event_type"] == "bid_update":
            active["last_bid"] = payload.get("price_value")
            if active["last_bid"] is None:
                raw = payload.get("price")
                try:
                    active["last_bid"] = float(str(raw).replace("$", "").replace(",", "").strip()) if raw else None
                except Exception:
                    active["last_bid"] = None
            active["last_bid_at"] = event["created_at"]
        elif event["event_type"] == "auction_state":
            active["auction_state"] = payload.get("state")
        elif event["event_type"] == "auction_winner":
            active["winner"] = payload.get("winner") or payload.get("winner_username") or None
            active["winner_at"] = event["created_at"]
            active["final_price"] = _parse_price_value(payload)
            active["price_source"] = _infer_price_source(payload)

    rows = []
    anomaly_counts = {
        "winner_without_price": 0,
        "price_without_winner": 0,
        "lot_without_close": 0,
    }
    for lot in reversed(lots[-limit:]):
        notes = []
        if lot["winner"] and not lot["final_price"]:
            anomaly_counts["winner_without_price"] += 1
            notes.append("Winner detected but final price missing")
        if lot["last_bid"] and not lot["winner"]:
            anomaly_counts["price_without_winner"] += 1
            notes.append("Bid seen but winner not detected yet")
        if not lot["winner"] and lot["auction_state"] == "awaiting_next_item":
            anomaly_counts["lot_without_close"] += 1
            notes.append("Lot rolled forward without winner capture")
        rows.append({
            **lot,
            "notes": notes,
            "final_price": round(float(lot["final_price"] or 0), 2) if lot["final_price"] is not None else None,
            "last_bid": round(float(lot["last_bid"] or 0), 2) if lot["last_bid"] is not None else None,
        })

    return {
        "stream": dict(stream_row) if stream_row else None,
        "rows": rows,
        "summary": {
            "total_lots": len(rows),
            "winner_without_price": anomaly_counts["winner_without_price"],
            "price_without_winner": anomaly_counts["price_without_winner"],
            "lot_without_close": anomaly_counts["lot_without_close"],
        },
    }

def _clean_product_name(name):
    """Strip internal SKU prefix like '[SKU-CODE] ' from display names."""
    if not name:
        return name
    name = name.strip()
    if name.startswith("["):
        end = name.find("]")
        if end != -1:
            return name[end + 1:].strip()
    return name


def _tracking_url(carrier, tracking_number):
    tracking = (tracking_number or "").strip()
    if not tracking:
        return None
    carrier_key = (carrier or "usps").strip().lower()
    if carrier_key == "usps":
        return f"https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking}"
    return None


def _cancel_missing_picklist_orders(effective_sid, shipments):
    if not effective_sid:
        return 0
    pdf_usernames = {(s.get("username") or "").strip().lower() for s in shipments if s.get("username")}
    pdf_lots = {
        str(item.get("lot_number") or "").strip()
        for ship in shipments
        for item in (ship.get("items") or [])
        if str(item.get("lot_number") or "").strip()
    }
    orders_cancelled = 0
    all_session_orders = list_sale_orders(session_id=effective_sid)
    for so in all_session_orders:
        if so.get("state") == "cancel":
            continue
        order_lines = list_sale_order_lines(int(so["id"])) or []
        order_lots = {
            str(line.get("lot_number") or "").strip()
            for line in order_lines
            if str(line.get("lot_number") or "").strip()
        }
        buyer = (so.get("whatnot_buyer_username") or "").strip().lower()
        should_cancel = False
        if order_lots:
            should_cancel = order_lots.isdisjoint(pdf_lots)
        elif buyer:
            should_cancel = buyer not in pdf_usernames
        if should_cancel:
            update_sale_order(int(so["id"]), state="cancel", fulfillment_status="pending", payment_status="unpaid")
            reverse_sale_order_inventory(int(so["id"]))
            orders_cancelled += 1
    return orders_cancelled


def _normalize_product_match(value):
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    stop = {
        "eau", "de", "parfum", "spray", "ml", "oz", "ounce", "ounces",
        "men", "mens", "women", "womens", "unisex", "perfume", "fragrance",
        "long", "lasting", "default",
    }
    parts = [part for part in text.split() if part and part not in stop]
    return " ".join(parts)


def _match_inventory_product(products, product_name):
    target = _normalize_product_match(product_name)
    if not target:
        return None, 0
    best = None
    best_score = 0
    target_tokens = set(target.split())
    for product in products:
        candidate = _normalize_product_match(product.get("name"))
        if not candidate:
            continue
        score = 0
        if candidate == target:
            score = 100
        elif candidate in target or target in candidate:
            score = 90
        else:
            candidate_tokens = set(candidate.split())
            overlap = len(target_tokens & candidate_tokens)
            if overlap:
                score = int((overlap / max(1, len(target_tokens))) * 80)
        if score > best_score:
            best = product
            best_score = score
    return best, best_score


def _match_inventory_product_by_code(products, barcode=None, sku=None):
    barcode_value = str(barcode or "").strip()
    sku_value = str(sku or "").strip().lower()
    if not barcode_value and not sku_value:
        return None
    for product in products:
        product_barcode = str(product.get("barcode") or "").strip()
        product_sku = str(product.get("default_code") or product.get("sku") or "").strip().lower()
        if barcode_value and product_barcode and product_barcode == barcode_value:
            return product
        if sku_value and product_sku and product_sku == sku_value:
            return product
    return None


def _normalize_lot_number(value):
    return str(value or "").strip().lower()


def _extract_lot_number(row):
    for key in ("Lot", "Lot No", "Lot Number", "lot", "lot_no", "lot_number", "Lot #"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _extract_sheet_barcode(row):
    for key in ("Barcode", "barcode", "UPC", "upc", "Code", "code", "Seller SKU", "seller_sku", "SKU", "sku"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _extract_sheet_product_name(row):
    for key in ("Product Name", "product_name", "Name", "name", "Product", "product"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _looks_like_barcode(value):
    raw = re.sub(r"[^0-9/ ]+", "", str(value or "").strip())
    if not raw:
        return False
    parts = [part.strip() for part in raw.split("/") if part.strip()]
    if not parts:
        return False
    return all(re.fullmatch(r"\d{7,14}", part) for part in parts)


def _google_sheet_csv_url(candidate):
    raw = str(candidate or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if "docs.google.com" not in (parsed.netloc or "").lower():
        return raw
    if "/export" in (parsed.path or "") and "format=csv" in (parsed.query or "").lower():
        return raw
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", parsed.path or "")
    if not match:
        return raw
    spreadsheet_id = match.group(1)
    qs = parse_qs(parsed.query or "")
    gid = (qs.get("gid") or [""])[0]
    export = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv"
    if gid:
        export = f"{export}&gid={gid}"
    return export


def _download_sheet_csv_text(url):
    candidate = _google_sheet_csv_url(url)
    if not candidate:
        raise ValueError("sheet_url required")
    request = Request(
        candidate,
        headers={
            "User-Agent": "YNFDealsGoogleSheetImport/1.0",
            "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.5",
        },
    )
    with urlopen(request, timeout=15) as response:
        payload = response.read(4 * 1024 * 1024 + 1)
        if not payload or len(payload) > 4 * 1024 * 1024:
            raise ValueError("sheet_download_failed")
        charset = response.headers.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if "<!DOCTYPE html" in text or "Sign in to your Google Account" in text or "Allow Google Sheets access" in text:
            raise ValueError("google_sheet_not_public_csv")
        return text


def _parse_tiktok_sheet_rows(csv_text):
    text = str(csv_text or "").strip()
    rows = []
    if not text:
        return rows
    raw_reader = list(csv.reader(io.StringIO(text)))
    if not raw_reader:
        return rows
    normalized_header = [str(cell or "").strip().lower() for cell in (raw_reader[0] or [])]
    known_header_tokens = {
        "lot", "lot no", "lot number", "lot #",
        "barcode", "upc", "code", "seller sku", "sku",
        "product", "product name", "name",
    }
    has_header = any(cell in known_header_tokens for cell in normalized_header if cell)
    data_rows = raw_reader[1:] if has_header else raw_reader
    if has_header:
        reader = csv.DictReader(io.StringIO(text))
        sequential_lot = 1
        for source_row in reader:
            lot_number = _extract_lot_number(source_row)
            barcode = _normalize_tiktok_barcode(_extract_sheet_barcode(source_row))
            product_name = _extract_sheet_product_name(source_row)
            if not lot_number and not barcode and not product_name:
                continue
            if not lot_number:
                lot_number = str(sequential_lot)
                sequential_lot += 1
            rows.append({
                "lot_number": str(lot_number).strip(),
                "barcode": barcode,
                "product_name": product_name,
            })
        return rows
    sequential_lot = 1
    for source_row in data_rows:
        values = [str(cell or "").strip() for cell in source_row]
        non_empty = [value for value in values if value]
        if not non_empty:
            continue
        lot_number = ""
        barcode = ""
        product_name = ""
        if len(non_empty) == 1 and _looks_like_barcode(non_empty[0]):
            barcode = _normalize_tiktok_barcode(non_empty[0])
        elif len(non_empty) >= 2 and non_empty[0].isdigit() and _looks_like_barcode(non_empty[1]):
            lot_number = non_empty[0]
            barcode = _normalize_tiktok_barcode(non_empty[1])
            if len(non_empty) >= 3:
                product_name = non_empty[2]
        else:
            barcode_candidate = next((value for value in non_empty if _looks_like_barcode(value)), "")
            if barcode_candidate:
                barcode = _normalize_tiktok_barcode(barcode_candidate)
            trailing = [value for value in non_empty if value != barcode_candidate]
            if trailing:
                product_name = trailing[-1]
        if not lot_number:
            lot_number = str(sequential_lot)
        sequential_lot += 1
        if not barcode and not product_name:
            continue
        rows.append({
            "lot_number": lot_number,
            "barcode": barcode,
            "product_name": product_name,
        })
    return rows


def _normalize_tiktok_sheet_rows(rows):
    normalized = []
    for row in rows or []:
        normalized.append((
            str(row.get("lot_number") or "").strip(),
            _normalize_tiktok_barcode(row.get("barcode") or ""),
            str(row.get("product_name") or "").strip(),
        ))
    return normalized


def _tiktok_live_sale_fee(sale_price):
    return round(float(sale_price or 0) * 0.06, 2)


def _tiktok_live_status_label(status_family):
    family = str(status_family or "").strip().lower()
    if family == "cancelled":
        return "Cancelled"
    if family == "confirmed":
        return "To ship"
    if family == "pending":
        return "Pending"
    return "Unlinked"


def _tiktok_live_iso_datetime(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.isdigit():
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc).isoformat()
        except Exception:
            return raw
    return raw


def _tiktok_live_pending_until(value):
    raw = str(value or "").strip()
    if not raw or not raw.isdigit():
        return ""
    try:
        return datetime.fromtimestamp(int(raw) + 3600, tz=timezone.utc).isoformat()
    except Exception:
        return ""


def _tiktok_live_buyer_fallback(match):
    match = match or {}
    raw_order = match.get("raw_order") if isinstance(match.get("raw_order"), dict) else {}
    buyer_email = str(match.get("buyer_email") or raw_order.get("buyer_email") or "").strip()
    if buyer_email and "@" in buyer_email:
        local = buyer_email.split("@", 1)[0].strip()
        if local:
            return f"TikTok buyer {local}"
    buyer_user_id = str(match.get("buyer_user_id") or raw_order.get("user_id") or "").strip()
    if buyer_user_id:
        return f"TikTok user {buyer_user_id}"
    order_id = str(match.get("order_id") or match.get("external_order_id") or "").strip()
    if order_id:
        return f"Order {order_id}"
    return "Pending TikTok buyer"


def _tiktok_match_address(match):
    parts = [
        match.get("full_address"),
        match.get("address_line_1"),
        match.get("address_line_2"),
        match.get("address_line_3"),
        match.get("address_line_4"),
        match.get("city"),
        match.get("state"),
        match.get("zipcode"),
        match.get("country"),
    ]
    seen = set()
    clean = []
    for part in parts:
        value = str(part or "").strip()
        key = value.lower()
        if value and key not in seen:
            clean.append(value)
            seen.add(key)
    return ", ".join(clean)


def _tiktok_live_pending_reservation_nets(item_ids):
    clean_ids = sorted({int(value) for value in item_ids or [] if value})
    if not clean_ids:
        return {}
    nets = {}
    rows = get_inventory_movement_reference_totals(
        [_TIKTOK_LIVE_PENDING_RESERVE_REF, _TIKTOK_LIVE_PENDING_RELEASE_REF],
        clean_ids,
    )
    for row in rows:
        ref_id = int(row.get("reference_id") or 0)
        nets[ref_id] = float(nets.get(ref_id, 0)) + float(row.get("net_qty") or 0)
    return nets


def _release_tiktok_live_pending_reservations(items, *, reason="TikTok LIVE pending reserve released"):
    clean_item_ids = sorted({int(item.get("id")) for item in (items or []) if item and item.get("id")})
    if not clean_item_ids:
        return []
    release_map = {}
    rows = get_inventory_movement_reference_totals(
        [_TIKTOK_LIVE_PENDING_RESERVE_REF, _TIKTOK_LIVE_PENDING_RELEASE_REF],
        clean_item_ids,
    )
    for row in rows:
        item_id = int(row.get("reference_id") or 0)
        product_id = int(row.get("product_id") or 0)
        net_qty = float(row.get("net_qty") or 0)
        if net_qty < 0:
            release_map.setdefault(item_id, []).append((product_id, abs(net_qty)))
    released = []
    for item_id, product_rows in release_map.items():
        for product_id, qty in product_rows:
            record_inventory_movement(
                int(product_id),
                "in",
                qty,
                reason=reason,
                reference_type=_TIKTOK_LIVE_PENDING_RELEASE_REF,
                reference_id=item_id,
            )
        released.append(item_id)
    return released


def _sync_tiktok_go_live_sheet_rows(session, parsed_rows, *, sheet_url=""):
    if not session:
        return {"updated": False, "imported_rows": 0, "matched_rows": 0, "unmatched_rows": 0, "lots_touched": 0}
    grouped_rows = {}
    for parsed_row in parsed_rows:
        lot_no = str(parsed_row.get("lot_number") or "").strip()
        if not lot_no:
            continue
        grouped_rows.setdefault(lot_no, []).append(parsed_row)
    touched_lots = {}
    matched_rows = 0
    unmatched_rows = 0
    imported_rows = 0
    for lot_no, lot_rows in grouped_rows.items():
        lot = touched_lots.get(lot_no)
        if not lot:
            lot = create_company_lot(int(session["id"]), lot_no, status="open")
            touched_lots[lot_no] = lot
        desired_items = []
        for parsed_row in lot_rows:
            product = find_product_by_code(parsed_row.get("barcode")) if parsed_row.get("barcode") else None
            desired_items.append({
                "product_id": product.get("id") if product else None,
                "barcode": parsed_row.get("barcode") or "",
                "sku": (product.get("default_code") or product.get("sku") or "") if product else "",
                "product_name": (product.get("name") or parsed_row.get("product_name") or "") if product or parsed_row.get("product_name") else "",
                "unit_cost": float(product.get("cost_price") or 0) if product else 0,
                "qty_snapshot": 1,
                "status": "open",
                "_matched": bool(product),
            })
        existing_items = list_lot_items(int(lot["id"]))
        existing_signature = [
            (
                item.get("product_id"),
                str(item.get("barcode") or "").strip(),
                str(item.get("sku") or "").strip(),
                str(item.get("product_name") or "").strip(),
                round(float(item.get("unit_cost") or 0), 4),
                int(item.get("qty_snapshot") or 1),
                str(item.get("status") or "open").strip() or "open",
            )
            for item in existing_items
        ]
        desired_signature = [
            (
                item.get("product_id"),
                str(item.get("barcode") or "").strip(),
                str(item.get("sku") or "").strip(),
                str(item.get("product_name") or "").strip(),
                round(float(item.get("unit_cost") or 0), 4),
                int(item.get("qty_snapshot") or 1),
                str(item.get("status") or "open").strip() or "open",
            )
            for item in desired_items
        ]
        if existing_signature != desired_signature:
            _release_tiktok_live_pending_reservations(
                existing_items,
                reason=f"TikTok LIVE sheet sync replaced lot {lot_no}",
            )
            first_item = desired_items[0] if desired_items else None
            if first_item:
                replace_lot_items_for_scan(
                    lot["id"],
                    product_id=first_item.get("product_id"),
                    barcode=first_item.get("barcode"),
                    sku=first_item.get("sku"),
                    product_name=first_item.get("product_name"),
                    unit_cost=first_item.get("unit_cost"),
                    qty_snapshot=first_item.get("qty_snapshot"),
                    status=first_item.get("status"),
                )
                for extra_item in desired_items[1:]:
                    add_lot_item(
                        lot["id"],
                        product_id=extra_item.get("product_id"),
                        barcode=extra_item.get("barcode"),
                        sku=extra_item.get("sku"),
                        product_name=extra_item.get("product_name"),
                        unit_cost=extra_item.get("unit_cost"),
                        qty_snapshot=extra_item.get("qty_snapshot"),
                        status=extra_item.get("status"),
                    )
            else:
                replace_lot_items_for_scan(lot["id"])
            update_company_lot(lot["id"], status="open")
        imported_rows += len(desired_items)
        matched_rows += sum(1 for item in desired_items if item.get("_matched"))
        unmatched_rows += sum(1 for item in desired_items if not item.get("_matched"))
    _append_tiktok_go_live_journal(
        session,
        "sheet_sync_applied",
        extra={
            "imported_rows": imported_rows,
            "matched_rows": matched_rows,
            "unmatched_rows": unmatched_rows,
            "sheet_url": sheet_url,
        },
    )
    _write_tiktok_go_live_snapshot(session)
    return {
        "updated": True,
        "imported_rows": imported_rows,
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows,
        "lots_touched": len(touched_lots),
    }


def _auto_sync_tiktok_go_live_sheet_session(session, force=False):
    if not session or int(session.get("id") or 0) <= 0:
        return {"updated": False}
    session_status = str((session.get("status") or "")).strip().lower()
    if session_status not in {"live", "open", "draft"}:
        return {"updated": False, "reason": "session_not_live"}
    cfg = _get_tiktok_go_live_sheet_sync(session.get("id"))
    if not cfg or not cfg.get("enabled") or not str(cfg.get("sheet_url") or "").strip():
        return {"updated": False}
    now = time.time()
    session_id = int(session["id"])
    with _TIKTOK_GO_LIVE_SYNC_LOCK:
        state = dict(_TIKTOK_GO_LIVE_SYNC_STATE.get(session_id) or {})
    last_run = float(state.get("last_run") or 0)
    if not force and now - last_run < 4.0:
        return {"updated": False, "throttled": True, **state}
    csv_text = _download_sheet_csv_text(cfg.get("sheet_url"))
    parsed_rows = _parse_tiktok_sheet_rows(csv_text)
    signature = _normalize_tiktok_sheet_rows(parsed_rows)
    if signature == tuple(state.get("signature") or ()):
        new_state = {
            **state,
            "last_run": now,
            "row_count": len(parsed_rows),
        }
        with _TIKTOK_GO_LIVE_SYNC_LOCK:
            _TIKTOK_GO_LIVE_SYNC_STATE[session_id] = new_state
        return {"updated": False, "row_count": len(parsed_rows), **new_state}
    result = _sync_tiktok_go_live_sheet_rows(session, parsed_rows, sheet_url=str(cfg.get("sheet_url") or ""))
    new_state = {
        "last_run": now,
        "signature": list(signature),
        "row_count": len(parsed_rows),
        "last_synced_at": datetime.now(timezone.utc).isoformat(),
    }
    with _TIKTOK_GO_LIVE_SYNC_LOCK:
        _TIKTOK_GO_LIVE_SYNC_STATE[session_id] = new_state
    return {**result, **new_state}


def _sync_tiktok_go_live_pending_inventory(session, rows):
    session_id = int((session or {}).get("id") or 0)
    if session_id <= 0:
        return rows
    item_ids = []
    for row in rows or []:
        for item in row.get("items") or []:
            if item.get("itemId"):
                item_ids.append(item.get("itemId"))
        if row.get("itemId"):
            item_ids.append(row.get("itemId"))
    reservation_nets = _tiktok_live_pending_reservation_nets(item_ids)
    for row in rows or []:
        reserved_any = False
        for item in row.get("items") or []:
            item_id = int(item.get("itemId") or 0)
            product_id = item.get("productId")
            if item_id <= 0 or not product_id:
                continue
            net_qty = float(reservation_nets.get(item_id) or 0)
            if net_qty < 0:
                record_inventory_movement(
                    int(product_id),
                    "in",
                    abs(net_qty),
                    reason=f"TikTok LIVE pending reserve removed: session {session_id} lot {row.get('lotNo') or '—'}",
                    reference_type=_TIKTOK_LIVE_PENDING_RELEASE_REF,
                    reference_id=item_id,
                )
                net_qty = 0
                reservation_nets[item_id] = 0
            item["inventoryReserved"] = False
            reserved_any = reserved_any or False
        row["inventoryReserved"] = reserved_any
    return rows


def _attach_tiktok_go_live_inventory_snapshot(rows):
    rows = list(rows or [])
    product_ids = sorted({int(row.get("productId")) for row in rows if row.get("productId")})
    product_map = {}
    for product_id in product_ids:
        try:
            product_map[product_id] = get_product(product_id) or {}
        except Exception:
            product_map[product_id] = {}
    for row in rows:
        product = product_map.get(int(row.get("productId") or 0)) if row.get("productId") else {}
        if product:
            row["onHandQty"] = float(product.get("on_hand_qty") or 0)
            row["retail"] = float(product.get("retail_price") or 0)
        elif row.get("onHandQty") is None:
            row["onHandQty"] = None
    return rows


def _tiktok_live_order_epoch(value):
    raw = str(value or "").strip()
    if not raw:
        return 0
    if raw.isdigit():
        try:
            return int(raw)
        except Exception:
            return 0
    try:
        normalized = raw.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp())
    except Exception:
        return 0


def _tiktok_live_match_start_epoch(session, lookback_seconds=0):
    start_epoch = _tiktok_live_order_epoch((session or {}).get("started_at"))
    if not start_epoch:
        return 0
    try:
        lookback = max(0, int(lookback_seconds or 0))
    except Exception:
        lookback = 0
    return max(0, start_epoch - lookback)


def _normalize_tiktok_live_listing_title(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _is_tiktok_live_generic_listing(line):
    seller_sku = str((line or {}).get("seller_sku") or "").strip()
    if not seller_sku.isdigit():
        return False
    title = str((line or {}).get("product_name") or "").strip()
    normalized = _normalize_tiktok_live_listing_title(title)
    if not normalized:
        return True
    generic_tokens = (
        "bangerperfume",
        "bangerperfumes",
        "batch",
        "nocancellations",
        "generic",
        "liveauction",
        "auction",
    )
    if any(token in normalized for token in generic_tokens):
        return True
    # Proper product listings usually carry brand/product identifiers instead of
    # the simple generic live-auction title.
    proper_title_tokens = (
        "lattafa",
        "armaf",
        "afnan",
        "maison",
        "zimaya",
        "alhambra",
        "rasasi",
        "dumont",
        "ahmed",
        "jeanlowe",
        "eau",
        "spray",
        "parfum",
        "perfumeoil",
    )
    return not any(token in normalized for token in proper_title_tokens)


def _tiktok_live_batch_number_from_title(title):
    normalized_title = str(title or "").strip().lower()
    normalized = _normalize_tiktok_live_listing_title(title)
    match = re.search(r"\b\d{6}b(\d+)\b", normalized_title)
    if match:
        return max(1, int(match.group(1)))
    match = re.search(r"(?:^|[^a-z0-9])b\s*(\d+)(?:$|[^a-z0-9])", normalized_title)
    if match:
        return max(1, int(match.group(1)))
    match = re.search(r"\bbatch\s*(\d+)\b", normalized_title)
    if match:
        return max(1, int(match.group(1)))
    match = re.search(r"batch(\d+)", normalized)
    if match:
        return max(1, int(match.group(1)))
    return None


def _tiktok_live_lot_number_from_seller_sku(seller_sku):
    raw = str(seller_sku or "").strip()
    if not raw:
        return ""
    if raw.isdigit():
        return str(int(raw))
    match = re.search(r"(\d+)\s*$", raw)
    if match:
        return str(int(match.group(1)))
    return ""


def _tiktok_live_generic_batch_map(lines):
    generic_titles = []
    for line in lines or []:
        if not _is_tiktok_live_generic_listing(line):
            continue
        title_key = _normalize_tiktok_live_listing_title(line.get("product_name")) or "__generic_live__"
        if title_key in {item[0] for item in generic_titles}:
            continue
        explicit_batch = _tiktok_live_batch_number_from_title(line.get("product_name"))
        created_epoch = _tiktok_live_order_epoch(line.get("created_at") or line.get("paid_at") or line.get("updated_at"))
        raw_lot = _tiktok_live_lot_number_from_seller_sku(line.get("seller_sku"))
        if not raw_lot:
            continue
        generic_titles.append((title_key, explicit_batch, created_epoch, str(line.get("product_name") or "")))
    generic_titles.sort(key=lambda item: (item[2] or 0, item[1] or 9999, item[3]))
    batch_by_title = {}
    next_batch = 1
    for title_key, explicit_batch, _created_epoch, _title in generic_titles:
        if explicit_batch:
            batch_by_title[title_key] = explicit_batch
            next_batch = max(next_batch, explicit_batch + 1)
            continue
        while next_batch in set(batch_by_title.values()):
            next_batch += 1
        batch_by_title[title_key] = next_batch
        next_batch += 1
    return batch_by_title


def _tiktok_live_batch_override_for_session(session):
    text = " ".join([
        str((session or {}).get("name") or ""),
        str((session or {}).get("title") or ""),
        str((session or {}).get("show_id") or ""),
        str((session or {}).get("created_at") or ""),
        str((session or {}).get("started_at") or ""),
    ]).lower()
    sequence = str((session or {}).get("sequence") or "").strip()
    is_session_20 = sequence == "20" or "go live session - 20" in text or "go live session #20" in text
    is_today_session = "20260516" in text or "2026-05-16" in text or "may 16" in text
    if is_session_20 and is_today_session:
        return {3: 2, 2: 3}
    return {}


def _tiktok_live_apply_batch_override(batch_number, batch_overrides=None):
    try:
        batch = max(1, int(batch_number or 1))
    except Exception:
        batch = 1
    if not batch_overrides:
        return batch
    try:
        return max(1, int(batch_overrides.get(batch) or batch))
    except Exception:
        return batch


def _tiktok_live_final_lot_number_for_line(line, batch_by_title, batch_overrides=None):
    if not _is_tiktok_live_generic_listing(line):
        return ""
    raw_lot = _tiktok_live_lot_number_from_seller_sku((line or {}).get("seller_sku"))
    if not raw_lot:
        return ""
    title_key = _normalize_tiktok_live_listing_title((line or {}).get("product_name")) or "__generic_live__"
    batch_number = int((batch_by_title or {}).get(title_key) or 1)
    effective_batch_number = _tiktok_live_apply_batch_override(batch_number, batch_overrides)
    return str(((effective_batch_number - 1) * 300) + int(raw_lot))


def _tiktok_live_expected_batch_for_lot(lot_no):
    try:
        numeric = int(str(lot_no or "").strip())
    except Exception:
        return 1
    if numeric <= 0:
        return 1
    return ((numeric - 1) // 300) + 1


def _tiktok_live_batch_range_label(batch_number):
    try:
        batch = max(1, int(batch_number or 1))
    except Exception:
        batch = 1
    start = ((batch - 1) * 300) + 1
    end = batch * 300
    return f"{start}-{end}"


def _tiktok_live_batch_guard_from_lines(lines, max_lot_no, session_started_epoch=0, batch_overrides=None):
    expected_batch = _tiktok_live_expected_batch_for_lot(max_lot_no)
    if expected_batch <= 1 or not lines:
        return {
            "expectedBatch": expected_batch,
            "expectedRange": _tiktok_live_batch_range_label(expected_batch),
            "detectedBatch": None,
            "detectedTitle": "",
            "blocking": False,
            "status": "waiting",
            "message": "",
        }

    generic_lines = []
    for line in lines or []:
        created_epoch = _tiktok_live_order_epoch(line.get("created_at") or line.get("paid_at") or line.get("updated_at"))
        if session_started_epoch and created_epoch and created_epoch < session_started_epoch:
            continue
        if not _is_tiktok_live_generic_listing(line):
            continue
        raw_lot = _tiktok_live_lot_number_from_seller_sku(line.get("seller_sku"))
        if not raw_lot:
            continue
        generic_lines.append({**line, "_created_epoch": created_epoch})

    batch_by_title = _tiktok_live_generic_batch_map(generic_lines)
    detected = []
    for line in generic_lines:
        title = str(line.get("product_name") or "").strip()
        title_key = _normalize_tiktok_live_listing_title(title) or "__generic_live__"
        batch_number = int((batch_by_title or {}).get(title_key) or 1)
        detected.append({
            "batch": batch_number,
            "title": title,
            "created_epoch": int(line.get("_created_epoch") or 0),
        })

    if not detected:
        return {
            "expectedBatch": expected_batch,
            "expectedRange": _tiktok_live_batch_range_label(expected_batch),
            "detectedBatch": None,
            "detectedTitle": "",
            "blocking": False,
            "status": "waiting",
            "message": "",
        }

    latest = sorted(detected, key=lambda item: (item.get("created_epoch") or 0, item.get("batch") or 0))[-1]
    detected_batch = int(latest.get("batch") or 1)
    effective_batch = _tiktok_live_apply_batch_override(detected_batch, batch_overrides)
    override_active = effective_batch != detected_batch
    blocking = effective_batch > expected_batch
    expected_range = _tiktok_live_batch_range_label(expected_batch)
    detected_range = _tiktok_live_batch_range_label(detected_batch)
    effective_range = _tiktok_live_batch_range_label(effective_batch)
    message = ""
    status = "matched" if effective_batch == expected_batch else "waiting"
    if override_active and effective_batch == expected_batch:
        status = "overridden"
        message = (
            f"Today only batch override active: TikTok B{detected_batch} is mapped to "
            f"operational B{effective_batch} lots {effective_range}."
        )
    if blocking:
        status = "blocked"
        message = (
            f"Wrong TikTok listing selected: expected B{expected_batch} for lots {expected_range}, "
            f"but TikTok is sending B{detected_batch} for lots {detected_range}."
        )

    return {
        "expectedBatch": expected_batch,
        "expectedRange": expected_range,
        "detectedBatch": detected_batch,
        "detectedRange": detected_range,
        "effectiveBatch": effective_batch,
        "effectiveRange": effective_range,
        "detectedTitle": latest.get("title") or "",
        "blocking": blocking,
        "overrideActive": override_active,
        "status": status,
        "message": message,
    }


def _build_tiktok_go_live_pending_matches(lines, session_started_epoch=0, batch_overrides=None):
    generic_lines = []
    for line in lines or []:
        created_epoch = _tiktok_live_order_epoch(line.get("created_at") or line.get("paid_at") or line.get("updated_at"))
        if session_started_epoch and created_epoch and created_epoch < session_started_epoch:
            continue
        if not _is_tiktok_live_generic_listing(line):
            continue
        raw_lot = _tiktok_live_lot_number_from_seller_sku(line.get("seller_sku"))
        if not raw_lot:
            continue
        generic_lines.append({**line, "_created_epoch": created_epoch, "_raw_lot": int(raw_lot)})

    batch_by_title = _tiktok_live_generic_batch_map(generic_lines)
    matches = {}
    for line in generic_lines:
        final_lot = _tiktok_live_final_lot_number_for_line(line, batch_by_title, batch_overrides=batch_overrides)
        if not final_lot:
            continue
        lot_key = str(final_lot)
        title_key = _normalize_tiktok_live_listing_title(line.get("product_name")) or "__generic_live__"
        detected_batch = int(batch_by_title[title_key])
        effective_batch = _tiktok_live_apply_batch_override(detected_batch, batch_overrides)
        current = matches.get(lot_key)
        if current is None:
            matches[lot_key] = {**line, "live_lot_number": lot_key, "live_batch_number": detected_batch, "live_effective_batch_number": effective_batch}
            continue
        current_rank = 2 if current.get("status_family") == "confirmed" else 1 if current.get("status_family") == "pending" else 0
        next_rank = 2 if line.get("status_family") == "confirmed" else 1 if line.get("status_family") == "pending" else 0
        current_ts = str(current.get("updated_at") or current.get("created_at") or "")
        next_ts = str(line.get("updated_at") or line.get("created_at") or "")
        if next_rank > current_rank or (next_rank == current_rank and next_ts >= current_ts):
            matches[lot_key] = {**line, "live_lot_number": lot_key, "live_batch_number": detected_batch, "live_effective_batch_number": effective_batch}
    return matches


def _enrich_tiktok_go_live_rows_with_pending_orders(session, rows):
    rows = list(rows or [])
    if not rows:
        return rows
    session_started_epoch = _tiktok_live_order_epoch((session or {}).get("started_at"))
    session_status = str((session or {}).get("status") or "").strip().lower()
    match_start_epoch = _tiktok_live_match_start_epoch(
        session,
        _TIKTOK_GO_LIVE_LIVE_ORDER_LOOKBACK_SECONDS if session_status == "live" else 0,
    )
    max_lot_no = 0
    for row in rows:
        lot_no = str(row.get("lotNo") or "").strip()
        if lot_no.isdigit():
            max_lot_no = max(max_lot_no, int(lot_no))
    # TikTok returns newest order search results first. During a live show the
    # operator needs the newest buyer rows quickly, so keep the hot poll small
    # and frequent. Ended/session review views can still fetch deeper history.
    if session_status == "live":
        expected_batch = _tiktok_live_expected_batch_for_lot(max_lot_no)
        max_pages = max(4, min(8, expected_batch + 3))
        cache_ttl_seconds = 1
    else:
        max_pages = max(6, min(20, (max_lot_no // 100) + 4))
        cache_ttl_seconds = 10
    payload = {"page_size": 100, "max_pages": max_pages}
    if match_start_epoch:
        payload["create_time_ge"] = match_start_epoch
    batch_overrides = _tiktok_live_batch_override_for_session(session)
    try:
        pending_result = get_recent_tiktok_order_line_matches(payload, ttl_seconds=cache_ttl_seconds)
        pending_lines = pending_result.get("lines") or []
        matches = _build_tiktok_go_live_pending_matches(pending_lines, session_started_epoch=match_start_epoch, batch_overrides=batch_overrides)
        batch_guard = _tiktok_live_batch_guard_from_lines(pending_lines, max_lot_no, session_started_epoch=match_start_epoch, batch_overrides=batch_overrides)
    except Exception:
        return rows
    enriched = []
    for row in rows:
        lot_no = str(row.get("lotNo") or "").strip()
        match = matches.get(lot_no) if lot_no else None
        next_row = dict(row)
        if batch_guard:
            next_row["tiktokBatchGuard"] = batch_guard
        if match:
            row_expected_batch = _tiktok_live_expected_batch_for_lot(lot_no)
            match_batch = int(match.get("live_effective_batch_number") or match.get("live_batch_number") or row_expected_batch or 1)
            if match_batch != row_expected_batch:
                match = None
        if match:
            recipient_name = str(match.get("recipient_name") or "").strip()
            buyer_username = (
                match.get("buyer_username")
                or match.get("buyer_name")
                or match.get("buyer_user_id")
                or ""
            )
            buyer_name = (
                match.get("buyer_name")
                or recipient_name
                or match.get("buyer_username")
                or ""
            )
            buyer_display = buyer_username or buyer_name or recipient_name or _tiktok_live_buyer_fallback(match)
            sale_price = float(match.get("total_price") or match.get("sale_price") or match.get("unit_price") or 0)
            cost = float(next_row.get("cost") or 0)
            fees = _tiktok_live_sale_fee(sale_price)
            status_family = str(match.get("status_family") or "").strip().lower()
            if status_family == "cancelled":
                sale_price = 0.0
                fees = 0.0
                profit = 0.0
            else:
                profit = round(sale_price - fees - cost, 2)
            next_row["tiktokOrder"] = {
                "orderId": match.get("order_id") or match.get("external_order_id"),
                "buyerUsername": buyer_username,
                "buyerName": buyer_name,
                "recipientName": recipient_name,
                "buyerDisplay": buyer_display,
                "buyerEmail": match.get("buyer_email") or match.get("email") or "",
                "phone": match.get("phone") or match.get("phone_number") or "",
                "address": _tiktok_match_address(match),
                "addressLine1": match.get("address_line_1") or "",
                "addressLine2": match.get("address_line_2") or "",
                "city": match.get("city") or "",
                "state": match.get("state") or "",
                "zipcode": match.get("zipcode") or "",
                "country": match.get("country") or "",
                "status": match.get("order_status") or match.get("status"),
                "statusFamily": status_family,
                "salePrice": sale_price,
                "sellerSku": match.get("seller_sku"),
                "liveLotNumber": match.get("live_lot_number") or lot_no,
                "liveBatchNumber": match.get("live_batch_number"),
                "liveEffectiveBatchNumber": match.get("live_effective_batch_number") or match.get("live_batch_number"),
                "listingTitle": match.get("product_name") or "",
                "createdAt": _tiktok_live_iso_datetime(match.get("created_at")),
                "pendingUntil": _tiktok_live_pending_until(match.get("created_at")),
                "quantity": match.get("quantity"),
                "buyerUserId": match.get("buyer_user_id") or ((match.get("raw_order") or {}).get("user_id") if isinstance(match.get("raw_order"), dict) else ""),
            }
            next_row["buyer_username"] = buyer_username
            next_row["buyer"] = buyer_display
            next_row["orderedAt"] = _tiktok_live_iso_datetime(match.get("created_at"))
            next_row["salesPrice"] = sale_price
            next_row["fees"] = fees
            next_row["profit"] = profit
            next_row["statusLabel"] = _tiktok_live_status_label(status_family)
            next_row["statusFamily"] = status_family
        else:
            review_later = _is_tiktok_go_live_review_later_row(next_row)
            next_row["buyer"] = ""
            next_row["orderedAt"] = ""
            next_row["salesPrice"] = 0
            next_row["fees"] = 0
            next_row["profit"] = 0
            row_expected_batch = _tiktok_live_expected_batch_for_lot(lot_no)
            batch_blocked = bool((batch_guard or {}).get("blocking")) and row_expected_batch == int((batch_guard or {}).get("expectedBatch") or 0)
            next_row["statusLabel"] = "Batch mismatch" if batch_blocked else "Review later" if review_later else "Waiting"
            next_row["statusFamily"] = "batch_mismatch" if batch_blocked else "review_later" if review_later else "unlinked"
        enriched.append(next_row)
    return enriched


def _extract_tiktok_live_lot_number_from_order(order):
    external_ref = str(order.get("external_order_ref") or "").strip()
    ref_parts = external_ref.split(":")
    if len(ref_parts) >= 3 and ref_parts[0].lower() == "tiktok_live":
        if len(ref_parts) >= 4 and re.fullmatch(r"\d{15,22}", ref_parts[-1] or "") and re.fullmatch(r"\d+", ref_parts[-2] or ""):
            return ref_parts[-2]
        if re.fullmatch(r"\d+", ref_parts[-1] or ""):
            return ref_parts[-1]
    match = re.search(r"tiktok_live:[^:]+:(\d+)$", external_ref, re.I)
    if match:
        return match.group(1)
    linked = str(order.get("linked_lot_numbers") or "").strip()
    if linked:
        first = str(linked.split(",")[0] or "").strip()
        if first:
            return first
    notes = str(order.get("notes") or "").strip()
    match = re.search(r"\bLot\s+(\d+)\b", notes, re.I)
    if match:
        return match.group(1)
    return ""


def _extract_tiktok_order_id_from_ref(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"\d{15,22}", raw):
        return raw
    match = re.search(r"\b\d{15,22}\b", raw)
    return match.group(0) if match else ""


def _materialize_tiktok_go_live_sale_orders_from_api(session, rows=None):
    if not session or not session.get("id"):
        return {"ok": False, "imported": 0, "skipped": 0, "error": "session_required"}
    session_id = int(session.get("id") or 0)
    if session_id <= 0:
        return {"ok": False, "imported": 0, "skipped": 0, "error": "invalid_session_id"}

    # Do not short-circuit when orders already exist. The duplicate reference
    # guard below keeps order creation idempotent, while still allowing buyer
    # contact details from the TikTok API to refresh existing customer records.

    if rows is None:
        lots = list_company_lots(session_id=session_id, limit=5000)
        base_rows = []
        for lot in sorted(lots, key=lambda value: int(str(value.get("lot_number") or "0").isdigit() and value.get("lot_number") or 0)):
            items = list_lot_items(lot["id"])
            base_rows.append(_tiktok_go_live_row_from_lot_items(lot, items))
        rows = base_rows
    if rows and not any((row.get("tiktokOrder") or {}) for row in rows):
        rows = _enrich_tiktok_go_live_rows_with_pending_orders(session, rows)

    existing_orders = list_sale_orders(session_id=session_id, order_source="tiktok_live")
    existing_by_ref = {}
    for row in existing_orders:
        ref = (row.get("external_order_ref") or "").strip().lower()
        if ref:
            existing_by_ref.setdefault(ref, []).append(row)
    existing_refs = set(existing_by_ref.keys())
    imported = 0
    updated = 0
    skipped = 0
    errors = []
    seen_refs = set(existing_refs)

    def _set_existing_tiktok_live_order_financials(order_id, subtotal, total_amount):
        now = datetime.now(timezone.utc).isoformat()
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_orders
                    SET subtotal = %s,
                        total_amount = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (float(subtotal or 0), float(total_amount or 0), now, int(order_id)),
                )
            conn.commit()

    for row in rows or []:
        match = row.get("tiktokOrder") or {}
        lot_no = str(row.get("lotNo") or "").strip()
        status_family = str(row.get("statusFamily") or match.get("statusFamily") or "").strip().lower()
        if not lot_no or not match or status_family == "unlinked":
            skipped += 1
            continue
        order_id = str(match.get("orderId") or "").strip()
        external_ref = f"tiktok_live:{order_id or 'api'}:{lot_no}"
        ref_key = external_ref.lower()

        buyer_username = str(match.get("buyerUsername") or "").strip()
        buyer_name = str(match.get("buyerName") or "").strip()
        recipient_name = str(match.get("recipientName") or "").strip()
        buyer_display = str(match.get("buyerDisplay") or buyer_username or buyer_name or recipient_name or _tiktok_live_buyer_fallback(match) or "").strip()
        buyer_email = str(match.get("buyerEmail") or match.get("buyer_email") or match.get("email") or "").strip()
        buyer_phone = str(match.get("phone") or match.get("phone_number") or "").strip()
        buyer_address = str(match.get("address") or _tiktok_match_address({
            "full_address": match.get("full_address"),
            "address_line_1": match.get("addressLine1") or match.get("address_line_1"),
            "address_line_2": match.get("addressLine2") or match.get("address_line_2"),
            "address_line_3": match.get("addressLine3") or match.get("address_line_3"),
            "address_line_4": match.get("addressLine4") or match.get("address_line_4"),
            "city": match.get("city"),
            "state": match.get("state"),
            "zipcode": match.get("zipcode"),
            "country": match.get("country"),
        }) or "").strip()
        customer = None
        customer_key = buyer_username or buyer_name or recipient_name or buyer_display or buyer_phone or buyer_email
        try:
            if customer_key:
                customer = upsert_customer(
                    customer_key,
                    display_name=(buyer_name or recipient_name or buyer_display or None),
                    email=(buyer_email or None),
                    phone=(buyer_phone or None),
                    address=(buyer_address or None),
                    platform="tiktok_live",
                    platform_user_id=(buyer_username or order_id or customer_key),
                    identity_username=(buyer_username or buyer_name or recipient_name or None),
                )
        except Exception as exc:
            errors.append(f"customer:{lot_no}:{exc}")
        if ref_key in seen_refs:
            matching_existing_orders = existing_by_ref.get(ref_key) or []
            if matching_existing_orders:
                try:
                    for existing_order in matching_existing_orders:
                        if status_family == "cancelled":
                            update_sale_order(
                                int(existing_order["id"]),
                                state="cancel",
                                fulfillment_status="cancelled",
                                payment_status="unpaid",
                            )
                            _set_existing_tiktok_live_order_financials(int(existing_order["id"]), 0, 0)
                            reverse_sale_order_inventory(int(existing_order["id"]))
                        elif status_family in {"confirmed", "pending"}:
                            sale_price = float(row.get("salesPrice") or match.get("salePrice") or 0)
                            update_sale_order(
                                int(existing_order["id"]),
                                state="sale",
                                fulfillment_status="pending",
                                payment_status="paid",
                            )
                            _set_existing_tiktok_live_order_financials(int(existing_order["id"]), sale_price, sale_price)
                            apply_sale_order_inventory(int(existing_order["id"]))
                        updated += 1
                except Exception as exc:
                    errors.append(f"status_refresh:{lot_no}:{exc}")
            skipped += 1
            continue

        sale_price = float(row.get("salesPrice") or match.get("salePrice") or 0)
        lot_id = None
        try:
            lot_id = int(row.get("lotId") or row.get("id") or 0) or None
        except Exception:
            lot_id = None
        ordered_at = (
            row.get("orderedAt")
            or match.get("createdAt")
            or _tiktok_live_iso_datetime(match.get("created_at"))
            or datetime.now(timezone.utc).isoformat()
        )
        is_cancelled = status_family == "cancelled"
        is_confirmed = status_family == "confirmed"
        items = list(row.get("items") or [])
        try:
            order = create_sale_order(
                session_id=session_id,
                customer_id=customer.get("id") if customer else None,
                buyer_group_id=None,
                whatnot_buyer_username=buyer_username or buyer_display or None,
                state="cancel" if is_cancelled else "sale",
                subtotal=0,
                total_amount=0,
                ordered_at=ordered_at,
                notes=(
                    f"TikTok LIVE RAW live match | Lot {lot_no} | "
                    f"Seller SKU: {match.get('sellerSku') or match.get('seller_sku') or ''} | "
                    f"Status: {match.get('status') or match.get('statusFamily') or ''}"
                ),
                order_source="tiktok_live",
                external_order_ref=external_ref,
                fulfillment_status="cancelled" if is_cancelled else "pending",
                payment_status="paid" if is_confirmed else "unpaid",
            )
            line_count = max(1, len(items))
            unit_split = round(sale_price / line_count, 4) if line_count > 0 else sale_price
            if items:
                for item in items:
                    add_sale_order_line(
                        int(order["id"]),
                        product_id=int(item["productId"]) if item.get("productId") else None,
                        description=(item.get("productName") or row.get("productName") or f"TikTok LIVE lot {lot_no}"),
                        qty=max(1.0, float(item.get("qty") or 1)),
                        unit_price=unit_split,
                        inventory_applied=0,
                        lot_id=lot_id,
                    )
            else:
                add_sale_order_line(
                    int(order["id"]),
                    product_id=int(row["productId"]) if row.get("productId") else None,
                    description=(row.get("productName") or f"TikTok LIVE lot {lot_no}"),
                    qty=1,
                    unit_price=sale_price,
                    inventory_applied=0,
                    lot_id=lot_id,
                )
            if not is_cancelled:
                apply_sale_order_inventory(int(order["id"]))
            imported += 1
            seen_refs.add(ref_key)
        except Exception as exc:
            errors.append(f"order:{lot_no}:{exc}")

    return {"ok": not errors, "imported": imported, "updated": updated, "skipped": skipped, "errors": errors}


def _materialize_tiktok_go_live_live_rows(session, rows):
    """Persist matched live rows as provisional TikTok LIVE sale orders.

    During the live show the lot sheet is still the operator's working surface,
    but downstream Sales, customer history, and inventory need the order as soon
    as TikTok exposes it. The existing materializer is idempotent by
    external_order_ref, so this thin wrapper keeps the hot path scoped to rows
    that actually have TikTok order metadata.
    """
    if not session or str((session or {}).get("status") or "").strip().lower() != "live":
        return {"ok": True, "imported": 0, "updated": 0, "skipped": 0}
    matched_rows = [
        row for row in (rows or [])
        if isinstance(row, dict)
        and isinstance(row.get("tiktokOrder"), dict)
        and str((row.get("tiktokOrder") or {}).get("orderId") or "").strip()
        and str(row.get("lotNo") or "").strip()
        and str(row.get("statusFamily") or (row.get("tiktokOrder") or {}).get("statusFamily") or "").strip().lower()
        not in {"", "unlinked", "review_later", "batch_mismatch"}
    ]
    if not matched_rows:
        return {"ok": True, "imported": 0, "updated": 0, "skipped": 0}
    return _materialize_tiktok_go_live_sale_orders_from_api(session, rows=matched_rows)


def _tiktok_live_manual_status(order):
    state = str(order.get("state") or "").strip().lower()
    fulfillment = str(order.get("fulfillment_status") or "").strip().lower()
    payment = str(order.get("payment_status") or "").strip().lower()
    tracking = str(order.get("tracking_status") or "").strip().lower()
    delivered_at = str(order.get("delivered_at") or "").strip()
    if state == "cancel" or payment in {"cancelled", "unpaid", "refunded"}:
        return "cancelled", "Cancelled"
    if fulfillment == "delivered" or tracking == "delivered" or delivered_at:
        return "confirmed", "Delivered"
    if fulfillment == "shipped":
        return "pending", "Shipped"
    if fulfillment == "packed":
        return "pending", "Packed"
    if payment == "paid":
        return "confirmed", "To ship"
    return "pending", "Imported"


def _enrich_tiktok_go_live_rows_with_sale_orders(session, rows):
    rows = list(rows or [])
    if not session or not rows:
        return rows
    try:
        orders = list_sale_orders(session_id=int(session.get("id") or 0), order_source="tiktok_live")
    except Exception:
        return rows
    orders_by_lot = {}
    for order in orders:
        lot_no = _extract_tiktok_live_lot_number_from_order(order)
        if not lot_no:
            continue
        current = orders_by_lot.get(lot_no)
        current_stamp = str(current.get("ordered_at") or current.get("created_at") or "") if current else ""
        next_stamp = str(order.get("ordered_at") or order.get("created_at") or "")
        if not current or next_stamp >= current_stamp:
            orders_by_lot[lot_no] = order
    enriched = []
    for row in rows:
        lot_no = str(row.get("lotNo") or "").strip()
        order = orders_by_lot.get(lot_no)
        next_row = dict(row)
        if order:
            sale_price = float(order.get("subtotal") or order.get("total_amount") or row.get("salesPrice") or 0)
            cost = float(next_row.get("cost") or 0)
            finance_fee = float(order.get("finance_fee_amount") or 0)
            fees = finance_fee if finance_fee > 0 else _tiktok_live_sale_fee(sale_price)
            status_family, status_label = _tiktok_live_manual_status(order)
            if status_family == "cancelled":
                sale_price = 0.0
                fees = 0.0
                profit = 0.0
            else:
                profit = round(sale_price - fees - cost, 2)
            buyer_display = (
                order.get("display_name")
                or order.get("whatnot_buyer_username")
                or order.get("whatnot_username")
                or ""
            )
            next_row["tiktokOrder"] = {
                "saleOrderId": order.get("id"),
                "orderNumber": order.get("order_number") or "",
                "orderId": (
                    _extract_tiktok_order_id_from_ref(order.get("external_order_ref"))
                    or _extract_tiktok_order_id_from_ref(order.get("order_number"))
                ),
                "externalRef": order.get("external_order_ref") or "",
                "buyerUsername": order.get("whatnot_buyer_username") or "",
                "buyerName": order.get("display_name") or "",
                "buyerDisplay": buyer_display,
                "status": order.get("fulfillment_status") or order.get("state"),
                "statusFamily": status_family,
                "salePrice": sale_price,
                "tiktokFee": fees,
                "feeSource": order.get("fee_source") or ("settled" if finance_fee > 0 else "estimated_6pct"),
                "sellerSku": lot_no,
                "createdAt": order.get("ordered_at") or order.get("created_at"),
                "quantity": order.get("line_qty") or 1,
            }
            next_row["buyer_username"] = order.get("whatnot_buyer_username") or ""
            next_row["buyer"] = buyer_display
            next_row["orderedAt"] = order.get("ordered_at") or order.get("created_at")
            next_row["salesPrice"] = sale_price
            next_row["fees"] = fees
            next_row["profit"] = profit
            next_row["statusLabel"] = status_label
            next_row["statusFamily"] = status_family
        enriched.append(next_row)
    return enriched


def _tiktok_go_live_session_has_sale_orders(session):
    if not session or not session.get("id"):
        return False
    try:
        return bool(list_sale_orders_fast(session_id=int(session.get("id") or 0), order_source="tiktok_live", limit=1))
    except Exception:
        return False


def _tiktok_go_live_recently_ended_without_saved_orders(session, has_saved_orders):
    # Ended TikTok Live auction reviews must be stable. Once a live session is
    # completed, confirmed/cancelled order state is final for our workflow and
    # should come from saved sale_orders/session rows only. Re-querying TikTok
    # here caused the review table to flicker and sometimes reinterpret old
    # statuses while operators were auditing labels, picklists, and packing.
    return False


def _build_tiktok_live_lot_map(csv_text, products):
    if not str(csv_text or "").strip():
        return {}
    lot_map = {}
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        lot_number = _extract_lot_number(row)
        if not lot_number:
            continue
        barcode = (row.get("Barcode") or row.get("barcode") or row.get("UPC") or row.get("upc") or "").strip()
        sku = (row.get("SKU") or row.get("Sku") or row.get("sku") or row.get("Product SKU") or "").strip()
        product_name = (row.get("Product Name") or row.get("Name") or row.get("product_name") or "").strip()
        product = _match_inventory_product_by_code(products, barcode=barcode, sku=sku)
        if not product and product_name:
            product, _score = _match_inventory_product(products, product_name)
        lot_map[_normalize_lot_number(lot_number)] = {
            "lot_number": lot_number,
            "barcode": barcode,
            "sku": sku,
            "product_name": product_name,
            "product": product,
        }
    return lot_map


def _parse_tiktok_float(value, default=0.0):
    raw = (value or "").strip()
    if not raw:
        return float(default)
    raw = raw.replace("$", "").replace(",", "").strip()
    try:
        return float(raw)
    except Exception:
        return float(default)


TIKTOK_BARCODE_ALIASES = {
    "3220360598918": "6290360598918",
}


def _normalize_tiktok_barcode(value):
    raw = (value or "").strip()
    if not raw:
        return ""
    return TIKTOK_BARCODE_ALIASES.get(raw, raw)


TIKTOK_FIELD_MAP = {
    "Order ID": "external_order_id",
    "Order Status": "order_status",
    "Order Substatus": "order_substatus",
    "Cancelation/Return Type": "cancellation_return_type",
    "Normal or Pre-order": "order_type",
    "SKU ID": "external_sku_id",
    "Seller SKU": "seller_sku",
    "Barcode": "barcode",
    "Product Name": "product_name",
    "Variation": "variation_name",
    "Virtual Bundle Seller SKU": "virtual_bundle_seller_sku",
    "Quantity": "quantity",
    "Sku Quantity of return": "returned_quantity",
    "SKU Unit Original Price": "unit_price_original",
    "SKU Subtotal Before Discount": "subtotal_before_discount",
    "SKU Platform Discount": "platform_discount",
    "SKU Seller Discount": "seller_discount",
    "SKU Subtotal After Discount": "subtotal_after_discount",
    "Shipping Fee After Discount": "shipping_fee_after_discount",
    "Original Shipping Fee": "original_shipping_fee",
    "Shipping Fee Seller Discount": "shipping_fee_seller_discount",
    "Co-Funded Shipping Fee Discount": "cofunded_shipping_discount",
    "Shipping Fee Platform Discount": "shipping_fee_platform_discount",
    "Payment platform discount": "payment_platform_discount",
    "Retail Delivery Fee": "retail_delivery_fee",
    "Taxes": "tax_amount",
    "Order Amount": "order_total",
    "Order Refund Amount": "refund_total",
    "Created Time": "created_at",
    "Paid Time": "paid_at",
    "RTS Time": "ready_to_ship_at",
    "Shipped Time": "shipped_at",
    "Delivered Time": "delivered_at",
    "Cancelled Time": "cancelled_at",
    "Cancel By": "cancelled_by",
    "Cancel Reason": "cancel_reason",
    "Fulfillment Type": "fulfillment_type",
    "Warehouse Name": "warehouse_name",
    "Tracking ID": "tracking_number",
    "Delivery Option Type": "delivery_option_type",
    "Delivery Option": "delivery_option",
    "Shipping Provider Name": "shipping_provider",
    "Buyer Message": "buyer_message",
    "Buyer Nickname": "buyer_nickname",
    "Buyer Username": "buyer_username",
    "Recipient": "recipient_name",
    "Phone #": "phone",
    "Country": "country",
    "State": "state",
    "City": "city",
    "Zipcode": "zipcode",
    "Address Line 1": "address_line_1",
    "Address Line 2": "address_line_2",
    "Delivery Instruction": "delivery_instruction",
    "Payment Method": "payment_method",
    "Weight(kg)": "weight_kg",
    "Product Category": "product_category",
    "Package ID": "external_package_id",
    "Seller Note": "seller_note",
    "Shipping Information": "shipping_information_raw",
    "Combined Listing": "combined_listing",
}


def _parse_tiktok_datetime(value):
    raw = (value or "").strip()
    if not raw:
        return None
    formats = (
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except Exception:
            pass
    return None


def _tiktok_normalized_row(row):
    normalized = {}
    for source_key, target_key in TIKTOK_FIELD_MAP.items():
        normalized[target_key] = (row.get(source_key) or "").strip()
    normalized["barcode"] = _normalize_tiktok_barcode(normalized.get("barcode"))
    return normalized


def _compact_label_text(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _is_random_banger_listing(value):
    compact = _compact_label_text(value)
    return (
        ("randombangerperfume" in compact or "bangerperfume" in compact)
        and ("nocancellation" in compact or "nocancelation" in compact)
    )


def _resolved_tiktok_live_product_name(original_name, lot_match=None, product=None):
    """TikTok labels use one generic auction listing; the Seller SKU is the lot number."""
    if not _is_random_banger_listing(original_name):
        return str(original_name or "").strip()
    if product and str(product.get("name") or "").strip():
        return str(product.get("name")).strip()
    if lot_match and str(lot_match.get("product_name") or "").strip():
        return str(lot_match.get("product_name")).strip()
    return str(original_name or "").strip()


def _extract_tiktok_tracking_number(text):
    raw = str(text or "")
    explicit = (
        re.search(r"Tracking\s+number:\s*([0-9][0-9\s-]{15,})", raw, re.I)
        or re.search(r"Tracking:\s*([0-9][0-9\s-]{15,})", raw, re.I)
    )
    if explicit:
        normalized = re.sub(r"\D+", "", explicit.group(1).strip())
        if len(normalized) >= 20:
            return normalized
    digit_runs = re.findall(r"(?:\d[\s-]?){20,30}", raw)
    for candidate in digit_runs:
        normalized = re.sub(r"\D+", "", candidate or "")
        if len(normalized) >= 20:
            return normalized
    return ""


def _ocr_tracking_number_from_pdf_page(page):
    try:
        from PyPDF2 import PdfWriter
    except Exception:
        return ""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "page.pdf")
            image_prefix = os.path.join(tmpdir, "page")
            writer = PdfWriter()
            writer.add_page(page)
            with open(pdf_path, "wb") as handle:
                writer.write(handle)
            subprocess.run(
                ["pdftoppm", "-png", "-singlefile", pdf_path, image_prefix],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            image_path = image_prefix + ".png"
            result = subprocess.run(
                ["tesseract", image_path, "stdout", "--psm", "6"],
                check=True,
                capture_output=True,
                text=True,
            )
            return _extract_tiktok_tracking_number(result.stdout)
    except Exception:
        return ""


def _normalize_tiktok_buyer_key(value):
    cleaned = unicodedata.normalize("NFKD", str(value or ""))
    cleaned = cleaned.replace("’", "'").replace("`", "'").lower()
    cleaned = re.sub(r"[^a-z0-9@._'-]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_tiktok_label_page_identity(text):
    raw = str(text or "")
    order_match = re.search(r"Order\s+ID:\s*([0-9]+)", raw, re.I)
    qty_total_match = re.search(r"Qty\s+Total:\s*(\d+)", raw, re.I)
    buyer_id_match = re.search(r"Buyer\s+ID:\s*([^\n]+)", raw, re.I)
    buyer_nickname_match = re.search(r"Buyer\s+Nickname:\s*([^\n]+)", raw, re.I)
    tracking_number = _extract_tiktok_tracking_number(raw)
    seller_sku = ""
    seller_skus = []
    seller_items = []
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    table_started = False
    collecting = []
    for line in lines:
        lower = line.lower()
        if lower == "qty":
            table_started = True
            collecting = []
            continue
        if not table_started:
            continue
        if lower.startswith("qty total") or lower.startswith("order id:"):
            break
        collecting.append(line)

    idx = 0
    while idx < len(collecting):
        name_lines = []
        while idx < len(collecting) and not re.fullmatch(r"[A-Za-z0-9._-]+", collecting[idx]):
            name_lines.append(collecting[idx])
            idx += 1
        if idx + 2 >= len(collecting):
            break
        sku_candidate = collecting[idx].strip()
        seller_candidate = collecting[idx + 1].strip()
        qty_candidate = collecting[idx + 2].strip()
        if (
            re.fullmatch(r"[A-Za-z0-9._-]+", sku_candidate)
            and re.fullmatch(r"[A-Za-z0-9._-]+", seller_candidate)
            and re.fullmatch(r"\d+(?:\.\d+)?", qty_candidate)
        ):
            if seller_candidate and seller_candidate not in seller_skus:
                seller_skus.append(seller_candidate)
            seller_items.append({
                "seller_sku": seller_candidate,
                "sku": sku_candidate,
                "listing_name": " ".join(name_lines).strip(),
                "qty": qty_candidate,
            })
            idx += 3
            continue
        idx += 1

    if seller_skus:
        seller_sku = seller_skus[-1]

    if not seller_skus:
        for table_match in re.finditer(
            r"\(NO\s+CANCELLATIONS\)\s*([A-Za-z0-9._-]+)\s+([A-Za-z0-9._-]+)\s+\d+",
            raw,
            re.I,
        ):
            candidate = table_match.group(2).strip()
            if candidate and candidate not in seller_skus:
                seller_skus.append(candidate)
        if seller_skus:
            seller_sku = seller_skus[-1]
    if seller_sku and seller_sku not in seller_skus:
        seller_skus.append(seller_sku)
    return {
        "order_id": order_match.group(1) if order_match else "",
        "tracking_number": tracking_number,
        "qty_total": int(qty_total_match.group(1)) if qty_total_match else 0,
        "buyer_id": buyer_id_match.group(1).strip() if buyer_id_match else "",
        "buyer_nickname": buyer_nickname_match.group(1).strip() if buyer_nickname_match else "",
        "seller_sku": seller_sku,
        "seller_skus": seller_skus,
        "seller_items": seller_items,
    }


def _fetch_tiktok_live_session_lot_products(session_ids):
    clean_ids = sorted({int(value) for value in session_ids or [] if value})
    if not clean_ids:
        return {}
    lot_products = {}
    for session_id in clean_ids:
        for lot in list_company_lots(session_id=session_id, limit=2000):
            lot_number = str(lot.get("lot_number") or "").strip()
            if not lot_number:
                continue
            names = lot_products.setdefault(int(session_id), {}).setdefault(lot_number, [])
            for item in list_lot_items(lot.get("id")):
                product_name = str(item.get("product_name") or "").strip()
                if not product_name and item.get("product_id"):
                    product = get_product(int(item["product_id"])) or {}
                    product_name = str(product.get("name") or "").strip()
                if product_name and product_name not in names:
                    names.append(product_name)
    return lot_products


_TIKTOK_GO_LIVE_SHOW_PREFIX = "tiktok:ynfdeals:go-live:"
_TIKTOK_GO_LIVE_LEGACY_PREFIX = "tiktok:ynfdeals"
_TIKTOK_GO_LIVE_MIN_AUTO_SEQUENCE = 23
_TIKTOK_LABEL_ARTIFACT_LOCK = threading.Lock()
_TIKTOK_LABEL_ARTIFACT_TABLE = "tiktok_live_label_artifacts"
_TIKTOK_GO_LIVE_BACKUP_DIRNAME = "tiktok_go_live_backups"
_TIKTOK_LIVE_PENDING_RESERVE_REF = "tiktok_live_pending_item"
_TIKTOK_LIVE_PENDING_RELEASE_REF = "tiktok_live_pending_item_release"


def _is_tiktok_go_live_session_row(row):
    show_id = str((row or {}).get("show_id") or "").strip().lower()
    name = str((row or {}).get("name") or "").strip().lower()
    if not show_id and not name:
        return False
    if show_id.startswith(_TIKTOK_GO_LIVE_SHOW_PREFIX):
        return True
    if show_id == _TIKTOK_GO_LIVE_LEGACY_PREFIX or show_id.startswith(f"{_TIKTOK_GO_LIVE_LEGACY_PREFIX}:"):
        # Keep only numbered Go Live session shells from the pre-prefix era.
        if "sheet-sync" in show_id:
            return "go live session" in name
        return "go live session" in name
    return "go live session" in name


def _tiktok_go_live_backup_dir():
    path = os.path.join(os.path.dirname(DB_PATH), _TIKTOK_GO_LIVE_BACKUP_DIRNAME)
    os.makedirs(path, exist_ok=True)
    return path


def _tiktok_go_live_journal_path(session_id):
    return os.path.join(_tiktok_go_live_backup_dir(), f"session_{int(session_id)}_journal.csv")


def _tiktok_go_live_snapshot_path(session_id):
    return os.path.join(_tiktok_go_live_backup_dir(), f"session_{int(session_id)}_snapshot.csv")


def _tiktok_go_live_download_dir():
    path = os.path.expanduser("~/Downloads")
    os.makedirs(path, exist_ok=True)
    return path


def _is_tiktok_go_live_review_later_row(row):
    return bool(
        (row or {}).get("reviewLater")
        or str((row or {}).get("notes") or "").strip().lower() == "review_later"
        or str((row or {}).get("productName") or (row or {}).get("product_name") or "").strip().lower() == "review later"
        or str((row or {}).get("statusFamily") or "").strip().lower() == "review_later"
    )


def _tiktok_go_live_operator_csv_path(session_payload):
    sequence = int((session_payload or {}).get("sequence") or (session_payload or {}).get("serverSessionId") or 0)
    label = sequence if sequence > 0 else "draft"
    return os.path.join(_tiktok_go_live_download_dir(), f"tiktok-go-live-session-{label}-rolling.csv")


def _write_tiktok_go_live_operator_csv(session_payload):
    rows = list((session_payload or {}).get("rows") or [])
    path = _tiktok_go_live_operator_csv_path(session_payload)
    header = [
        "lot_no",
        "barcode",
        "product_name",
        "review_later",
        "cost",
        "buyer_name",
        "sale_price",
        "fee",
        "profit",
        "status",
        "notes",
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for row in rows:
            sale_price = float(row.get("tiktokOrder", {}).get("salePrice") or row.get("salesPrice") or 0)
            cost = float(row.get("cost") or 0)
            fee = float(row.get("fees") or 0)
            profit = round(sale_price - (cost + fee), 2)
            writer.writerow({
                "lot_no": str(row.get("lotNo") or "").strip(),
                "barcode": str(row.get("barcode") or "").strip(),
                "product_name": str(row.get("productName") or "").strip(),
                "review_later": "yes" if _is_tiktok_go_live_review_later_row(row) else "",
                "cost": f"{cost:.2f}",
                "buyer_name": str(row.get("buyer") or row.get("tiktokOrder", {}).get("buyerDisplay") or "").strip(),
                "sale_price": f"{sale_price:.2f}",
                "fee": f"{fee:.2f}",
                "profit": f"{profit:.2f}",
                "status": str(row.get("statusLabel") or "").strip(),
                "notes": str(row.get("notes") or "").strip(),
            })
    return path


def _build_tiktok_go_live_all_sessions_csv(limit=1000):
    session_limit = max(1, min(int(limit or 1000), 2000))
    sessions = _list_tiktok_go_live_session_rows_fast(limit=session_limit)
    header = [
        "session_id",
        "session_sequence",
        "session_name",
        "session_status",
        "session_started_at",
        "session_ended_at",
        "lot_no",
        "barcode",
        "sku",
        "product_name",
        "product_id",
        "item_id",
        "item_count",
        "review_later",
        "buyer",
        "buyer_username",
        "sale_order_id",
        "sale_order_number",
        "tiktok_order_id",
        "external_order_ref",
        "sale_price",
        "cost",
        "fee",
        "profit",
        "status",
        "status_family",
        "ordered_at",
        "notes",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header)
    writer.writeheader()
    row_count = 0
    for session in sessions:
        sequence = None
        match = re.search(r"Go Live Session\s*-?\s*(\d+)", str(session.get("name") or ""), re.I)
        if match:
            sequence = int(match.group(1))
        lots = list_company_lots(session_id=session["id"], limit=3000)
        rows = []
        for lot in sorted(lots, key=lambda value: int(str(value.get("lot_number") or "0").isdigit() and value.get("lot_number") or 0)):
            rows.append(_tiktok_go_live_row_from_lot_items(lot, list_lot_items(lot["id"])))
        rows = _enrich_tiktok_go_live_rows_with_sale_orders(session, rows)
        rows = _pad_tiktok_go_live_rows(session, rows)
        for row in rows:
            order = row.get("tiktokOrder") or {}
            has_export_value = any(
                str(row.get(key) or "").strip()
                for key in ("barcode", "sku", "productName", "buyer", "statusLabel", "notes")
            ) or bool(order)
            if not has_export_value:
                continue
            writer.writerow({
                "session_id": session.get("id"),
                "session_sequence": sequence or "",
                "session_name": session.get("name") or "",
                "session_status": session.get("status") or "",
                "session_started_at": session.get("started_at") or "",
                "session_ended_at": session.get("ended_at") or session.get("updated_at") or "",
                "lot_no": row.get("lotNo") or "",
                "barcode": row.get("barcode") or "",
                "sku": row.get("sku") or "",
                "product_name": row.get("productName") or "",
                "product_id": row.get("productId") or "",
                "item_id": row.get("itemId") or "",
                "item_count": row.get("itemCount") or "",
                "review_later": "yes" if _is_tiktok_go_live_review_later_row(row) else "",
                "buyer": row.get("buyer") or order.get("buyerDisplay") or "",
                "buyer_username": row.get("buyer_username") or row.get("buyerUsername") or order.get("buyerUsername") or "",
                "sale_order_id": order.get("saleOrderId") or "",
                "sale_order_number": order.get("orderNumber") or "",
                "tiktok_order_id": order.get("orderId") or "",
                "external_order_ref": order.get("externalRef") or "",
                "sale_price": row.get("salesPrice") or order.get("salePrice") or "",
                "cost": row.get("cost") or "",
                "fee": row.get("fees") or "",
                "profit": row.get("profit") or "",
                "status": row.get("statusLabel") or order.get("status") or "",
                "status_family": row.get("statusFamily") or order.get("statusFamily") or "",
                "ordered_at": row.get("orderedAt") or order.get("createdAt") or "",
                "notes": row.get("notes") or "",
            })
            row_count += 1
    return buf.getvalue(), row_count, len(sessions)


def _list_tiktok_go_live_session_rows_fast(limit=80):
    session_limit = int(limit or 80)
    if not postgres_available():
        raise RuntimeError("postgres_unavailable")
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.company_sessions
                ORDER BY COALESCE(ended_at, updated_at, started_at, '') DESC, id DESC
                LIMIT %s
                """,
                (max(session_limit * 4, 200),),
            )
            cols = [desc[0] for desc in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    filtered = [row for row in rows if _is_tiktok_go_live_session_row(row)]
    filtered.sort(
        key=lambda row: (
            str(row.get("ended_at") or row.get("updated_at") or row.get("started_at") or ""),
            int(row.get("id") or 0),
        ),
        reverse=True,
    )
    return filtered[:session_limit]


def _write_csv_row_durably(path, header, row):
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        if not file_exists or os.path.getsize(path) == 0:
            writer.writeheader()
        writer.writerow(row)
        handle.flush()
        os.fsync(handle.fileno())


def _rewrite_csv_durably(path, header, rows):
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def _append_tiktok_go_live_journal(session, action, lot_no="", item=None, row=None, extra=None):
    session = session or {}
    item = item or {}
    row = row or {}
    extra = extra or {}
    journal_row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "session_id": int(session.get("id") or 0),
        "session_name": session.get("name") or "",
        "session_status": session.get("status") or "",
        "show_id": session.get("show_id") or "",
        "lot_no": str(lot_no or row.get("lotNo") or row.get("lot_number") or "").strip(),
        "item_id": row.get("itemId") or item.get("id") or "",
        "barcode": str(row.get("barcode") or item.get("barcode") or "").strip(),
        "sku": row.get("sku") or item.get("sku") or "",
        "product_id": row.get("productId") or item.get("product_id") or "",
        "product_name": (
            row.get("productName")
            or row.get("product_name")
            or item.get("product_name")
            or item.get("linked_product_name")
            or ""
        ),
        "matched": int(bool(row.get("matched") or row.get("productId") or item.get("product_id"))),
        "cost": row.get("cost") if row.get("cost") is not None else (item.get("unit_cost") if item.get("unit_cost") is not None else ""),
        "notes": str(row.get("notes") or item.get("notes") or "").strip(),
        "extra_json": json.dumps(extra, ensure_ascii=True, sort_keys=True),
    }
    _write_csv_row_durably(
        _tiktok_go_live_journal_path(session.get("id")),
        [
            "timestamp",
            "action",
            "session_id",
            "session_name",
            "session_status",
            "show_id",
            "lot_no",
            "item_id",
            "barcode",
            "sku",
            "product_id",
            "product_name",
            "matched",
            "cost",
            "notes",
            "extra_json",
        ],
        journal_row,
    )


def _write_tiktok_go_live_snapshot(session):
    session = session or {}
    session_id = int(session.get("id") or 0)
    if session_id <= 0:
        return
    lots = list_company_lots(session_id=session_id, limit=2000)
    lots_by_number = {str(lot.get("lot_number") or ""): lot for lot in lots}
    ordered_numbers = sorted(
        lots_by_number.keys(),
        key=lambda value: (0, int(value)) if str(value).isdigit() else (1, str(value)),
    )
    snapshot_at = datetime.now(timezone.utc).isoformat()
    snapshot_rows = []
    for lot_no in ordered_numbers:
        lot = lots_by_number.get(lot_no) or {}
        items = list_lot_items(int(lot.get("id"))) if lot.get("id") else []
        barcodes = [str(item.get("barcode") or "").strip() for item in items if str(item.get("barcode") or "").strip()]
        skus = [str(item.get("sku") or "").strip() for item in items if str(item.get("sku") or "").strip()]
        product_ids = [str(item.get("product_id") or "").strip() for item in items if item.get("product_id") is not None]
        product_names = [
            str(item.get("product_name") or item.get("linked_product_name") or "").strip()
            for item in items
            if str(item.get("product_name") or item.get("linked_product_name") or "").strip()
        ]
        notes = [str(item.get("notes") or "").strip() for item in items if str(item.get("notes") or "").strip()]
        total_cost = sum(float(item.get("unit_cost") or 0) for item in items)
        last_scanned_at = max((str(item.get("scanned_at") or "").strip() for item in items if str(item.get("scanned_at") or "").strip()), default="")
        snapshot_rows.append({
            "session_id": session_id,
            "session_name": session.get("name") or "",
            "session_status": session.get("status") or "",
            "show_id": session.get("show_id") or "",
            "lot_no": str(lot_no or "").strip(),
            "lot_status": lot.get("status") or "",
            "item_id": " / ".join(str(item.get("id") or "") for item in items if item.get("id") is not None),
            "barcode": " / ".join(barcodes),
            "sku": " / ".join(skus),
            "product_id": " / ".join(product_ids),
            "product_name": " + ".join(product_names),
            "matched": int(bool(product_ids)),
            "notes": " | ".join(notes),
            "cost": total_cost if items else "",
            "on_hand_qty": "",
            "scanned_at": last_scanned_at,
            "snapshot_at": snapshot_at,
        })
    _rewrite_csv_durably(
        _tiktok_go_live_snapshot_path(session_id),
        [
            "session_id",
            "session_name",
            "session_status",
            "show_id",
            "lot_no",
            "lot_status",
            "item_id",
            "barcode",
            "sku",
            "product_id",
            "product_name",
            "matched",
            "notes",
            "cost",
            "on_hand_qty",
            "scanned_at",
            "snapshot_at",
        ],
        snapshot_rows,
    )


def _ensure_tiktok_label_artifact_schema():
    if not postgres_available():
        raise RuntimeError("postgres_unavailable")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {}.{} (
                        id TEXT PRIMARY KEY,
                        session_key TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        original_filename TEXT,
                        original_pdf BYTEA,
                        output_pdf BYTEA NOT NULL,
                        annotated INTEGER NOT NULL DEFAULT 0,
                        total INTEGER NOT NULL DEFAULT 0,
                        original_sha256 TEXT,
                        output_sha256 TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                ).format(
                    sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                    sql.Identifier(_TIKTOK_LABEL_ARTIFACT_TABLE),
                )
            )
            cur.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {}.{} (session_key, created_at DESC)").format(
                    sql.Identifier("idx_tiktok_live_label_artifacts_session_key_created"),
                    sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                    sql.Identifier(_TIKTOK_LABEL_ARTIFACT_TABLE),
                )
            )
        conn.commit()


def _safe_tiktok_label_token(value, fallback="session"):
    token = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return token[:120] or fallback


def _safe_tiktok_label_filename(value):
    filename = re.sub(r"[^A-Za-z0-9._ -]+", "", str(value or "").strip()) or "tiktok-live-labels.pdf"
    filename = filename.replace('"', "").strip()
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    return filename


def _row_to_tiktok_label_artifact(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "session_key": row["session_key"],
        "filename": row["filename"],
        "original_filename": row["original_filename"],
        "original_pdf": row["original_pdf"],
        "output_pdf": row["output_pdf"],
        "annotated": int(row["annotated"] or 0),
        "total": int(row["total"] or 0),
        "original_sha256": row["original_sha256"],
        "output_sha256": row["output_sha256"],
        "created_at": row["created_at"],
    }


def _public_tiktok_label_artifact(row):
    if not row:
        return None
    return {
        "id": row.get("id"),
        "session_key": row.get("session_key"),
        "filename": row.get("filename"),
        "annotated": int(row.get("annotated") or 0),
        "total": int(row.get("total") or 0),
        "created_at": row.get("created_at"),
        "has_original_pdf": bool(row.get("original_pdf")),
    }


def _normalize_public_identity(value):
    return str(value or "").strip().lower()


def _normalize_public_phone(value):
    return re.sub(r"\D+", "", str(value or ""))


def _guest_in_house_order_access_allowed(order, buyer_name=None, buyer_phone=None, buyer_email=None):
    if not order:
        return False
    if _normalize_public_identity(order.get("employee_name")) != _normalize_public_identity(buyer_name):
        return False
    order_phone = _normalize_public_phone(order.get("buyer_phone"))
    order_email = _normalize_public_identity(order.get("buyer_email"))
    input_phone = _normalize_public_phone(buyer_phone)
    input_email = _normalize_public_identity(buyer_email)
    if order_phone and order_phone != input_phone:
        return False
    if order_email and order_email != input_email:
        return False
    return True


def _save_tiktok_label_artifact(session_key, filename, pdf_bytes, annotated, total, *, original_pdf_bytes=None, original_filename=None):
    clean_session_key = _safe_tiktok_label_token(session_key, fallback="session")
    safe_name = _safe_tiktok_label_filename(filename)
    digest = __import__("hashlib").sha256(pdf_bytes).hexdigest()[:10]
    created_at = datetime.now(timezone.utc).isoformat()
    artifact_id = f"{clean_session_key}-{int(time.time())}-{digest}"
    with _TIKTOK_LABEL_ARTIFACT_LOCK:
        _ensure_tiktok_label_artifact_schema()
        entry = {
            "id": artifact_id,
            "session_key": str(session_key or "").strip(),
            "filename": safe_name,
            "original_filename": _safe_tiktok_label_filename(original_filename or filename) if (original_filename or filename) else None,
            "original_pdf": original_pdf_bytes,
            "output_pdf": pdf_bytes,
            "annotated": int(annotated or 0),
            "total": int(total or 0),
            "original_sha256": __import__("hashlib").sha256(original_pdf_bytes).hexdigest() if original_pdf_bytes else None,
            "output_sha256": __import__("hashlib").sha256(pdf_bytes).hexdigest(),
            "created_at": created_at,
        }
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        INSERT INTO {}.{} (
                            id, session_key, filename, original_filename, original_pdf, output_pdf,
                            annotated, total, original_sha256, output_sha256, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            session_key = EXCLUDED.session_key,
                            filename = EXCLUDED.filename,
                            original_filename = EXCLUDED.original_filename,
                            original_pdf = EXCLUDED.original_pdf,
                            output_pdf = EXCLUDED.output_pdf,
                            annotated = EXCLUDED.annotated,
                            total = EXCLUDED.total,
                            original_sha256 = EXCLUDED.original_sha256,
                            output_sha256 = EXCLUDED.output_sha256,
                            created_at = EXCLUDED.created_at
                        """
                    ).format(
                        sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                        sql.Identifier(_TIKTOK_LABEL_ARTIFACT_TABLE),
                    ),
                    (
                        entry["id"],
                        entry["session_key"],
                        entry["filename"],
                        entry["original_filename"],
                        entry["original_pdf"],
                        entry["output_pdf"],
                        entry["annotated"],
                        entry["total"],
                        entry["original_sha256"],
                        entry["output_sha256"],
                        entry["created_at"],
                    ),
                )
            conn.commit()
    return entry


def _latest_tiktok_label_artifact(session_key):
    clean_key = str(session_key or "").strip()
    if not clean_key:
        return None
    with _TIKTOK_LABEL_ARTIFACT_LOCK:
        _ensure_tiktok_label_artifact_schema()
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        SELECT id, session_key, filename, original_filename, original_pdf, output_pdf,
                               annotated, total, original_sha256, output_sha256, created_at
                        FROM {}.{}
                        WHERE session_key = %s
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                        """
                    ).format(
                        sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                        sql.Identifier(_TIKTOK_LABEL_ARTIFACT_TABLE),
                    ),
                    (clean_key,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return _row_to_tiktok_label_artifact(dict(zip((desc[0] for desc in cur.description), row)))
    return None


def _get_tiktok_label_artifact(artifact_id):
    clean_id = str(artifact_id or "").strip()
    if not clean_id:
        return None
    with _TIKTOK_LABEL_ARTIFACT_LOCK:
        _ensure_tiktok_label_artifact_schema()
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        SELECT id, session_key, filename, original_filename, original_pdf, output_pdf,
                               annotated, total, original_sha256, output_sha256, created_at
                        FROM {}.{}
                        WHERE id = %s
                        LIMIT 1
                        """
                    ).format(
                        sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                        sql.Identifier(_TIKTOK_LABEL_ARTIFACT_TABLE),
                    ),
                    (clean_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return _row_to_tiktok_label_artifact(dict(zip((desc[0] for desc in cur.description), row)))
    return None


def _tiktok_go_live_row_from_lot(row):
    product_name = str(row.get("product_name") or row.get("linked_product_name") or "").strip()
    winner_username = str(row.get("winner_username") or "").strip()
    review_later = str(row.get("notes") or "").strip().lower() == "review_later" or product_name.lower() == "review later"
    return {
        "lotNo": str(row.get("lot_number") or "").strip(),
        "barcode": str(row.get("barcode") or "").strip(),
        "productName": product_name,
        "notes": str(row.get("notes") or "").strip(),
        "sku": str(row.get("sku") or "").strip(),
        "cost": float(row.get("unit_cost") or 0),
        "productId": row.get("product_id"),
        "itemId": row.get("id"),
        "matched": bool(product_name),
        "buyer": winner_username,
        "buyerUsername": winner_username,
        "buyer_username": winner_username,
        "winner_username": winner_username,
        "reviewLater": review_later,
        "statusFamily": "review_later" if review_later else ("pending" if winner_username else ""),
        "statusLabel": "Review later" if review_later else ("Pending" if winner_username else ""),
    }


def _tiktok_go_live_row_from_lot_items(lot, items):
    lot = lot or {}
    items = list(items or [])
    if not items:
        winner_username = str(lot.get("winner_username") or "").strip()
        return {
            "lotNo": str(lot.get("lot_number") or "").strip(),
            "barcode": "",
            "productName": "",
            "notes": "",
            "sku": "",
            "cost": 0,
            "productId": None,
            "itemId": None,
            "matched": False,
            "itemCount": 0,
            "items": [],
            "buyer": winner_username,
            "buyerUsername": winner_username,
            "buyer_username": winner_username,
            "winner_username": winner_username,
            "reviewLater": False,
            "statusFamily": "pending" if winner_username else "",
            "statusLabel": "Pending" if winner_username else "",
        }
    if len(items) == 1:
        item = dict(items[0])
        item["winner_username"] = lot.get("winner_username")
        item["lot_number"] = lot.get("lot_number")
        row = _tiktok_go_live_row_from_lot(item)
        row["itemCount"] = 1
        row["items"] = [{
            "itemId": item.get("id"),
            "productId": item.get("product_id"),
            "barcode": str(item.get("barcode") or "").strip(),
            "sku": str(item.get("sku") or "").strip(),
            "productName": str(item.get("product_name") or item.get("linked_product_name") or "").strip(),
            "cost": float(item.get("unit_cost") or 0),
            "notes": str(item.get("notes") or "").strip(),
        }]
        return row

    normalized_items = []
    for item in items:
        normalized_items.append({
            "itemId": item.get("id"),
            "productId": item.get("product_id"),
            "barcode": str(item.get("barcode") or "").strip(),
            "sku": str(item.get("sku") or "").strip(),
            "productName": str(item.get("product_name") or item.get("linked_product_name") or "").strip(),
            "cost": float(item.get("unit_cost") or 0),
            "notes": str(item.get("notes") or "").strip(),
        })

    product_names = [item["productName"] for item in normalized_items if item["productName"]]
    barcodes = [item["barcode"] for item in normalized_items if item["barcode"]]
    skus = [item["sku"] for item in normalized_items if item["sku"]]
    notes = [item["notes"] for item in normalized_items if item["notes"]]
    product_ids = [item["productId"] for item in normalized_items if item["productId"] is not None]
    item_ids = [item["itemId"] for item in normalized_items if item["itemId"] is not None]
    count = len(normalized_items)
    summary_name = f"({count} products) " + " + ".join(product_names) if product_names else f"({count} products)"
    winner_username = str(lot.get("winner_username") or "").strip()
    review_later = any(item["notes"].strip().lower() == "review_later" or item["productName"].strip().lower() == "review later" for item in normalized_items)
    return {
        "lotNo": str(lot.get("lot_number") or "").strip(),
        "barcode": " / ".join(barcodes),
        "productName": summary_name,
        "notes": " | ".join(notes),
        "sku": " / ".join(skus),
        "cost": round(sum(float(item["cost"] or 0) for item in normalized_items), 4),
        "productId": product_ids[0] if len(product_ids) == 1 else None,
        "itemId": item_ids[0] if len(item_ids) == 1 else None,
        "matched": bool(product_names),
        "itemCount": count,
        "items": normalized_items,
        "productIds": product_ids,
        "itemIds": item_ids,
        "buyer": winner_username,
        "buyerUsername": winner_username,
        "buyer_username": winner_username,
        "winner_username": winner_username,
        "reviewLater": review_later,
        "statusFamily": "review_later" if review_later else ("pending" if winner_username else ""),
        "statusLabel": "Review later" if review_later else ("Pending" if winner_username else ""),
    }


def _summarize_tiktok_go_live_rows(rows):
    counted_rows = [
        row for row in (rows or [])
        if str(row.get("barcode") or "").strip() or _is_tiktok_go_live_review_later_row(row)
    ]
    sold_like = [row for row in counted_rows if str(row.get("statusFamily") or "") in {"pending", "confirmed"}]
    cancelled = [row for row in counted_rows if str(row.get("statusFamily") or "") == "cancelled"]
    buyers = {
        str(row.get("buyer") or "").strip().lower()
        for row in sold_like
        if str(row.get("buyer") or "").strip()
    }
    return {
        "totalLots": len(counted_rows),
        "pendingLots": sum(1 for row in counted_rows if str(row.get("statusFamily") or "") == "pending"),
        "confirmedLots": sum(1 for row in counted_rows if str(row.get("statusFamily") or "") == "confirmed"),
        "cancelledLots": len(cancelled),
        "customerCount": len(buyers),
        "revenue": round(sum(float(row.get("salesPrice") or 0) for row in sold_like), 2),
        "profit": round(sum(float(row.get("profit") or 0) for row in sold_like), 2),
    }


def _extract_tiktok_live_lot_from_ref_value(ref):
    match = re.search(r"tiktok_live:[^:]+:([^:]+)", str(ref or ""))
    return match.group(1).strip() if match else ""


def _summarize_tiktok_go_live_session_fast(session):
    if not session or not session.get("id"):
        return {"lotCount": 0, "summary": _summarize_tiktok_go_live_rows([]), "lastSoldAt": ""}
    session_id = int(session.get("id") or 0)
    lot_count = 0
    lot_costs = {}
    orders = []
    if not postgres_available():
        raise RuntimeError("postgres_unavailable")
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM {POSTGRES_SIDECAR_SCHEMA}.company_lots cl
                WHERE cl.session_id = %s
                """,
                (session_id,),
            )
            lot_count = int(cur.fetchone()[0] or 0)
            cur.execute(
                f"""
                SELECT cl.lot_number, COALESCE(SUM(li.unit_cost), 0)
                FROM {POSTGRES_SIDECAR_SCHEMA}.company_lots cl
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_lot_items li ON li.lot_id = cl.id
                WHERE cl.session_id = %s
                GROUP BY cl.lot_number
                """,
                (session_id,),
            )
            lot_costs = {str(lot_no or "").strip(): float(cost or 0) for lot_no, cost in cur.fetchall()}
            cur.execute(
                f"""
                SELECT so.external_order_ref, so.state, so.fulfillment_status, so.payment_status,
                       so.total_amount, so.subtotal, so.ordered_at, so.created_at,
                       so.whatnot_buyer_username, c.display_name AS display_name,
                       so.tracking_status, so.delivered_at,
                       ABS(COALESCE(tfr.fee_amount, 0)) AS finance_fee_amount
                FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c
                  ON c.id = so.customer_id
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.tiktok_finance_order_records tfr
                  ON tfr.sale_order_id = so.id
                 AND ABS(COALESCE(tfr.fee_amount, 0)) > 0
                WHERE so.session_id = %s
                  AND so.order_source = 'tiktok_live'
                  AND COALESCE(so.external_order_ref, '') NOT LIKE 'archived_duplicate:%%'
                """,
                (session_id,),
            )
            cols = [
                "external_order_ref", "state", "fulfillment_status", "payment_status",
                "total_amount", "subtotal", "ordered_at", "created_at",
                "whatnot_buyer_username", "display_name", "tracking_status", "delivered_at",
                "finance_fee_amount",
            ]
            orders = [dict(zip(cols, row)) for row in cur.fetchall()]
    orders_by_lot = {}
    for order in orders:
        lot_no = _extract_tiktok_live_lot_from_ref_value(order.get("external_order_ref"))
        if not lot_no:
            continue
        current = orders_by_lot.get(lot_no)
        current_stamp = str(current.get("ordered_at") or current.get("created_at") or "") if current else ""
        next_stamp = str(order.get("ordered_at") or order.get("created_at") or "")
        if not current or next_stamp >= current_stamp:
            orders_by_lot[lot_no] = order

    pending_lots = 0
    confirmed_lots = 0
    cancelled_lots = 0
    revenue = 0.0
    cost_of_goods = 0.0
    platform_fees = 0.0
    profit = 0.0
    buyers = set()
    last_sold_at = ""
    for order in orders_by_lot.values():
        status_family, _status_label = _tiktok_live_manual_status(order)
        sale_price = float(order.get("subtotal") or order.get("total_amount") or 0)
        lot_no = _extract_tiktok_live_lot_from_ref_value(order.get("external_order_ref"))
        cost = float(lot_costs.get(lot_no, 0))
        finance_fee = float(order.get("finance_fee_amount") or 0)
        fees = finance_fee if finance_fee > 0 else _tiktok_live_sale_fee(sale_price)
        buyer = str(order.get("display_name") or order.get("whatnot_buyer_username") or "").strip().lower()
        ordered_at = str(order.get("ordered_at") or order.get("created_at") or "").strip()
        if ordered_at and ordered_at > last_sold_at:
            last_sold_at = ordered_at
        if buyer and status_family in {"pending", "confirmed"}:
            buyers.add(buyer)
        if status_family == "cancelled":
            cancelled_lots += 1
            continue
        if status_family == "pending":
            pending_lots += 1
        else:
            confirmed_lots += 1
        revenue += sale_price
        cost_of_goods += cost
        platform_fees += fees
        profit += sale_price - fees - cost
    summary = {
        "totalLots": lot_count,
        "pendingLots": pending_lots,
        "confirmedLots": confirmed_lots,
        "cancelledLots": cancelled_lots,
        "customerCount": len(buyers),
        "revenue": round(revenue, 2),
        "costOfGoods": round(cost_of_goods, 2),
        "platformFees": round(platform_fees, 2),
        "profit": round(profit, 2),
    }
    return {"lotCount": lot_count, "summary": summary, "lastSoldAt": last_sold_at}


_TIKTOK_GO_LIVE_EXPECTED_LOT_COUNTS = {
    79: 250,
    76: 52,
    77: 103,
    78: 285,
    68: 47,
    69: 100,
    71: 51,
    73: 200,
    80: 273,
}


def _pad_tiktok_go_live_rows(session, rows):
    rows = list(rows or [])
    session_id = int((session or {}).get("id") or 0)
    expected = int(_TIKTOK_GO_LIVE_EXPECTED_LOT_COUNTS.get(session_id) or 0)
    if expected <= len(rows):
        return rows
    existing = {str(row.get("lotNo") or "").strip() for row in rows}
    for lot_no in range(1, expected + 1):
        lot_key = str(lot_no)
        if lot_key in existing:
            continue
        rows.append({
            "lotNo": lot_key,
            "barcode": "",
            "productName": "",
            "notes": "",
            "sku": "",
            "cost": 0,
            "productId": None,
            "itemId": None,
            "matched": False,
            "statusLabel": "Missing lot",
            "statusFamily": "cancelled",
        })
        existing.add(lot_key)
        if len(rows) >= expected:
            break
    rows.sort(key=lambda row: int(str(row.get("lotNo") or "0").isdigit() and row.get("lotNo") or 0))
    return rows


def _serialize_tiktok_go_live_session(session, include_rows=True, live_api_enrich=True, auto_sheet_sync=True):
    if not session:
        return None
    session_status = str(session.get("status") or "").strip().lower()
    sequence = None
    match = re.search(r"Go Live Session\s*-?\s*(\d+)", str(session.get("name") or ""), re.I)
    if match:
        sequence = int(match.group(1))
    elif session.get("id"):
        sequence = int(session["id"])
    if not include_rows:
        quick = _summarize_tiktok_go_live_session_fast(session)
        summary = quick.get("summary") or {}
        return {
            "id": f"server-go-live-{session.get('id')}",
            "serverSessionId": int(session.get("id")),
            "showId": session.get("show_id"),
            "sequence": sequence,
            "displayName": session.get("name") or f"Go Live Session {sequence or session.get('id')}",
            "liveName": session.get("name"),
            "status": session.get("status"),
            "startedAt": session.get("started_at"),
            "endedAt": session.get("ended_at") or session.get("updated_at") or session.get("started_at"),
            "lotCount": int(quick.get("lotCount") or 0),
            "rows": [],
            "summary": summary,
            "lastSoldAt": quick.get("lastSoldAt") or "",
            "sheetSync": {},
            "backupJournalPath": _tiktok_go_live_journal_path(session.get("id")),
            "backupSnapshotPath": _tiktok_go_live_snapshot_path(session.get("id")),
            "rollingExportPath": _tiktok_go_live_operator_csv_path({"sequence": sequence, "serverSessionId": session.get("id")}),
            "summaryOnly": True,
        }
    sheet_sync_cfg = _get_tiktok_go_live_sheet_sync(session.get("id")) or {}
    manual_orders_only = bool(sheet_sync_cfg.get("manualOrdersOnly"))
    if session_status == "live" and live_api_enrich and auto_sheet_sync:
        try:
            _auto_sync_tiktok_go_live_sheet_session(session)
        except Exception:
            pass
    lots = list_company_lots(session_id=session["id"], limit=2000)
    rows = []
    for lot in sorted(lots, key=lambda value: int(str(value.get("lot_number") or "0").isdigit() and value.get("lot_number") or 0)):
        items = list_lot_items(lot["id"])
        rows.append(_tiktok_go_live_row_from_lot_items(lot, items))
    rows = _attach_tiktok_go_live_inventory_snapshot(rows)
    has_saved_orders = _tiktok_go_live_session_has_sale_orders(session)
    allow_recent_api_context = (
        _tiktok_go_live_recently_ended_without_saved_orders(session, has_saved_orders)
        and not manual_orders_only
    )
    if allow_recent_api_context and session_status in {"ended", "closed"} and not has_saved_orders:
        try:
            recovery_result = _materialize_tiktok_go_live_sale_orders_from_api(session, rows=rows)
            if recovery_result.get("imported"):
                has_saved_orders = _tiktok_go_live_session_has_sale_orders(session)
        except Exception:
            pass
    if allow_recent_api_context and live_api_enrich:
        rows = _enrich_tiktok_go_live_rows_with_pending_orders(session, rows)
    elif session_status == "live" and not manual_orders_only and live_api_enrich:
        # Only a currently live session may use fresh TikTok Shop API matches.
        # Historical open/draft sessions must stay pinned to saved sale orders so
        # recent Shop API rows cannot collide with reused lot numbers.
        rows = _enrich_tiktok_go_live_rows_with_pending_orders(session, rows)
        try:
            live_materialize_result = _materialize_tiktok_go_live_live_rows(session, rows)
            if live_materialize_result.get("imported") or live_materialize_result.get("updated"):
                has_saved_orders = _tiktok_go_live_session_has_sale_orders(session)
        except Exception:
            pass
        # Saved sale orders can exist for earlier rows while the show is still
        # running. Do not let that make the live view ignore fresh TikTok API
        # rows for later lots that have not been materialized yet.
        if has_saved_orders:
            rows = _enrich_tiktok_go_live_rows_with_sale_orders(session, rows)
        rows = _sync_tiktok_go_live_pending_inventory(session, rows)
    elif session_status in {"ended", "closed", "archived"} or has_saved_orders:
        rows = _enrich_tiktok_go_live_rows_with_sale_orders(session, rows)
    else:
        rows = _enrich_tiktok_go_live_rows_with_sale_orders(session, rows)
    rows = _attach_tiktok_go_live_inventory_snapshot(rows)
    rows = _pad_tiktok_go_live_rows(session, rows)
    summary = _summarize_tiktok_go_live_rows(rows)
    if session_status in {"live", "open", "draft"}:
        last_row = rows[-1] if rows else None
        last_has_barcode = bool(last_row and (str(last_row.get("barcode") or "").strip() or _is_tiktok_go_live_review_later_row(last_row)))
        if not rows or last_has_barcode:
            next_lot_no = str(len(rows) + 1)
            rows.append({
                "lotNo": next_lot_no,
                "barcode": "",
                "productName": "",
                "notes": "",
                "sku": "",
                "cost": 0,
                "productId": None,
                "itemId": None,
                "matched": False,
            })
    return {
        "id": f"server-go-live-{session.get('id')}",
        "serverSessionId": int(session.get("id")),
        "showId": session.get("show_id"),
        "sequence": sequence,
        "displayName": session.get("name") or f"Go Live Session {sequence or session.get('id')}",
        "liveName": session.get("name") or "",
        "endedAt": session.get("ended_at") or session.get("updated_at") or session.get("started_at"),
        "startedAt": session.get("started_at"),
        "status": session.get("status"),
        "lotCount": len(rows),
        "summary": summary,
        "rows": rows,
        "sheetSync": {
            **sheet_sync_cfg,
            **(_get_tiktok_go_live_sheet_sync_state(session.get("id")) or {}),
        },
        "backupJournalPath": _tiktok_go_live_journal_path(session.get("id")),
        "backupSnapshotPath": _tiktok_go_live_snapshot_path(session.get("id")),
        "rollingExportPath": _tiktok_go_live_operator_csv_path({"sequence": sequence, "serverSessionId": session.get("id")}),
    }


_TIKTOK_GO_LIVE_SESSION_CACHE = {}
_TIKTOK_GO_LIVE_SESSION_CACHE_TTL_SECONDS = 20


def _clear_tiktok_go_live_session_cache():
    _TIKTOK_GO_LIVE_SESSION_CACHE.clear()


def _list_tiktok_go_live_sessions_uncached(limit=80, include_rows=True):
    sessions = _list_tiktok_go_live_session_rows_fast(limit=int(limit or 80))
    return [_serialize_tiktok_go_live_session(session, include_rows=include_rows) for session in sessions]


def _list_tiktok_go_live_sessions(limit=80, include_rows=True):
    cache_limit = int(limit or 80)
    cache_key = (cache_limit, bool(include_rows))
    now = time.time()
    cached = _TIKTOK_GO_LIVE_SESSION_CACHE.get(cache_key)
    if cached and now - cached[0] <= _TIKTOK_GO_LIVE_SESSION_CACHE_TTL_SECONDS:
        return copy.deepcopy(cached[1])
    rows = _list_tiktok_go_live_sessions_uncached(cache_limit, include_rows=include_rows)
    _TIKTOK_GO_LIVE_SESSION_CACHE[cache_key] = (now, copy.deepcopy(rows))
    return rows


def _next_tiktok_go_live_sequence():
    max_sequence = 0
    for session in _list_tiktok_go_live_sessions_uncached(limit=300, include_rows=False):
        max_sequence = max(max_sequence, int(session.get("sequence") or 0))
    return max(max_sequence + 1, _TIKTOK_GO_LIVE_MIN_AUTO_SEQUENCE)


def _get_active_tiktok_go_live_session(live_api_enrich=True, auto_sheet_sync=False):
    sessions = [
        row for row in _list_tiktok_go_live_session_rows_fast(limit=300)
        if str(row.get("status") or "").strip().lower() == "live"
    ]
    sessions.sort(
        key=lambda row: (
            str(row.get("updated_at") or row.get("started_at") or ""),
            int(row.get("id") or 0),
        ),
        reverse=True,
    )
    if sessions:
        return _serialize_tiktok_go_live_session(
            sessions[0],
            live_api_enrich=live_api_enrich,
            auto_sheet_sync=auto_sheet_sync,
        )
    return None


def _tiktok_buyer_lookup_key(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lstrip("@").lower())


def _recent_tiktok_live_virtual_orders_for_username(username, existing_refs=None):
    target = _tiktok_buyer_lookup_key(username)
    if not target:
        return []
    existing_refs = {str(ref or "").strip().lower() for ref in (existing_refs or []) if str(ref or "").strip()}
    recent_sessions = [
        row for row in list_company_sessions(limit=30, exclude_test_data=False)
        if _is_tiktok_go_live_session_row(row)
    ][:8]
    if not recent_sessions:
        return []
    starts = [_tiktok_live_order_epoch(row.get("started_at")) for row in recent_sessions if row.get("started_at")]
    payload = {"page_size": 100, "max_pages": 20}
    if starts:
        payload["create_time_ge"] = max(0, min(starts) - 3600)
    try:
        api_lines = get_recent_tiktok_order_line_matches(payload, ttl_seconds=10).get("lines") or []
    except Exception:
        return []
    virtual_orders = []
    seen_refs = set(existing_refs)
    for session in recent_sessions:
        session_id = int(session.get("id") or 0)
        if session_id <= 0 or _tiktok_go_live_session_has_sale_orders(session):
            continue
        start_epoch = _tiktok_live_order_epoch(session.get("started_at"))
        ended_epoch = _tiktok_live_order_epoch(session.get("ended_at")) or int(time.time()) + 3600
        session_lines = []
        for line in api_lines:
            created_epoch = _tiktok_live_order_epoch(line.get("created_at") or line.get("paid_at") or line.get("updated_at"))
            if start_epoch and created_epoch and created_epoch < start_epoch:
                continue
            if ended_epoch and created_epoch and created_epoch > ended_epoch + 3600:
                continue
            session_lines.append(line)
        matches = _build_tiktok_go_live_pending_matches(
            session_lines,
            session_started_epoch=start_epoch,
            batch_overrides=_tiktok_live_batch_override_for_session(session),
        )
        lot_cache = {}
        for lot_no, match in matches.items():
            buyer_values = [
                match.get("buyer_username"),
                match.get("buyer_name"),
                match.get("recipient_name"),
                _tiktok_live_buyer_fallback(match),
            ]
            if target not in {_tiktok_buyer_lookup_key(value) for value in buyer_values if value}:
                continue
            order_id = str(match.get("order_id") or match.get("external_order_id") or "").strip()
            external_ref = f"tiktok_live:{order_id or 'api'}:{lot_no}"
            ref_key = external_ref.lower()
            if ref_key in seen_refs:
                continue
            seen_refs.add(ref_key)
            if lot_no not in lot_cache:
                lot = get_company_lot_by_number(session_id, lot_no)
                lot_cache[lot_no] = list_lot_items(lot["id"]) if lot else []
            items = lot_cache.get(lot_no) or []
            sale_price = float(match.get("total_price") or match.get("sale_price") or match.get("unit_price") or 0)
            line_count = max(1, len(items))
            unit_split = round(sale_price / line_count, 4)
            lines = []
            for item in items:
                qty = float(item.get("qty_snapshot") or 1)
                lines.append({
                    "id": f"live-api-{session_id}-{lot_no}-{item.get('id')}",
                    "product_id": item.get("product_id"),
                    "product_id_name": item.get("linked_product_name") or item.get("product_name"),
                    "product_name": item.get("linked_product_name") or item.get("product_name"),
                    "name": item.get("linked_product_name") or item.get("product_name"),
                    "barcode": item.get("barcode"),
                    "sku": item.get("sku"),
                    "qty": qty,
                    "product_uom_qty": qty,
                    "unit_price": unit_split,
                    "price_unit": unit_split,
                    "subtotal": unit_split * qty,
                    "price_subtotal": unit_split * qty,
                    "unit_cost": float(item.get("unit_cost") or 0),
                    "cost_price": float(item.get("unit_cost") or 0),
                    "lot_number": lot_no,
                })
            if not lines:
                lines = [{
                    "id": f"live-api-{session_id}-{lot_no}",
                    "product_name": match.get("product_name") or f"TikTok LIVE lot {lot_no}",
                    "name": match.get("product_name") or f"TikTok LIVE lot {lot_no}",
                    "qty": float(match.get("quantity") or 1),
                    "product_uom_qty": float(match.get("quantity") or 1),
                    "unit_price": sale_price,
                    "price_unit": sale_price,
                    "subtotal": sale_price,
                    "price_subtotal": sale_price,
                    "unit_cost": 0,
                    "cost_price": 0,
                    "lot_number": lot_no,
                }]
            status_family = str(match.get("status_family") or "").strip().lower()
            buyer_display = next((str(value).strip() for value in buyer_values if str(value or "").strip()), target)
            ordered_at = _tiktok_live_iso_datetime(match.get("created_at"))
            virtual_orders.append({
                "id": f"live-api-{session_id}-{lot_no}",
                "order_number": f"TikTok LIVE Lot {lot_no}",
                "name": f"TikTok LIVE Lot {lot_no}",
                "session_id": session_id,
                "session_name": session.get("name"),
                "whatnot_session_id": session_id,
                "whatnot_session_id_name": session.get("name"),
                "whatnot_buyer_username": buyer_display,
                "order_source": "tiktok_live",
                "external_order_ref": external_ref,
                "state": "cancel" if status_family == "cancelled" else "sale",
                "fulfillment_status": "cancelled" if status_family == "cancelled" else "pending",
                "payment_status": "paid" if status_family != "cancelled" else "unpaid",
                "subtotal": sale_price,
                "total_amount": sale_price,
                "amount_total": sale_price,
                "ordered_at": ordered_at,
                "date_order": ordered_at,
                "created_at": ordered_at,
                "updated_at": _tiktok_live_iso_datetime(match.get("updated_at") or match.get("created_at")),
                "notes": f"Status: {match.get('order_status') or ''} | Seller SKU: {match.get('seller_sku') or ''} | Lot: {lot_no}",
                "line_count": len(lines),
                "lines": lines,
                "virtual": True,
            })
    virtual_orders.sort(key=lambda row: str(row.get("ordered_at") or ""), reverse=True)
    return virtual_orders


def _build_tiktok_live_label_product_index(session_id=None, lot_map_csv_text=""):
    index = {}
    buyer_groups = {}
    order_sessions = {}
    requested_session_id = int(session_id) if session_id else None
    lot_number_by_id = {}

    def entry(lot_number, product_names, product_items=None):
        return {
            "lot_number": str(lot_number or "").strip(),
            "product_names": [str(name or "").strip() for name in (product_names or []) if str(name or "").strip()],
            "product_items": [
                {
                    "lot_number": str((item or {}).get("lot_number") or lot_number or "").strip(),
                    "product_name": str((item or {}).get("product_name") or "").strip(),
                    "barcode": str((item or {}).get("barcode") or "").strip(),
                    "sku": str((item or {}).get("sku") or "").strip(),
                    "product_id": (item or {}).get("product_id"),
                    "qty": float((item or {}).get("qty") or 1),
                }
                for item in (product_items or [])
                if str((item or {}).get("product_name") or "").strip()
            ],
        }

    def set_entry(key, lot_number, product_names, *, overwrite=False, product_items=None):
        if not product_names:
            return
        if overwrite or key not in index:
            index[key] = entry(lot_number, product_names, product_items=product_items)

    def buyer_key(value):
        return _normalize_tiktok_buyer_key(value)

    def add_buyer_group(value, product_items):
        key = buyer_key(value)
        if not key or not product_items:
            return
        group = buyer_groups.setdefault(key, [])
        for item in product_items:
            product_name = str((item or {}).get("product_name") or "").strip()
            if not product_name:
                continue
            group.append({
                "lot_number": str((item or {}).get("lot_number") or "").strip(),
                "product_name": product_name,
                "barcode": str((item or {}).get("barcode") or "").strip(),
                "sku": str((item or {}).get("sku") or "").strip(),
                "product_id": (item or {}).get("product_id"),
                "qty": float((item or {}).get("qty") or 1),
            })

    def lot_number_for_line(line, order_session_id=None):
        lot_id = line.get("lot_id") if isinstance(line, dict) else None
        if lot_id is None:
            return ""
        try:
            lot_id_int = int(lot_id)
        except Exception:
            return ""
        if lot_id_int not in lot_number_by_id:
            lot_number_by_id[lot_id_int] = ""
            try:
                if order_session_id:
                    for lot in list_company_lots(session_id=order_session_id, limit=5000) or []:
                        try:
                            mapped_id = int(lot.get("id"))
                        except Exception:
                            continue
                        lot_number_by_id[mapped_id] = str(lot.get("lot_number") or "").strip()
            except Exception:
                pass
        return lot_number_by_id.get(lot_id_int) or ""

    if str(lot_map_csv_text or "").strip():
        products = list_products(active_only=False, low_stock_only=False)
        lot_map = _build_tiktok_live_lot_map(lot_map_csv_text, products)
        for lot_number, lot_match in lot_map.items():
            product_names = []
            product = lot_match.get("product") if lot_match else None
            if product and str(product.get("name") or "").strip():
                product_names.append(str(product.get("name")).strip())
            elif lot_match and str(lot_match.get("product_name") or "").strip():
                product_names.append(str(lot_match.get("product_name")).strip())
            if product_names:
                set_entry(("", str(lot_number)), lot_number, product_names, overwrite=True)
    orders = list_sale_orders(order_source="tiktok_live")
    order_ids = [
        int(order.get("id"))
        for order in orders
        if str(order.get("id") or "").isdigit()
        and not str(order.get("external_order_ref") or "").startswith("archived_duplicate:")
        and not str(order.get("status") or "").strip().lower().startswith("archived_duplicate")
    ]
    line_rows = list_sale_order_lines_bulk(order_ids) if order_ids else []
    lines_by_order = {}
    for line in line_rows or []:
        try:
            line_order_id = int(line.get("sale_order_id"))
        except Exception:
            continue
        lines_by_order.setdefault(line_order_id, []).append(line)
    for order in orders:
        ref = str(order.get("external_order_ref") or "")
        if str(order.get("status") or "").strip().lower().startswith("archived_duplicate") or ref.startswith("archived_duplicate:"):
            continue
        order_session_id = int(order.get("session_id") or 0) if order.get("session_id") else None
        if requested_session_id and order_session_id and order_session_id != requested_session_id:
            continue
        match = re.search(r"tiktok_live:([^:]+):([^:]+)", ref)
        if not match:
            continue
        order_id, lot_number = match.group(1), match.group(2)
        if order_session_id:
            order_sessions[order_id] = order_session_id
        lines = lines_by_order.get(int(order["id"])) or []
        product_items = []
        product_names = [
            str(line.get("description") or "").strip()
            for line in lines
            if str(line.get("description") or "").strip()
        ]
        for line in lines:
            description = str(line.get("description") or "").strip()
            if not description:
                continue
            product_items.append({
                "lot_number": lot_number_for_line(line, order_session_id=order_session_id) or lot_number,
                "product_name": description,
                "barcode": line.get("barcode") or "",
                "sku": line.get("sku") or "",
                "product_id": line.get("product_id"),
                "qty": float(line.get("qty") or line.get("product_uom_qty") or 1),
            })
        if not product_names:
            notes_match = re.search(r"Product:\s*([^|]+)", str(order.get("notes") or ""), re.I)
            if notes_match:
                product_names = [notes_match.group(1).strip()]
        if not product_names:
            continue
        for buyer_value in (
            order.get("whatnot_buyer_username"),
            order.get("buyer_username"),
            order.get("buyer_name"),
            order.get("customer_name"),
            order.get("customer_username"),
            order.get("recipient_name"),
        ):
            add_buyer_group(buyer_value, product_items)
        set_entry((order_id, lot_number), lot_number, product_names, overwrite=True, product_items=product_items)
        set_entry((order_id, ""), lot_number, product_names, product_items=product_items)
        notes_text = str(order.get("notes") or "")
        tracking_match = re.search(r"\bTracking\s+ID:\s*([^|]+)", notes_text, re.I)
        tracking_number = tracking_match.group(1).strip() if tracking_match else ""
        package_match = re.search(r"\bPackage\s+ID:\s*([^|]+)", notes_text, re.I)
        package_id = package_match.group(1).strip() if package_match else ""
        raw_lot_match = re.search(
            r"Batch\s+\d+\s+lot\s+([A-Za-z0-9._-]+)\s+mapped\s+to\s+Session\s+lot\s+([A-Za-z0-9._-]+)",
            notes_text,
            re.I,
        )
        if raw_lot_match and raw_lot_match.group(2).strip() == str(lot_number).strip():
            raw_lot = raw_lot_match.group(1).strip()
            set_entry((order_id, raw_lot), lot_number, product_names, product_items=product_items)
            if tracking_number:
                set_entry(("tracking", tracking_number, raw_lot), lot_number, product_names, overwrite=True, product_items=product_items)
            if package_id:
                set_entry(("package", package_id, raw_lot), lot_number, product_names, overwrite=True, product_items=product_items)
        variant_match = re.search(r"\bVariant:\s*([A-Za-z0-9._-]+)", notes_text, re.I)
        if variant_match:
            variant_lot = variant_match.group(1).strip()
            set_entry((order_id, variant_lot), lot_number, product_names, product_items=product_items)
            if tracking_number:
                set_entry(("tracking", tracking_number, variant_lot), lot_number, product_names, overwrite=True, product_items=product_items)
            if package_id:
                set_entry(("package", package_id, variant_lot), lot_number, product_names, overwrite=True, product_items=product_items)
    session_ids = [requested_session_id] if requested_session_id else order_sessions.values()
    lot_products_by_session = _fetch_tiktok_live_session_lot_products(session_ids)
    if requested_session_id:
        for lot_number, product_names in lot_products_by_session.get(requested_session_id, {}).items():
            # Raw TikTok labels carry Seller SKU as the lot number. This lets
            # label enrichment work even when the CSV row is a duplicate or the
            # original order record was imported before session linking existed.
            set_entry(("", str(lot_number)), lot_number, product_names)
    for order_id, session_id in order_sessions.items():
        for lot_number, product_names in lot_products_by_session.get(session_id, {}).items():
            set_entry((order_id, str(lot_number)), lot_number, product_names)
    for buyer, product_items in buyer_groups.items():
        product_names = [str(item.get("product_name") or "").strip() for item in product_items if str(item.get("product_name") or "").strip()]
        set_entry(("buyer", buyer), "", product_names, overwrite=True, product_items=product_items)
    return index


def _tiktok_label_index_names(entry):
    if isinstance(entry, dict):
        return entry.get("product_names") or []
    return entry or []


def _tiktok_label_index_items(entry, fallback_lot=""):
    if not isinstance(entry, dict):
        return [(str(fallback_lot or "").strip(), name) for name in (entry or [])]
    items = []
    for item in entry.get("product_items") or []:
        product_name = str((item or {}).get("product_name") or "").strip()
        if product_name:
            items.append((str((item or {}).get("lot_number") or fallback_lot or "").strip(), product_name))
    if items:
        return items
    lot_number = str(entry.get("lot_number") or fallback_lot or "").strip()
    return [(lot_number, name) for name in (entry.get("product_names") or [])]


def _tiktok_label_index_lot(entry, fallback=""):
    if isinstance(entry, dict):
        return str(entry.get("lot_number") or fallback or "").strip()
    return str(fallback or "").strip()


def _tiktok_label_batch_final_lot(listing_name, seller_sku, batch_overrides=None):
    # TikTok labels carry the listing-local Seller SKU. Live listings reuse
    # Seller SKU 1-300 for every batch, while our operational lot numbers are
    # global: batch 1 => 1-300, batch 2 => 301-600, batch 3 => 601-900.
    batch_number = _tiktok_live_batch_number_from_title(listing_name)
    raw_lot = _tiktok_live_lot_number_from_seller_sku(seller_sku)
    if not raw_lot:
        return ""
    effective_batch = _tiktok_live_apply_batch_override(batch_number or 1, batch_overrides)
    return str(((int(effective_batch) - 1) * 300) + int(raw_lot))


def _packing_scanner_index_path():
    return os.path.join(os.path.dirname(DB_PATH), "packing_scanner_index.json")


def _packing_scanner_events_path():
    return os.path.join(os.path.dirname(DB_PATH), "packing_scanner_events.jsonl")


def _normalize_tracking_key(value):
    digits = re.sub(r"\D+", "", str(value or ""))
    if not digits:
        return ""
    direct = re.match(r"^(9[2345]\d{20})(?:\d+)?$", digits)
    if direct:
        return direct.group(1)
    # USPS IMpb labels can scan as 420 + destination ZIP + tracking number.
    embedded = re.search(r"(?:^|420\d{5,9})(9[2345]\d{20})(?:\d+)?$", digits)
    if embedded:
        return embedded.group(1)
    fallback = re.search(r"(9[2345]\d{20})", digits)
    if fallback:
        return fallback.group(1)
    return digits


def _normalize_product_lookup_key(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _packing_scanner_product_lookup():
    cached = getattr(_packing_scanner_product_lookup, "_cached", None)
    if isinstance(cached, dict):
        return cached
    lookup = {}
    try:
        for product in list_products(active_only=False, low_stock_only=False) or []:
            key = _normalize_product_lookup_key(product.get("name"))
            if key and key not in lookup:
                lookup[key] = product
    except Exception:
        lookup = {}
    _packing_scanner_product_lookup._cached = lookup
    return lookup


def _packing_scanner_enrich_item(item):
    next_item = dict(item or {})
    if next_item.get("barcode") or next_item.get("sku") or next_item.get("product_id"):
        return next_item
    product = _packing_scanner_product_lookup().get(_normalize_product_lookup_key(next_item.get("product_name")))
    if product:
        next_item["barcode"] = str(product.get("barcode") or "").strip()
        next_item["sku"] = str(product.get("sku") or "").strip()
        next_item["product_id"] = product.get("id")
    return next_item


def _load_packing_scanner_index():
    path = _packing_scanner_index_path()
    if not os.path.exists(path):
        return {"records": {}}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("records"), dict):
            return data
    except Exception:
        pass
    return {"records": {}}


def _save_packing_scanner_index(data):
    path = _packing_scanner_index_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _packing_scanner_dedupe_items(items):
    merged = {}
    for raw_item in items or []:
        item = _packing_scanner_enrich_item(raw_item)
        product_name = str(item.get("product_name") or item.get("name") or "").strip()
        lot_number = str(item.get("lot_number") or item.get("lot") or "").strip()
        barcode = str(item.get("barcode") or "").strip()
        sku = str(item.get("sku") or "").strip()
        if not product_name and not barcode and not sku:
            continue
        key = (lot_number, barcode, sku, product_name)
        current = merged.setdefault(key, {
            "lot_number": lot_number,
            "product_name": product_name,
            "barcode": barcode,
            "sku": sku,
            "product_id": item.get("product_id"),
            "qty_required": 0,
        })
        try:
            current["qty_required"] += max(1, int(float(item.get("qty_required") or item.get("qty") or 1)))
        except Exception:
            current["qty_required"] += 1
    return list(merged.values())


def _packing_scanner_items_from_index_entry(entry, fallback_lot=""):
    if isinstance(entry, dict) and entry.get("product_items"):
        return _packing_scanner_dedupe_items([
            {
                "lot_number": str(item.get("lot_number") or fallback_lot or "").strip(),
                "product_name": str(item.get("product_name") or "").strip(),
                "barcode": str(item.get("barcode") or "").strip(),
                "sku": str(item.get("sku") or "").strip(),
                "product_id": item.get("product_id"),
                "qty": item.get("qty") or 1,
            }
            for item in (entry.get("product_items") or [])
        ])
    return _packing_scanner_dedupe_items([
        {"lot_number": lot_number, "product_name": product_name, "qty": 1}
        for lot_number, product_name in _tiktok_label_index_items(entry, fallback_lot)
    ])


def _upsert_packing_scanner_records(records):
    normalized = []
    for record in records or []:
        tracking_key = _normalize_tracking_key(record.get("tracking_number"))
        if not tracking_key:
            continue
        items = _packing_scanner_dedupe_items(record.get("items") or [])
        if not items:
            continue
        normalized.append({
            "tracking_number": str(record.get("tracking_number") or "").strip(),
            "tracking_key": tracking_key,
            "order_id": str(record.get("order_id") or "").strip(),
            "buyer": str(record.get("buyer") or "").strip(),
            "session_id": record.get("session_id"),
            "session_name": str(record.get("session_name") or "").strip(),
            "packing_session_key": str(record.get("packing_session_key") or "").strip(),
            "source": str(record.get("source") or "label_pdf").strip(),
            "items": items,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    if not normalized:
        return
    data = _load_packing_scanner_index()
    store = data.setdefault("records", {})
    for record in normalized:
        store[record["tracking_key"]] = record
    _save_packing_scanner_index(data)


def _packing_scanner_order_from_sale_order(order):
    if not order:
        return None
    lines = list_sale_order_lines(int(order["id"])) or []
    items = []
    for line in lines:
        product_name = str(line.get("product_name") or line.get("description") or line.get("name") or "").strip()
        items.append({
            "line_id": line.get("id"),
            "product_id": line.get("product_id"),
            "lot_number": str(line.get("lot_number") or "").strip(),
            "product_name": product_name,
            "barcode": str(line.get("barcode") or "").strip(),
            "sku": str(line.get("sku") or "").strip(),
            "qty_required": max(1, int(float(line.get("qty") or line.get("product_uom_qty") or 1))),
            "unit_price": float(line.get("unit_price") or line.get("price_unit") or 0),
            "unit_cost": float(line.get("unit_cost") or 0),
        })
    return {
        "order_id": order.get("id"),
        "order_number": order.get("order_number"),
        "external_order_ref": order.get("external_order_ref"),
        "tracking_number": order.get("tracking_number"),
        "buyer": order.get("display_name") or order.get("whatnot_buyer_username") or order.get("buyer_username") or "",
        "session_id": order.get("session_id"),
        "session_name": order.get("session_name"),
        "order_source": order.get("order_source"),
        "payment_status": order.get("payment_status"),
        "fulfillment_status": order.get("fulfillment_status"),
        "items": _packing_scanner_dedupe_items(items),
        "source": "sale_order",
    }


def _lookup_packing_scanner_order(tracking_number):
    tracking_key = _normalize_tracking_key(tracking_number)
    if not tracking_key:
        return None
    cached = (_load_packing_scanner_index().get("records") or {}).get(tracking_key)
    if cached and cached.get("items"):
        return {
            "order_id": cached.get("order_id"),
            "order_number": cached.get("order_id"),
            "external_order_ref": cached.get("order_id"),
            "tracking_number": cached.get("tracking_number") or tracking_number,
            "buyer": cached.get("buyer") or "",
            "session_id": cached.get("session_id"),
            "session_name": cached.get("session_name") or "",
            "order_source": "tiktok_live",
            "payment_status": "",
            "fulfillment_status": "",
            "items": cached.get("items") or [],
            "source": cached.get("source") or "label_pdf",
        }

    for source in ("tiktok_live", "tiktok_shop", None):
        rows = list_sale_orders(q=tracking_key, order_source=source) if source else list_sale_orders(q=tracking_key)
        for order in rows or []:
            if _normalize_tracking_key(order.get("tracking_number")) == tracking_key or tracking_key in _normalize_tracking_key(order.get("notes")):
                return _packing_scanner_order_from_sale_order(order)
    return None


def _packing_scanner_completed_tracking_keys():
    path = _packing_scanner_events_path()
    completed = set()
    if not os.path.exists(path):
        return completed
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if str(row.get("event_type") or "").strip() != "order_completed":
                    continue
                tracking_key = _normalize_tracking_key(row.get("tracking_key") or row.get("tracking_number"))
                if tracking_key:
                    completed.add(tracking_key)
    except Exception:
        return completed
    return completed


def _packing_scanner_session_summary(session_id=None):
    data = _load_packing_scanner_index()
    records = list((data.get("records") or {}).values())
    if session_id:
        requested_session_id = str(session_id).strip()
    else:
        session_ids = sorted(
            {
                str(record.get("session_id") or "").strip()
                for record in records
                if str(record.get("session_id") or "").strip()
            },
            key=lambda value: int(value) if value.isdigit() else -1,
            reverse=True,
        )
        requested_session_id = session_ids[0] if session_ids else ""

    if requested_session_id:
        filtered = [
            record for record in records
            if str(record.get("session_id") or "").strip() == requested_session_id
        ]
    else:
        filtered = records

    completed_keys = _packing_scanner_completed_tracking_keys()
    rows = []
    total_items = 0
    packed_items = 0
    session_name = ""
    for record in filtered:
        items = record.get("items") or []
        item_count = sum(max(1, int(float(item.get("qty_required") or item.get("qty") or 1))) for item in items)
        tracking_key = _normalize_tracking_key(record.get("tracking_key") or record.get("tracking_number"))
        packed = tracking_key in completed_keys
        total_items += item_count
        if packed:
            packed_items += item_count
        if not session_name and record.get("session_name"):
            session_name = record.get("session_name")
        rows.append({
            "tracking_number": record.get("tracking_number") or "",
            "tracking_key": tracking_key,
            "order_id": record.get("order_id") or "",
            "buyer": record.get("buyer") or "",
            "item_count": item_count,
            "packed": packed,
            "items_preview": [
                {
                    "lot_number": item.get("lot_number") or "",
                    "product_name": item.get("product_name") or "",
                    "barcode": item.get("barcode") or "",
                    "qty_required": item.get("qty_required") or item.get("qty") or 1,
                }
                for item in items[:4]
            ],
            "updated_at": record.get("updated_at") or "",
        })

    rows.sort(key=lambda row: (row["packed"], row["buyer"].lower(), row["tracking_number"]))
    if requested_session_id and not session_name:
        try:
            session = get_company_session(int(requested_session_id))
            session_name = str((session or {}).get("name") or "")
        except Exception:
            session_name = ""
    return {
        "session_id": requested_session_id,
        "session_name": session_name,
        "total_labels": len(rows),
        "packed_labels": sum(1 for row in rows if row.get("packed")),
        "open_labels": sum(1 for row in rows if not row.get("packed")),
        "total_items": total_items,
        "packed_items": packed_items,
        "open_items": max(0, total_items - packed_items),
        "records": rows[:500],
    }


def _append_packing_scanner_event(payload):
    event = dict(payload or {})
    tracking_number = str(event.get("tracking_number") or "").strip()
    if not tracking_number:
        raise ValueError("tracking_number required")
    event["tracking_number"] = tracking_number
    event["tracking_key"] = _normalize_tracking_key(tracking_number)
    event["event_type"] = str(event.get("event_type") or "scan").strip() or "scan"
    event["created_at"] = datetime.now(timezone.utc).isoformat()
    path = _packing_scanner_events_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return event


def _list_packing_scanner_events(tracking_number, limit=200):
    tracking_key = _normalize_tracking_key(tracking_number)
    if not tracking_key:
        return []
    path = _packing_scanner_events_path()
    if not os.path.exists(path):
        return []
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if _normalize_tracking_key(row.get("tracking_number") or row.get("tracking_key")) == tracking_key:
                    rows.append(row)
    except Exception:
        return []
    return rows[-max(1, min(int(limit or 200), 1000)):]


def _wrap_label_text(text, max_chars=36):
    words = str(text or "").split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or ["—"]


def _wrap_label_text_to_width(text, max_width, font_name="Helvetica-Bold", font_size=10):
    from reportlab.pdfbase.pdfmetrics import stringWidth

    words = str(text or "").split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and stringWidth(candidate, font_name, font_size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or ["—"]


def _fit_label_lines(text, max_width, *, max_lines=2, preferred_font_size=8.2, min_font_size=6.1, font_name="Helvetica-Bold"):
    font_size = preferred_font_size
    while font_size >= min_font_size:
        lines = _wrap_label_text_to_width(
            text,
            max_width=max_width,
            font_name=font_name,
            font_size=font_size,
        )
        visible_lines, hidden_lines = _split_wrapped_lines_for_space(lines, max_lines)
        if not hidden_lines:
            return visible_lines, font_size
        font_size -= 0.3
    lines = _wrap_label_text_to_width(
        text,
        max_width=max_width,
        font_name=font_name,
        font_size=min_font_size,
    )
    visible_lines, hidden_lines = _split_wrapped_lines_for_space(lines, max_lines)
    if hidden_lines and visible_lines:
        last = visible_lines[-1]
        if len(last) > 3:
            visible_lines[-1] = last[:-3].rstrip(" ,.-") + "..."
    return visible_lines, min_font_size


def _normalize_pack_label_product_name(product_name):
    text = str(product_name or "").strip()
    if not text:
        return "—"
    text = re.sub(r"\bEau de Parfum\b", "", text, flags=re.I)
    text = re.sub(r"\bExtrait de Parfum\b", "", text, flags=re.I)
    text = re.sub(r"\bEau de Toilette\b", "", text, flags=re.I)
    text = re.sub(r"\bEDP Spray\b", "", text, flags=re.I)
    text = re.sub(r"\bEDT Spray\b", "", text, flags=re.I)
    text = re.sub(r"\bEDP\b", "", text, flags=re.I)
    text = re.sub(r"\bEDT\b", "", text, flags=re.I)
    text = re.sub(r"\bParfum Spray\b", "Spray", text, flags=re.I)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([()])", r"\1", text)
    return text.strip(" -") or str(product_name or "—").strip()


def _format_label_lot(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.upper().startswith("L"):
        return raw.upper()
    return f"L{raw}"


def _split_wrapped_lines_for_space(lines, max_lines):
    safe_lines = [str(line or "").strip() for line in (lines or []) if str(line or "").strip()]
    if max_lines <= 0:
        return [], safe_lines
    if len(safe_lines) <= max_lines:
        return safe_lines, []
    return safe_lines[:max_lines], safe_lines[max_lines:]


def _flatten_tiktok_pack_items(packed_items):
    flat = []
    seen = set()
    for seller_sku, product_names in packed_items or []:
        for product_name in product_names or []:
            key = (str(seller_sku or "").strip(), str(product_name or "").strip())
            if not key[1] or key in seen:
                continue
            seen.add(key)
            flat.append(key)
    return flat


_TIKTOK_LABEL_CONTINUATION_THRESHOLD = 8
_TIKTOK_LABEL_WATERMARK_PATHS = (
    "/home/cybertechna/Downloads/Gemini_Generated_Image_htnrxhtnrxhtnrxh-removebg-preview.png",
)
_TIKTOK_SHOP_PROMO_URL = "https://shop.tiktok.com/us/store/ynfdeal/7495470678804564869?source=product_detail&enter_method=pdp_seller_name&first_entrance=google&first_entrance_position=search&first_entrance_tt_scene=seo"


def _resolve_tiktok_label_watermark_path():
    for path in _TIKTOK_LABEL_WATERMARK_PATHS:
        if path and os.path.exists(path):
            return path
    return None


def _draw_tiktok_pack_watermark(pdf, width, *, pack_box_top_y):
    watermark_path = _resolve_tiktok_label_watermark_path()
    if not watermark_path:
        return
    try:
        from reportlab.lib.utils import ImageReader
    except Exception:
        return
    try:
        image = ImageReader(watermark_path)
        image_width, image_height = image.getSize()
    except Exception:
        return
    if not image_width or not image_height:
        return

    max_width = min(width * 0.34, 96)
    max_height = 88
    scale = min(max_width / float(image_width), max_height / float(image_height))
    draw_width = max(1, image_width * scale)
    draw_height = max(1, image_height * scale)
    center_x = width / 2.0
    center_y = min(pack_box_top_y + 52, 224)
    draw_x = center_x - (draw_width / 2.0)
    draw_y = center_y - (draw_height / 2.0)

    pdf.saveState()
    try:
        if hasattr(pdf, "setFillAlpha"):
            pdf.setFillAlpha(0.13)
    except Exception:
        pass
    try:
        pdf.drawImage(image, draw_x, draw_y, width=draw_width, height=draw_height, mask='auto', preserveAspectRatio=True)
    finally:
        pdf.restoreState()


def _tiktok_shop_qr_card_dims(size=54, compact=False):
    if compact:
        return size + 98, max(size + 14, 58)
    return size + 108, max(size + 18, 70)


def _draw_tiktok_shop_qr_card(pdf, x, y, *, size=54, compact=False):
    try:
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderPDF
    except Exception:
        return
    try:
        qr_widget = QrCodeWidget(_TIKTOK_SHOP_PROMO_URL)
        bounds = qr_widget.getBounds()
        qr_width = max(1, bounds[2] - bounds[0])
        qr_height = max(1, bounds[3] - bounds[1])
        drawing = Drawing(size, size, transform=[size / qr_width, 0, 0, size / qr_height, 0, 0])
        drawing.add(qr_widget)
    except Exception:
        return

    card_width, card_height = _tiktok_shop_qr_card_dims(size=size, compact=compact)
    pdf.saveState()
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setStrokeColorRGB(0.84, 0.87, 0.93)
    pdf.roundRect(x, y, card_width, card_height, 6, stroke=1, fill=1)
    qr_x = x + 8
    qr_y = y + (card_height - size) / 2.0
    renderPDF.draw(drawing, pdf, qr_x, qr_y)
    text_x = qr_x + size + 16
    text_y = y + card_height - (15 if compact else 17)
    pdf.setFillColorRGB(0.06, 0.09, 0.16)
    pdf.setFont("Helvetica-Bold", 7.6 if compact else 8.2)
    pdf.drawString(text_x, text_y, "Follow + shop more")
    pdf.setFillColorRGB(0.35, 0.39, 0.45)
    pdf.setFont("Helvetica", 6.2 if compact else 6.6)
    pdf.drawString(text_x, text_y - 10, "Scan for more fragrances")
    pdf.drawString(text_x, text_y - 18, "@ynfdeal on TikTok Shop")
    pdf.restoreState()


def _draw_tiktok_product_table_replacements(pdf, width, height, display_items):
    if not display_items:
        return
    row_count = len(display_items)
    # The TikTok packing-slip table is consistent on the label PDFs: row one is
    # just below the header, with roughly 18-19pt row height.
    row_height = 18.4 if row_count >= 8 else 24
    table_top = height - 72
    product_x = 10
    product_width = max(92, min(112, width * 0.37))
    for idx, (seller_sku, product_name) in enumerate(display_items):
        row_y = table_top - (idx * row_height)
        # Do not render into the lower buyer/order summary zone.
        if row_y < 146:
            break
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(product_x - 2, row_y - row_height + 1, product_width + 4, row_height - 1, stroke=0, fill=1)
        pdf.setFillColorRGB(0.02, 0.03, 0.05)
        if row_count >= 8:
            font_size = 5.3
            line_gap = 5.4
            max_chars = 19
            max_lines = 2
        else:
            font_size = 5.6
            line_gap = 5.8
            max_chars = 20
            max_lines = 2
        pdf.setFont("Helvetica-Bold", font_size)
        label = f"Lot {seller_sku} - {product_name}" if seller_sku else product_name
        text_y = row_y - 7
        wrapped = _wrap_label_text(label, max_chars=max_chars)
        visible_lines, hidden_lines = _split_wrapped_lines_for_space(wrapped, max_lines)
        if hidden_lines and visible_lines:
            visible_lines[-1] = visible_lines[-1].rstrip(" ,.-")
            if len(visible_lines[-1]) > 3:
                visible_lines[-1] = visible_lines[-1][:-3].rstrip(" ,.-") + "..."
        for line in visible_lines:
            pdf.drawString(product_x, text_y, line)
            text_y -= line_gap


def _draw_whatnot_product_replacements(pdf, width, height, items):
    if not items:
        return
    # Whatnot packing slips have a stable table layout:
    # qty column on the far left, description block in the middle-left,
    # order attributes to the right, subtotal on the far right.
    # We only paint over the description block so the order id / subtotal remain.
    item_count = max(len(items), 1)
    # These Whatnot combined packing slips use a compact 4-column layout on a
    # 288x432 page. The description rows start much higher than our earlier
    # estimate, so anchor from the observed table position instead of the
    # generic label layout.
    table_top = height - 108
    table_bottom = 66
    row_height = max(36, min(50, (table_top - table_bottom) / item_count))
    redact_x = 22
    redact_width = 116
    # Wipe the whole description column body once so leftover listing copy
    # does not peek through between rows on compact Whatnot slips.
    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(redact_x, table_bottom - 2, redact_width, (table_top - table_bottom) + 18, stroke=0, fill=1)
    for idx, item in enumerate(items):
        row_top = table_top - (idx * row_height)
        row_bottom = row_top - row_height + 2
        box_height = max(34, row_height - 3)
        # Add a slightly oversized row wipe so each product block remains crisp.
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(redact_x - 1, row_bottom - 1, redact_width + 2, box_height + 2, stroke=0, fill=1)

        product_name = str(item.get("product_name") or item.get("whatnot_name") or "Product not matched").strip()
        subtitle_parts = []
        lot_number = str(item.get("lot_number") or "").strip()
        if lot_number:
            subtitle_parts.append(f"Lot #{lot_number}")
        barcode = str(item.get("barcode") or "").strip()
        if barcode:
            subtitle_parts.append(barcode)
        sku = str(item.get("sku") or "").strip()
        if sku and sku != barcode:
            subtitle_parts.append(sku)
        subtitle = " · ".join(subtitle_parts)

        pdf.setFillColorRGB(0.02, 0.03, 0.05)
        pdf.setFont("Helvetica-Bold", 8.6)
        text_y = row_top - 12
        for line in _wrap_label_text(product_name, max_chars=18)[:3]:
            pdf.drawString(redact_x + 6, text_y, line)
            text_y -= 8

        if subtitle:
            pdf.setFont("Helvetica", 6.3)
            pdf.setFillColorRGB(0.35, 0.39, 0.45)
            pdf.drawString(redact_x + 6, max(row_bottom + 4, text_y - 1), subtitle[:36])


def _build_tiktok_pack_continuation_page(width, height, identity, display_items, source_text, *, total_items=None, start_index=0):
    from PyPDF2 import PdfReader
    from reportlab.pdfgen import canvas

    buyer_match = re.search(r"Buyer\s+ID:\s*([^\n]+)", source_text or "", re.I)
    nickname_match = re.search(r"Buyer\s+Nickname:\s*([^\n]+)", source_text or "", re.I)
    tracking_number = (
        str(identity.get("tracking_number") or "").strip()
        or _extract_tiktok_tracking_number(source_text)
        or "—"
    )

    overlay = io.BytesIO()
    pdf = canvas.Canvas(overlay, pagesize=(width, height))
    margin = 16
    cursor = height - 24
    pdf.setFillColorRGB(0.02, 0.03, 0.05)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin, cursor, "FULL PACK LIST")
    pdf.setFont("Helvetica", 6.8)
    pdf.setFillColorRGB(0.35, 0.39, 0.45)
    if total_items and int(total_items) > len(display_items):
        summary_label = f"Items {int(start_index) + 1}-{int(start_index) + len(display_items)} of {int(total_items)}"
    else:
        summary_label = f"{len(display_items)} items"
    pdf.drawRightString(width - margin, cursor, summary_label)
    cursor -= 15

    pdf.setFont("Helvetica", 7)
    meta = [
        f"Order ID: {identity.get('order_id') or '—'}",
        f"Buyer: {(buyer_match.group(1).strip() if buyer_match else '') or (nickname_match.group(1).strip() if nickname_match else '—')}",
        f"Tracking: {tracking_number}",
    ]
    for line in meta:
        pdf.drawString(margin, cursor, line[:72])
        cursor -= 10
    cursor -= 4

    pdf.setStrokeColorRGB(0.12, 0.16, 0.22)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.roundRect(margin - 2, 14, width - (margin * 2) + 4, cursor - 8, 6, stroke=1, fill=1)

    pdf.setFillColorRGB(0.02, 0.03, 0.05)
    pdf.setFont("Helvetica-Bold", 7.1)
    pdf.drawString(margin + 4, cursor - 14, "LOT")
    pdf.drawString(margin + 38, cursor - 14, "PRODUCT")
    cursor -= 24
    for seller_sku, product_name in display_items:
        row_top = cursor
        lot_label = _format_label_lot(seller_sku) or "—"
        pdf.setFillColorRGB(0.92, 0.94, 0.98)
        pdf.roundRect(margin + 2, row_top - 7, 28, 12, 4, stroke=0, fill=1)
        pdf.setFillColorRGB(0.18, 0.23, 0.33)
        pdf.setFont("Helvetica-Bold", 6.4)
        pdf.drawCentredString(margin + 16, row_top - 1.5, lot_label)
        line_cursor = row_top
        display_name = _normalize_pack_label_product_name(product_name)
        available_width = width - (margin * 2) - 52
        wrapped_lines, font_size = _fit_label_lines(
            display_name,
            max_width=available_width,
            font_name="Helvetica-Bold",
            preferred_font_size=6.8,
            min_font_size=5.8,
            max_lines=3,
        )
        pdf.setFillColorRGB(0.02, 0.03, 0.05)
        pdf.setFont("Helvetica-Bold", font_size)
        for wrapped in wrapped_lines:
            pdf.drawString(margin + 38, line_cursor, wrapped)
            line_cursor -= max(6.7, font_size + 1.0)
        cursor = min(line_cursor - 5, row_top - 13)
        if cursor < 24:
            break

    pdf.save()
    overlay.seek(0)
    return PdfReader(overlay).pages[0]


_TIKTOK_CONTINUATION_PAGE_CHUNK = 14


def _build_tiktok_pack_continuation_pages(width, height, identity, display_items, source_text, *, total_items=None, start_index=0):
    items = list(display_items or [])
    if not items:
        return []
    chunk_size = max(1, int(_TIKTOK_CONTINUATION_PAGE_CHUNK))
    pages = []
    for start in range(0, len(items), chunk_size):
        chunk = items[start:start + chunk_size]
        pages.append(_build_tiktok_pack_continuation_page(
            width,
            height,
            identity,
            chunk,
            source_text,
            total_items=total_items,
            start_index=int(start_index) + start,
        ))
    return pages


def _annotate_tiktok_label_pdf(raw_pdf, session_id=None, lot_map_csv_text=""):
    try:
        from PyPDF2 import PdfReader, PdfWriter
    except Exception as exc:
        raise RuntimeError(f"pdf_tools_unavailable: {exc}")

    reader = PdfReader(io.BytesIO(raw_pdf))
    writer = PdfWriter()
    product_index = _build_tiktok_live_label_product_index(session_id=session_id, lot_map_csv_text=lot_map_csv_text)
    session = get_company_session(int(session_id)) if session_id else None
    batch_overrides = _tiktok_live_batch_override_for_session(session) if session else {}
    annotated_pages = 0
    carry_tracking_number = ""
    scanner_records = []

    ocr_tracking_cache = {}
    for page_index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        page_tracking_number = _extract_tiktok_tracking_number(text)
        if page_tracking_number:
            carry_tracking_number = page_tracking_number
        if "FULL PACK LIST" in text:
            # Drop previously-generated continuation pages so we can rebuild
            # them from the current source label pages and current session data.
            continue
        identity = _extract_tiktok_label_page_identity(text)
        if not page_tracking_number and page_index > 0:
            previous_index = page_index - 1
            if previous_index not in ocr_tracking_cache:
                ocr_tracking_cache[previous_index] = _ocr_tracking_number_from_pdf_page(reader.pages[previous_index])
            previous_tracking = str(ocr_tracking_cache.get(previous_index) or "").strip()
            if previous_tracking:
                identity["tracking_number"] = previous_tracking
                carry_tracking_number = previous_tracking
        if not identity.get("tracking_number") and carry_tracking_number:
            identity["tracking_number"] = carry_tracking_number
        packed_items = []
        scanner_items = []
        seller_items = identity.get("seller_items") or [
            {"seller_sku": seller_sku, "listing_name": ""}
            for seller_sku in (identity.get("seller_skus") or [])
        ]
        for seller_item in seller_items:
            seller_sku = str(seller_item.get("seller_sku") or "").strip()
            listing_name = seller_item.get("listing_name") or ""
            batch_final_lot = _tiktok_label_batch_final_lot(listing_name, seller_sku, batch_overrides=batch_overrides)
            index_entry = (
                (product_index.get((identity["order_id"], batch_final_lot)) if batch_final_lot else None)
                or (product_index.get(("", batch_final_lot)) if batch_final_lot else None)
                or product_index.get(("tracking", identity.get("tracking_number") or "", seller_sku))
                or product_index.get((identity["order_id"], seller_sku))
                or product_index.get(("", seller_sku))
            )
            product_items = _tiktok_label_index_items(index_entry, batch_final_lot or seller_sku)
            if product_items:
                scanner_items.extend(_packing_scanner_items_from_index_entry(index_entry, batch_final_lot or seller_sku))
                fallback_lot = batch_final_lot or _tiktok_label_index_lot(index_entry, seller_sku)
                for item_lot, product_name in product_items:
                    packed_items.append((item_lot or fallback_lot, [product_name]))
        if not packed_items:
            index_entry = None
            if identity["seller_sku"]:
                index_entry = (
                    product_index.get(("tracking", identity.get("tracking_number") or "", identity["seller_sku"]))
                    or product_index.get((identity["order_id"], ""))
                    or product_index.get((identity["order_id"], identity["seller_sku"]))
                    or product_index.get(("", identity["seller_sku"]))
                )
            product_items = _tiktok_label_index_items(index_entry, identity["seller_sku"])
            if product_items:
                scanner_items.extend(_packing_scanner_items_from_index_entry(index_entry, identity["seller_sku"]))
                fallback_lot = _tiktok_label_index_lot(index_entry, identity["seller_sku"])
                for item_lot, product_name in product_items:
                    packed_items.append((item_lot or fallback_lot, [product_name]))
            elif identity["seller_sku"]:
                legacy_product_names = (
                    product_index.get((identity["order_id"], identity["seller_sku"]))
                    or product_index.get(("", identity["seller_sku"]))
                )
                if legacy_product_names:
                    scanner_items.extend(_packing_scanner_items_from_index_entry(legacy_product_names, identity["seller_sku"]))
                    packed_items.append((identity["seller_sku"], _tiktok_label_index_names(legacy_product_names)))
        expected_qty_total = int(identity.get("qty_total") or 0)
        current_item_count = len(_flatten_tiktok_pack_items(packed_items))
        needs_buyer_fallback = (
            expected_qty_total
            and (
                current_item_count < expected_qty_total
                or any(not str(item.get("barcode") or "").strip() for item in (scanner_items or []))
            )
        )
        if needs_buyer_fallback:
            buyer_entries = []
            for buyer_value in (identity.get("buyer_nickname"), identity.get("buyer_id")):
                buyer_key = _normalize_tiktok_buyer_key(buyer_value)
                if buyer_key:
                    buyer_entry = product_index.get(("buyer", buyer_key))
                    if buyer_entry:
                        buyer_entries.append(buyer_entry)
            for buyer_entry in buyer_entries:
                buyer_scanner_items = _packing_scanner_items_from_index_entry(buyer_entry)
                buyer_count = int(sum(float(item.get("qty") or 1) for item in buyer_scanner_items))
                if buyer_count != expected_qty_total:
                    continue
                buyer_packed_items = []
                for item_lot, product_name in _tiktok_label_index_items(buyer_entry):
                    buyer_packed_items.append((item_lot, [product_name]))
                if buyer_packed_items:
                    packed_items = buyer_packed_items
                    scanner_items = buyer_scanner_items
                    break
        should_emit_pack_list = bool(
            packed_items
            and "Product Name" in text
            and identity["order_id"]
            and int(identity.get("qty_total") or 0) > 0
        )
        if should_emit_pack_list:
            buyer_match = re.search(r"Buyer\s+ID:\s*[^\n]+\n\s*Buyer\s+Nickname:\s*([^\n]+)", text or "", re.I)
            nickname_match = re.search(r"Buyer\s+Nickname:\s*([^\n]+)", text or "", re.I)
            tracking_number_for_cache = str(identity.get("tracking_number") or "").strip()
            if tracking_number_for_cache and scanner_items:
                packing_session_key = f"tiktok_live_session_{session_id}" if session_id else ""
                scanner_records.append({
                    "tracking_number": tracking_number_for_cache,
                    "order_id": identity.get("order_id") or "",
                    "buyer": (buyer_match.group(1).strip() if buyer_match else "") or (nickname_match.group(1).strip() if nickname_match else ""),
                    "session_id": int(session_id) if session_id else None,
                    "session_name": str((session or {}).get("name") or "").strip(),
                    "packing_session_key": packing_session_key,
                    "source": "tiktok_label_pdf",
                    "items": scanner_items,
                })
        writer.add_page(page)
        if should_emit_pack_list:
            display_items = _flatten_tiktok_pack_items(packed_items)
            for pack_page in _build_tiktok_pack_continuation_pages(
                float(page.mediabox.width),
                float(page.mediabox.height),
                identity,
                display_items,
                text,
                total_items=len(display_items),
                start_index=0,
            ):
                writer.add_page(pack_page)
                annotated_pages += 1

    _upsert_packing_scanner_records(scanner_records)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), annotated_pages, len(reader.pages)


def _annotate_whatnot_packing_slip_pdf(raw_pdf, session_id=None):
    try:
        from PyPDF2 import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise RuntimeError(f"pdf_tools_unavailable: {exc}")

    sid = int(session_id) if session_id else None
    auction_rows = list_auction_results(session_id=sid, limit=9999)
    reader = PdfReader(io.BytesIO(raw_pdf))
    writer = PdfWriter()
    annotated_pages = 0

    for page in reader.pages:
        text = page.extract_text() or ""
        if "Whatnot Packing Slip" not in text:
            writer.add_page(page)
            continue
        shipment = _parse_slip_page(text)
        if not shipment:
            writer.add_page(page)
            continue
        shipment = match_lots_to_products([shipment], auction_rows)[0]
        display_items = shipment.get("items") or []
        if display_items:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            overlay = io.BytesIO()
            pdf = canvas.Canvas(overlay, pagesize=(width, height))
            _draw_whatnot_product_replacements(pdf, width, height, display_items)
            pdf.save()
            overlay.seek(0)
            overlay_page = PdfReader(overlay).pages[0]
            page.merge_page(overlay_page)
            annotated_pages += 1
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), annotated_pages, len(reader.pages)


def _is_tiktok_export_description_row(mapped):
    order_id = (mapped.get("external_order_id") or "").strip().lower()
    order_status = (mapped.get("order_status") or "").strip().lower()
    seller_sku = (mapped.get("seller_sku") or "").strip().lower()
    return (
        order_id.startswith("platform unique order id")
        or order_status.startswith("current order status")
        or seller_sku.startswith("seller sku input")
    )


def _xlsx_col_index(cell_ref):
    letters = "".join(ch for ch in str(cell_ref or "") if ch.isalpha()).upper()
    if not letters:
        return 0
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return max(0, index - 1)


def _xlsx_cell_text(cell, shared_strings):
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        parts = [node.text or "" for node in cell.findall(f".//{ns}t")]
        return "".join(parts).strip()
    value = cell.find(f"{ns}v")
    raw = value.text if value is not None else ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw)].strip()
        except Exception:
            return ""
    return str(raw or "").strip()


def _xlsx_base64_to_csv_text(xlsx_base64):
    raw = base64.b64decode(str(xlsx_base64 or ""), validate=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as workbook:
        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        shared_strings = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{ns}si"):
                shared_strings.append("".join(node.text or "" for node in item.findall(f".//{ns}t")))

        sheet_names = [name for name in workbook.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")]
        if not sheet_names:
            raise ValueError("xlsx_no_worksheets")
        sheet_xml = workbook.read(sorted(sheet_names)[0])
        root = ET.fromstring(sheet_xml)
        rows = []
        max_columns = 0
        for row in root.findall(f".//{ns}sheetData/{ns}row"):
            values = []
            for cell in row.findall(f"{ns}c"):
                col = _xlsx_col_index(cell.attrib.get("r"))
                while len(values) <= col:
                    values.append("")
                values[col] = _xlsx_cell_text(cell, shared_strings)
            if any(str(value or "").strip() for value in values):
                rows.append(values)
                max_columns = max(max_columns, len(values))
        output = io.StringIO()
        writer = csv.writer(output)
        for row in rows:
            writer.writerow(row + [""] * (max_columns - len(row)))
        return output.getvalue()


def _tiktok_customer_key(mapped, *, source="tiktok_shop"):
    buyer_username = (mapped.get("buyer_username") or "").strip().lower()
    if buyer_username:
        return f"{str(source or 'tiktok').strip().lower()}:{buyer_username}"
    recipient = (mapped.get("recipient_name") or "").strip().lower()
    phone = (mapped.get("phone") or "").strip()
    if recipient or phone:
        return f"{str(source or 'tiktok').strip().lower()}:{recipient}:{phone}"
    order_id = (mapped.get("external_order_id") or "").strip()
    if order_id:
        return f"{str(source or 'tiktok').strip().lower()}-order:{order_id}"
    return None


def _build_tiktok_external_ref(mapped, *, source="tiktok_shop", row_number=None):
    order_id = (mapped.get("external_order_id") or "").strip()
    seller_sku = (mapped.get("seller_sku") or "").strip()
    barcode = (mapped.get("barcode") or "").strip()
    external_sku_id = (mapped.get("external_sku_id") or "").strip()
    package_id = (mapped.get("external_package_id") or "").strip()
    unique_piece = seller_sku or barcode or external_sku_id or package_id or (str(row_number) if row_number is not None else "")
    if order_id and unique_piece:
        return f"{source}:{order_id}:{unique_piece}"
    if order_id:
        return f"{source}:{order_id}"
    if unique_piece:
        return f"{source}:row:{unique_piece}"
    if row_number is not None:
        return f"{source}:row:{row_number}"
    return None


def _is_tiktok_cancelled(mapped, unit_price=0.0, subtotal=0.0):
    order_status = (mapped.get("order_status") or "").strip().lower()
    cancel_type = (mapped.get("cancellation_return_type") or "").strip().lower()
    cancelled_at = (mapped.get("cancelled_at") or "").strip()
    order_total = _parse_tiktok_float(mapped.get("order_total"), 0)
    refund_total = _parse_tiktok_float(mapped.get("refund_total"), 0)
    if cancelled_at:
        return True
    if "cancel" in order_status or "return" in order_status:
        return True
    if "cancel" in cancel_type or "return" in cancel_type:
        return True
    if order_total <= 0 and subtotal <= 0 and unit_price <= 0:
        return True
    if refund_total > 0 and order_total > 0 and refund_total >= order_total:
        return True
    return False


def _tiktok_payment_status(mapped, is_cancelled=False):
    if is_cancelled:
        return "unpaid"
    return "paid" if (mapped.get("paid_at") or "").strip() else "unpaid"


def _tiktok_fulfillment_status(mapped, is_cancelled=False):
    if is_cancelled:
        return "cancelled"
    if (mapped.get("delivered_at") or "").strip():
        return "delivered"
    if (mapped.get("shipped_at") or "").strip():
        return "shipped"
    return "pending"


def _tiktok_live_fulfillment_status(mapped=None, is_cancelled=False):
    if is_cancelled:
        return "cancelled"
    return "delivered"


def _tiktok_match_product(products, mapped):
    seller_sku = (mapped.get("seller_sku") or "").strip()
    barcode = (mapped.get("barcode") or "").strip()
    product_name = (mapped.get("combined_listing") or mapped.get("product_name") or "").strip()

    product = None
    matched_by = None
    score = 0

    if barcode:
        product = _match_inventory_product_by_code(products, barcode=barcode)
        if product:
            matched_by = "barcode"
            score = 100
    if not product and seller_sku:
        product = _match_inventory_product_by_code(products, sku=seller_sku)
        if product:
            matched_by = "seller_sku"
            score = 95
    if not product and product_name:
        product, score = _match_inventory_product(products, product_name)
        if product:
            matched_by = "product_name"

    warning = None
    if product and barcode and (product.get("barcode") or "").strip() and (product.get("barcode") or "").strip() != barcode:
        warning = "barcode_mismatch"

    return product, matched_by, score, warning


def _build_tiktok_order_note(row):
    mapped = _tiktok_normalized_row(row)
    channel_label = "TikTok order"
    if (mapped.get("seller_sku") or "").strip():
        channel_label = f"TikTok order | Lot {mapped.get('seller_sku')}"
    elif (mapped.get("recipient_name") or "").strip():
        channel_label = f"TikTok order | {mapped.get('recipient_name')}"
    pieces = [channel_label, mapped.get("phone")]
    address_bits = [
        mapped.get("address_line_1"),
        mapped.get("address_line_2"),
        mapped.get("city"),
        mapped.get("state"),
        mapped.get("zipcode"),
        mapped.get("country"),
    ]
    address = ", ".join([bit for bit in address_bits if bit])
    if address:
        pieces.append(address)
    if mapped.get("external_order_id"):
        pieces.append(f"Order ID: {mapped.get('external_order_id')}")
    if mapped.get("external_package_id"):
        pieces.append(f"Package ID: {mapped.get('external_package_id')}")
    if mapped.get("tracking_number"):
        pieces.append(f"Tracking ID: {mapped.get('tracking_number')}")
    if mapped.get("order_status"):
        pieces.append(f"Status: {mapped.get('order_status')}")
    if mapped.get("order_substatus"):
        pieces.append(f"Substatus: {mapped.get('order_substatus')}")
    if mapped.get("variation_name"):
        pieces.append(f"Variant: {mapped.get('variation_name')}")
    if mapped.get("buyer_nickname"):
        pieces.append(f"Buyer Nickname: {mapped.get('buyer_nickname')}")
    if mapped.get("buyer_message"):
        pieces.append(f"Buyer Message: {mapped.get('buyer_message')}")
    if mapped.get("delivery_instruction"):
        pieces.append(f"Delivery note: {mapped.get('delivery_instruction')}")
    if mapped.get("payment_method"):
        pieces.append(f"Payment: {mapped.get('payment_method')}")
    if mapped.get("seller_note"):
        pieces.append(f"Seller Note: {mapped.get('seller_note')}")
    if mapped.get("shipping_information_raw"):
        pieces.append(f"Shipping Info: {mapped.get('shipping_information_raw')}")
    return " | ".join([piece for piece in pieces if piece])

# ---------------------------------------------------------------------------
# Odoo XML-RPC helpers
# ---------------------------------------------------------------------------
import xmlrpc.client as _xmlrpc

def _odoo_models():
    """Return authenticated Odoo models proxy, or raise RuntimeError."""
    if not ODOO_URL or not ODOO_DB or not ODOO_API_KEY:
        raise RuntimeError("Odoo not configured (ODOO_URL / ODOO_DB / ODOO_API_KEY missing)")
    common = _xmlrpc.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_API_KEY, {})
    if not uid:
        raise RuntimeError("Odoo authentication failed")
    return _xmlrpc.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object"), uid

def odoo_search_read(model, domain, fields, limit=200, order="id desc"):
    models, uid = _odoo_models()
    return models.execute_kw(
        ODOO_DB, uid, ODOO_API_KEY,
        model, "search_read", [domain],
        {"fields": fields, "limit": limit, "order": order},
    )

def odoo_call(model, method, args, kwargs=None):
    models, uid = _odoo_models()
    return models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, model, method, args, kwargs or {})

def odoo_write(model, ids, vals):
    models, uid = _odoo_models()
    return models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, model, "write", [ids, vals])

def _extract_odoo_error(fault):
    msg = getattr(fault, "faultString", str(fault))
    lines = [l.strip() for l in msg.splitlines() if l.strip()]
    return lines[-1] if lines else str(fault)

def _parse_price_value(payload):
    value = payload.get("price_value")
    if value is None:
        value = payload.get("sale_price")
    if value is None:
        value = payload.get("winning_price")
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    price = payload.get("price")
    if price:
        cleaned = re.sub(r"[^0-9.]", "", str(price))
        if cleaned:
            try:
                return float(cleaned)
            except (TypeError, ValueError):
                pass
    footer = payload.get("footer_text") or ""
    matches = re.findall(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)", footer)
    if matches:
        try:
            return float(matches[-1].replace(",", ""))
        except (TypeError, ValueError):
            return None
    return None


def _current_company_session():
    status = collector_status()
    if not status.get("running"):
        # Allow Operator to run an "our auction" workflow without the Whatnot live collector,
        # e.g. TikTok auction mode. This is gated by an explicit operator toggle.
        try:
            state = load_collector_state()
        except Exception:
            state = {}
        if state.get("tiktok_operator_enabled") and state.get("tiktok_operator_session_id"):
            try:
                session = get_company_session(int(state["tiktok_operator_session_id"]))
                if session and str(session.get("status") or "").lower() != "ended":
                    return session
            except Exception:
                pass
        return None
    session_id = status.get("session_id")
    if not session_id:
        return None
    try:
        session = get_company_session(int(session_id))
        if not session:
            return None
        if str(session.get("status") or "").lower() == "ended":
            return None
        return session
    except Exception:
        return None


def _tiktok_operator_status():
    """Return current TikTok operator configuration from collector_state.json."""
    try:
        state = load_collector_state() or {}
    except Exception:
        state = {}
    return {
        "enabled": bool(state.get("tiktok_operator_enabled")),
        "stream_url": (state.get("tiktok_operator_stream_url") or "").strip() or None,
        "streamer": (state.get("tiktok_operator_streamer") or "").strip() or None,
        "session_id": state.get("tiktok_operator_session_id"),
        "last_ingested_event_id": int(state.get("tiktok_operator_last_ingested_event_id") or 0),
    }


def _sync_tiktok_operator_session_to_latest_stream():
    """
    Self-heal TikTok operator mode when the watcher creates a newer stream row.
    This can happen after restarting the OCR watcher with `--new-stream` or after
    a mid-stream recovery. The Operator UI should follow the latest TikTok stream
    automatically instead of staying pinned to an older company session.
    """
    cfg = _tiktok_operator_status()
    if not cfg.get("enabled") or not cfg.get("stream_url"):
        return None

    try:
        latest_stream_id = get_stream_id(cfg["stream_url"])
    except Exception:
        latest_stream_id = None
    if not latest_stream_id:
        return None

    try:
        current_session = get_company_session(int(cfg.get("session_id") or 0)) if cfg.get("session_id") else None
    except Exception:
        current_session = None

    if current_session and str(current_session.get("status") or "").lower() != "ended":
        try:
            if int(current_session.get("stream_id") or 0) == int(latest_stream_id):
                return current_session
        except Exception:
            pass

    session_id = _ensure_tiktok_operator_session(cfg["stream_url"], streamer=cfg.get("streamer"))
    if not session_id:
        return current_session

    try:
        state = load_collector_state() or {}
    except Exception:
        state = {}
    state["tiktok_operator_session_id"] = int(session_id)
    save_collector_state(state)
    try:
        return get_company_session(int(session_id))
    except Exception:
        return None


def _ensure_tiktok_operator_session(stream_url: str, streamer: str | None = None):
    """Create (or reuse) a live company session for TikTok operator mode."""
    stream_url = (stream_url or "").strip()
    if not stream_url:
        return None

    # Ensure a stream record exists in the shared DB so company_sessions can link it.
    try:
        stream_id = get_stream_id(stream_url)
    except Exception:
        stream_id = None
    if not stream_id:
        try:
            stream_id = ensure_ingest_stream(
                stream_url,
                streamer_name=(streamer or "").strip() or None,
                title="TikTok LIVE (Operator)",
                started_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception:
            stream_id = None
    if not stream_id:
        try:
            stream_id = get_stream_id(stream_url)
        except Exception:
            stream_id = None

    # End any existing live sessions for the same show_id to keep operator data clean.
    try:
        for s in list_company_sessions(OUR_WHATNOT_ACCOUNT, limit=200):
            if s.get("show_id") == stream_url and s.get("status") in ("draft", "live", "open"):
                try:
                    end_company_session(int(s["id"]))
                except Exception:
                    pass
    except Exception:
        pass

    created = create_company_session(
        stream_id=int(stream_id) if stream_id else None,
        show_id=stream_url,
        whatnot_account=OUR_WHATNOT_ACCOUNT,
        name=f"TikTok {streamer or stream_url} · {datetime.now().strftime('%Y-%m-%d %I:%M %p')}",
        status="live",
    )
    return int(created["id"]) if created else None


def _ingest_tiktok_operator_winners(local_company_session):
    """Ingest TikTok 'won' events into the active company session (when enabled)."""
    cfg = _tiktok_operator_status()
    if not cfg.get("enabled") or not cfg.get("stream_url"):
        return 0

    synced_session = _sync_tiktok_operator_session_to_latest_stream()
    if synced_session:
        local_company_session = synced_session
    if not local_company_session:
        return 0

    try:
        tiktok_stream_id = get_stream_id(cfg["stream_url"])
    except Exception:
        tiktok_stream_id = None
    if not tiktok_stream_id:
        return 0

    since_id = int(cfg.get("last_ingested_event_id") or 0)
    rows = [
        row for row in get_events_since(int(since_id), stream_id=int(tiktok_stream_id), limit=500)
        if str(row.get("event_type") or "") == "tiktok_auction_won"
    ][:50]

    ingested = 0
    max_id = since_id
    for row in rows:
        event_id = int(row.get("id") or 0)
        created_at = row.get("created_at")
        raw_payload = row.get("payload")
        max_id = max(max_id, event_id)
        try:
            p = json.loads(raw_payload or "{}")
        except Exception:
            p = {}
        lot_number = str(p.get("lot_number") or "").strip()
        winner_username = (p.get("winner_username") or p.get("winner") or "").strip()
        sale_price = p.get("sale_price")
        if sale_price in (None, ""):
            sale_price = p.get("raw_price")
        try:
            sale_price = float(sale_price or 0)
        except Exception:
            sale_price = 0.0
        if not (lot_number and winner_username):
            continue

        # Route through the normal winner ingest pipeline so Operator can:
        # 1) see a pending winner ticket (lot + winner + price)
        # 2) scan barcode to assign the real product
        # 3) confirm to deduct inventory and finalize revenue
        winner_payload = {
            "lot_number": lot_number,
            "winner_username": winner_username,
            "sale_price": float(sale_price or 0),
            "order_source": "tiktok_live",
        }

        ok = _maybe_ingest_winner_event(
            int(event_id),
            created_at,
            winner_payload,
            stream_id=int(tiktok_stream_id),
        )
        if ok:
            ingested += 1

    # Persist cursor so we don't re-ingest on next poll.
    try:
        state = load_collector_state() or {}
    except Exception:
        state = {}
    state["tiktok_operator_last_ingested_event_id"] = int(max_id or since_id)
    save_collector_state(state)
    return ingested


def _extract_show_id(stream_url):
    match = re.search(r"/live/([^/?#]+)", stream_url or "")
    return match.group(1) if match else None


MAX_INGEST_RETRIES = 5


def _resolve_company_session(requested=None, allow_latest=False):
    if requested:
        try:
            row = get_company_session(int(requested))
            if row:
                return row
        except (TypeError, ValueError):
            pass
    current = _current_company_session()
    if current:
        return current
    if allow_latest:
        rows = list_company_sessions(OUR_WHATNOT_ACCOUNT, limit=1)
        return rows[0] if rows else None
    return None


def _maybe_ingest_winner_event(event_id, created_at, payload, failed_ingest_id=None, stream_id=None):
    if not isinstance(payload, dict):
        return False
    winner_username = (payload.get("winner") or payload.get("winner_username") or "").strip()
    lot_number = str(payload.get("lot_number") or "").strip()
    sale_price = _parse_price_value(payload)
    if not winner_username:
        return False
    # Prefer stream-based lookup (most accurate) over collector state (may be stale).
    # Important: if a stream_id is present but does not map to an active company
    # session, do not fall back to whatever company session happens to be live.
    # That can leak old/backfilled winner events from a previous stream run into a
    # new live session for the same show URL.
    local_company_session = None
    if stream_id is not None:
        try:
            local_company_session = get_company_session_for_stream(int(stream_id))
        except Exception:
            pass
        if not local_company_session:
            return False
    if not local_company_session:
        local_company_session = _current_company_session()
    if local_company_session:
        try:
            recent_dup = None
            recent_rows = list_pending_winner_assignments(
                session_id=int(local_company_session["id"]),
                statuses=("pending", "assigned", "needs_review", "confirmed"),
                limit=200,
            )
            compare_username = (winner_username or "").strip().lower()
            compare_price = float(sale_price or 0)
            compare_created = str(created_at or "")
            for row in recent_rows:
                row_username = str(row.get("winner_username") or "").strip().lower()
                row_price = float(row.get("sale_price") or 0)
                detected_at = str(row.get("detected_at") or row.get("created_at") or "")
                if row_username != compare_username:
                    continue
                if abs(row_price - compare_price) >= 0.011:
                    continue
                # Keep the same approximate 20-second dedupe window without raw SQL datetime().
                try:
                    detected_dt = datetime.fromisoformat(detected_at.replace("Z", "+00:00"))
                    created_dt = datetime.fromisoformat(compare_created.replace("Z", "+00:00"))
                    if (created_dt - detected_dt).total_seconds() > 20:
                        continue
                except Exception:
                    if detected_at and compare_created and detected_at < compare_created:
                        continue
                recent_dup = row
                break
            if recent_dup:
                if failed_ingest_id:
                    mark_failed_ingest_resolved(failed_ingest_id)
                return True
        except Exception:
            pass
        lot = get_current_company_lot(local_company_session["id"])
        if not lot and lot_number:
            lot = get_company_lot_by_number(local_company_session["id"], lot_number)
        if not lot and lot_number:
            lot = create_company_lot(local_company_session["id"], lot_number, status="open")
            if lot:
                update_company_session(local_company_session["id"], current_lot_number=lot_number)
        if lot:
            if lot_number:
                try:
                    existing_confirmed = list_pending_winner_assignments(
                        session_id=int(local_company_session["id"]),
                        statuses=("confirmed",),
                        limit=500,
                    )
                except Exception:
                    existing_confirmed = []
                if any(str(row.get("lot_number") or "").strip() == lot_number for row in existing_confirmed):
                    if failed_ingest_id:
                        mark_failed_ingest_resolved(failed_ingest_id)
                    return True
            source_event_id = f"collector_event_{event_id}"
            existing = get_auction_result_by_source_event_id(source_event_id)
            if existing:
                assignment = queue_pending_winner_assignment(
                    local_company_session["id"],
                    lot_id=existing.get("lot_id") or lot.get("id"),
                    auction_result_id=existing.get("id"),
                    lot_number=existing.get("lot_number") or lot_number or lot.get("lot_number"),
                    winner_username=existing.get("winner_username") or winner_username,
                    sale_price=float(existing.get("sale_price") or sale_price or 0),
                    source_event_id=source_event_id,
                    detected_at=existing.get("sold_at") or created_at,
                )
                if assignment and candidate_items:
                    sync_pending_winner_assignment_items_from_lot(int(assignment["id"]), int(lot["id"]))
                if failed_ingest_id:
                    mark_failed_ingest_resolved(failed_ingest_id)
                return True
            if lot_number and lot.get("lot_number") != lot_number:
                lot = rename_company_lot(lot["id"], lot_number)
            items = list_lot_items(lot["id"])
            candidate_items = [item for item in items if item.get("status") in ("open", "active", "queued")]
            cost_price = 0.0
            product_name = lot_number or lot.get("lot_number") or "Awaiting product assignment"
            customer = upsert_customer(winner_username, display_name=winner_username)
            customer_id = customer.get("id") if customer else None
            # Calculate platform fees from settings
            try:
                _settings = get_setting_map()
            except Exception:
                _settings = {}
            _fee_pct = float(_settings.get("platform_fee_pct", 10.9))
            _fixed_fee = float(_settings.get("fixed_fee", 0.50))
            safe_sale_price = float(sale_price or 0)
            calculated_fees = round(safe_sale_price * _fee_pct / 100.0 + (_fixed_fee if safe_sale_price > 0 else 0), 2)
            result = record_auction_result(
                local_company_session["id"],
                lot_id=lot["id"],
                lot_number=lot_number or lot.get("lot_number"),
                winner_username=winner_username,
                customer_id=customer_id,
                sale_price=safe_sale_price,
                fees=calculated_fees,
                cost_price=cost_price,
                product_name=product_name,
                products_sold_count=0,
                source_event_id=source_event_id,
            )
            if not result.get("_created", True):
                assignment = queue_pending_winner_assignment(
                    local_company_session["id"],
                    lot_id=result.get("lot_id") or lot.get("id"),
                    auction_result_id=result.get("id"),
                    lot_number=result.get("lot_number") or lot_number or lot.get("lot_number"),
                    winner_username=result.get("winner_username") or winner_username,
                    sale_price=float(result.get("sale_price") or sale_price or 0),
                    source_event_id=source_event_id,
                    detected_at=result.get("sold_at") or created_at,
                )
                if assignment and candidate_items:
                    sync_pending_winner_assignment_items_from_lot(int(assignment["id"]), int(lot["id"]))
                if failed_ingest_id:
                    mark_failed_ingest_resolved(failed_ingest_id)
                return True
            assignment_notes = None
            incomplete_reasons = []
            if not winner_username:
                incomplete_reasons.append("missing winner username")
            if not (lot_number or lot.get("lot_number")):
                incomplete_reasons.append("missing lot number")
            if incomplete_reasons:
                assignment_notes = "Auto-routed to Needs Review: " + ", ".join(incomplete_reasons)
            assignment = queue_pending_winner_assignment(
                local_company_session["id"],
                lot_id=lot.get("id"),
                auction_result_id=result.get("id"),
                lot_number=lot_number or lot.get("lot_number"),
                winner_username=winner_username,
                sale_price=safe_sale_price,
                source_event_id=source_event_id,
                detected_at=result.get("sold_at") or created_at,
                notes=assignment_notes,
            )
            if assignment and incomplete_reasons:
                assignment = update_pending_winner_assignment_status(
                    assignment["id"],
                    "needs_review",
                    notes=assignment_notes,
                )
            if assignment and candidate_items:
                assignment = sync_pending_winner_assignment_items_from_lot(int(assignment["id"]), int(lot["id"])) or assignment
            update_company_lot(
                lot["id"],
                status="sold",
                winner_username=winner_username,
                winning_price=safe_sale_price,
                fees=float(result.get("fees") or 0),
                total_cost=0,
                total_profit=float(sale_price or 0) - float(result.get("fees") or 0),
                sold_products=0,
                closed_at=result.get("sold_at") or created_at,
            )
            create_buyer_group(local_company_session["id"], winner_username, customer_id=customer_id)
            mark_lot_items_status(lot["id"], from_statuses=("open", "active", "queued"), to_status="dropped")
            update_company_session(local_company_session["id"], current_lot_number=None)
            clear_shared_scan_for_session(local_company_session["id"])
            _clear_live_obs_scan(local_company_session["id"])
            _set_demo_scan(None)  # clear demo scan on winner
            if failed_ingest_id:
                mark_failed_ingest_resolved(failed_ingest_id)
            return True
    error_msg = "no_active_company_lot"
    if failed_ingest_id:
        increment_retry_count(failed_ingest_id, error_message=error_msg)
    else:
        save_failed_ingest(event_id, winner_username, sale_price, lot_number, created_at, error_msg)
    return False


def _sync_live_lot_number(payload, stream_id=None):
    if not isinstance(payload, dict):
        return
    lot_number = str(payload.get("lot_number") or "").strip()
    if not lot_number:
        return

    local_company_session = None
    if stream_id is not None:
        try:
            local_company_session = get_company_session_for_stream(int(stream_id))
        except Exception:
            pass
    if not local_company_session:
        local_company_session = _current_company_session()
    if not local_company_session:
        return

    lot = get_current_company_lot(local_company_session["id"])
    if not lot and lot_number:
        lot = get_company_lot_by_number(local_company_session["id"], lot_number)
    if not lot and lot_number:
        lot = create_company_lot(local_company_session["id"], lot_number, status="open")
        if lot:
            update_company_session(local_company_session["id"], current_lot_number=lot_number)
    if not lot:
        return
    current_lot_number = str(lot.get("lot_number") or "").strip()
    if current_lot_number == lot_number:
        return

    lot = rename_company_lot(lot["id"], lot_number)
    scan = shared_scan_for_session(local_company_session["id"]) or None
    if scan:
        updated_scan = dict(scan)
        updated_scan["lot_id"] = lot.get("id")
        updated_scan["lot_number"] = lot_number
        set_shared_scan_for_session(local_company_session["id"], updated_scan)
        _set_live_obs_scan(local_company_session["id"], updated_scan)


def _auto_create_sale_order_for_lot(session_id, winner_username, customer_id, lot, open_items, sale_price, auction_result_id=None):
    """Create or find a draft sale order for this buyer and add a line for the lot."""
    try:
        so = get_or_create_buyer_sale_order(int(session_id), winner_username, customer_id=customer_id)
        if not so:
            return
        lot_id = lot.get("id") if lot else None
        # Distribute sale_price evenly across items; fall back to sale_price for the whole lot
        if open_items:
            per_item_price = round(float(sale_price or 0) / len(open_items), 4)
            for item in open_items:
                product_id = item.get("product_id")
                desc = item.get("product_name") or item.get("description") or f"Lot {lot.get('lot_number')} item"
                qty = float(item.get("qty_snapshot") or 1)
                add_sale_order_line_for_item(
                    so["id"], product_id=product_id, description=desc, qty=qty,
                    unit_price=per_item_price, lot_id=lot_id, auction_result_id=auction_result_id,
                )
        else:
            desc = f"Lot {lot.get('lot_number')}"
            add_sale_order_line_for_item(
                so["id"], product_id=None, description=desc, qty=1,
                unit_price=float(sale_price or 0), lot_id=lot_id, auction_result_id=auction_result_id,
            )
    except Exception:
        pass  # Never block auction ingestion on SO creation failure


def _process_event_side_effects(events, stream_id=None):
    """Process live collector side effects for our stream."""
    for e in events:
        if e["event_type"] == "lot_update":
            try:
                payload = json.loads(e["payload"] or "{}")
            except Exception:
                continue
            _sync_live_lot_number(payload, stream_id=stream_id)
        elif e["event_type"] == "auction_winner":
            try:
                payload = json.loads(e["payload"] or "{}")
            except Exception:
                continue
            _maybe_ingest_winner_event(e["id"], e["created_at"], payload, stream_id=stream_id)
        elif e["event_type"] == "stream_ended":
            # Auto-end the company session when the stream finishes
            try:
                session = _current_company_session()
                if session and session.get("status") == "live":
                    clear_shared_scan_for_session(session["id"])
                    _clear_live_obs_scan(session["id"])
                    _set_demo_scan(None)
                    end_company_session(int(session["id"]))
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------

def _serve_static(handler, file_path):
    """Serve a static file from the Vite dist directory."""
    if not os.path.isfile(file_path):
        handler.send_response(404)
        handler.end_headers()
        return
    content_type, _ = mimetypes.guess_type(file_path)
    content_type = content_type or "application/octet-stream"
    with open(file_path, "rb") as f:
        data = f.read()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    if os.path.basename(file_path) == "index.html":
        handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        handler.send_header("Pragma", "no-cache")
    else:
        handler.send_header("Cache-Control", "public, max-age=3600")
    _send_security_headers(handler)
    handler.end_headers()
    handler.wfile.write(data)


def _send_security_headers(handler):
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
    handler.send_header("X-Frame-Options", "DENY")
    if _handler_is_trustworthy_origin(handler):
        handler.send_header("Cross-Origin-Opener-Policy", "same-origin")
        handler.send_header("Cross-Origin-Resource-Policy", "same-origin")
    handler.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), interest-cohort=()")
    handler.send_header("Content-Security-Policy", DASHBOARD_CSP)
    if DASHBOARD_HSTS_ENABLED and _handler_is_https(handler):
        handler.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")


def _handler_is_https(handler):
    proto = (handler.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
    return proto == "https"


def _handler_is_trustworthy_origin(handler):
    host = (handler.headers.get("Host") or "").split(":", 1)[0].strip().lower()
    return _handler_is_https(handler) or host in {"localhost", "127.0.0.1", "::1"}


# ---------------------------------------------------------------------------
# Request Handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    _NON_API_AUTH_PATHS = {"/latest_id", "/events", "/recent", "/obs/demo"}

    @staticmethod
    def _json_default(value):
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (set, tuple)):
            return list(value)
        return str(value)

    def _json(self, obj, status=200, extra_headers=None):
        started_at = getattr(self, "_req_started_at", None)
        data = json.dumps(obj, default=self._json_default).encode("utf-8")
        payload_bytes = len(data)
        elapsed_ms = None
        if isinstance(started_at, (int, float)):
            elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 1)

        if getattr(self, "_req_perf_pending", False):
            method = getattr(self, "_req_method", self.command)
            parsed = urlparse(getattr(self, "_req_path", self.path or ""))
            path = parsed.path or "/"
            query = parsed.query or ""
            perf_event = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "method": method,
                "path": path,
                "query": query,
                "status": int(status),
                "duration_ms": elapsed_ms,
                "response_bytes": payload_bytes,
                "client_ip": self._client_ip(),
            }
            _append_api_perf_event(perf_event)
            self._req_perf_pending = False

            if (
                (elapsed_ms is not None and elapsed_ms >= API_PERF_SLOW_MS)
                or payload_bytes >= API_PERF_LARGE_BYTES
            ):
                print(
                    f"[api-perf] {method} {path} status={status} ms={elapsed_ms} bytes={payload_bytes}",
                    flush=True,
                )

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(payload_bytes))
        if elapsed_ms is not None:
            self.send_header("Server-Timing", f"app;dur={elapsed_ms}")
        _send_security_headers(self)
        for key, value in (extra_headers or []):
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    # Most API calls are tiny, but TikTok CSV/XLSX imports are posted as JSON
    # from the browser and can be a few hundred KB after encoding.
    _MAX_REQUEST_BODY = 25 * 1024 * 1024

    class RequestTooLargeError(Exception):
        pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        if length > self._MAX_REQUEST_BODY:
            # Drain and reject oversized bodies
            self.rfile.read(min(length, self._MAX_REQUEST_BODY))
            self._json({"ok": False, "error": "request_too_large"}, status=413)
            raise self.RequestTooLargeError("request_too_large")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def log_message(self, format, *args):
        # Quieter logging — skip noisy polling requests
        path = ""
        if args and isinstance(args[0], str):
            parts = args[0].split(" ")
            if len(parts) > 1:
                path = parts[1]
        if path in ("/events", "/latest_id", "/api/session_stats", "/api/stream_status"):
            return
        super().log_message(format, *args)

    def handle_error(self, request, client_address):
        # Suppress BrokenPipeError — happens when the browser tab closes mid-response
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)

    def _check_auth(self):
        """Return True if request is authorized. Only enforced when API_SECRET_KEY is set."""
        if not API_SECRET_KEY:
            return True
        auth = self.headers.get("Authorization", "")
        if auth == f"Bearer {API_SECRET_KEY}":
            return True
        self._json({"ok": False, "error": "unauthorized"}, status=401)
        return False

    def _client_ip(self):
        forwarded = (self.headers.get("CF-Connecting-IP") or self.headers.get("X-Forwarded-For") or "").strip()
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "unknown"

    def _cookie_dict(self):
        raw = self.headers.get("Cookie", "")
        cookies = {}
        for part in raw.split(";"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            cookies[key.strip()] = value.strip()
        return cookies

    def _current_session(self):
        cookies = self._cookie_dict()
        return get_session(
            cookies.get(session_cookie_name()),
            client_ip=self._client_ip(),
            user_agent=self.headers.get("User-Agent", ""),
        )

    def _obs_scope_key(self):
        session = self._current_session() or {}
        email = str(session.get("email") or "").strip().lower()
        if not email:
            return "global"
        return f"user:{email}"

    def _partner_price_payload(self, product):
        return None

    def _set_session_cookie_header(self, session_id, *, clear=False):
        pieces = [f"{session_cookie_name()}={'' if clear else session_id}", "Path=/", "HttpOnly", "SameSite=Strict"]
        if DASHBOARD_HTTPS_ONLY:
            pieces.append("Secure")
        if clear:
            pieces.append("Max-Age=0")
            pieces.append("Expires=Thu, 01 Jan 1970 00:00:00 GMT")
        return ("Set-Cookie", "; ".join(pieces))

    def _session_auth_required(self, path):
        if not auth_enabled():
            return False
        if path in self._NON_API_AUTH_PATHS:
            return True
        if not path.startswith("/api/"):
            return False
        if path in {
            "/api/auth/config",
            "/api/auth/me",
            "/api/auth/lookup",
            "/api/auth/login",
            "/api/auth/logout",
        }:
            return False
        if path.startswith("/api/obs/"):
            return False
        if path.startswith("/api/v2/purchases/bargain/"):
            return False
        return True

    def _send_html(self, html, status=200):
        data = str(html or "").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        _send_security_headers(self)
        self.end_headers()
        self.wfile.write(data)

    def _handle_purchase_bargain_vendor_get(self, path):
        from app.api.routers.purchases import _build_vendor_html as _build_purchase_bargain_vendor_html

        token = path.removeprefix("/api/v2/purchases/bargain/").strip("/")
        if not token or "/" in token:
            self._json({"ok": False, "error": "bargain_session_not_found"}, status=404)
            return
        data = get_bargain_by_token(token)
        if not data:
            self._json({"ok": False, "error": "bargain_session_not_found"}, status=404)
            return
        proto = (self.headers.get("X-Forwarded-Proto") or "https").split(",", 1)[0].strip() or "https"
        host = (self.headers.get("Host") or "").strip()
        base_url = f"{proto}://{host}" if host else ""
        self._send_html(_build_purchase_bargain_vendor_html(data, base_url))

    def _handle_purchase_bargain_vendor_submit(self, path):
        from app.api.routers.purchases import _build_vendor_html as _build_purchase_bargain_vendor_html

        token = path.removeprefix("/api/v2/purchases/bargain/").removesuffix("/submit").strip("/")
        if not token or "/" in token:
            self._json({"ok": False, "error": "bargain_session_not_found"}, status=404)
            return
        content_type = self.headers.get("Content-Type", "")
        vendor_prices = []
        vendor_notes = None
        if "application/json" in content_type:
            payload = self._read_json()
            vendor_prices = payload.get("vendor_prices") or []
            vendor_notes = payload.get("vendor_notes")
        else:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8", errors="replace") if length > 0 else ""
            form = parse_qs(raw, keep_blank_values=True)
            vendor_notes = (form.get("vendor_notes") or [""])[0].strip() or None
            for key, values in form.items():
                if not key.startswith("vp_"):
                    continue
                try:
                    line_id = int(key[3:])
                    vendor_prices.append({
                        "line_id": line_id,
                        "vendor_price": float((values or [""])[0]),
                        "availability_status": (form.get(f"avail_{line_id}") or ["available"])[0],
                        "available_qty": (form.get(f"aq_{line_id}") or [""])[0],
                        "case_pack": (form.get(f"case_{line_id}") or [""])[0],
                        "replacement": (form.get(f"repl_{line_id}") or [""])[0],
                        "bulk_discount": (form.get(f"bulk_{line_id}") or [""])[0],
                    })
                except (TypeError, ValueError):
                    pass
        try:
            result = submit_bargain_quote(token, vendor_prices, vendor_notes=vendor_notes)
        except ValueError as exc:
            self._json({"ok": False, "error": str(exc)}, status=400)
            return
        if "application/json" in content_type:
            self._json({"ok": True, **(result or {})})
            return
        data = get_bargain_by_token(token)
        if not data:
            self._json({"ok": False, "error": "bargain_session_not_found"}, status=404)
            return
        proto = (self.headers.get("X-Forwarded-Proto") or "https").split(",", 1)[0].strip() or "https"
        host = (self.headers.get("Host") or "").strip()
        base_url = f"{proto}://{host}" if host else ""
        self._send_html(_build_purchase_bargain_vendor_html(data, base_url))

    def _require_session_auth(self):
        session = self._current_session()
        if session:
            return session
        self._json({"ok": False, "error": "auth_required"}, status=401)
        return None

    def _verify_csrf(self, session):
        if not session:
            return False
        token = (self.headers.get(csrf_header_name()) or "").strip()
        if token and token == session.get("csrf_token"):
            return True
        self._json({"ok": False, "error": "csrf_failed"}, status=403)
        return False

    def _verify_request_origin(self):
        # File uploads from Chromium/PDF/file-picker flows can produce Origin
        # values that are inconsistent across local IP, LAN hostname, and browser
        # preview contexts. Authenticated dashboard requests are still protected
        # by the session cookie and CSRF token, so do not block them here.
        return True

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", f"Content-Type,Authorization,{csrf_header_name()}")
        _send_security_headers(self)
        self.end_headers()

    # -------------------------------------------------------------------
    # GET routes
    # -------------------------------------------------------------------
    def do_GET(self):
        self._req_started_at = time.perf_counter()
        self._req_method = "GET"
        self._req_path = self.path
        self._req_perf_pending = True
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/auth/config":
            challenge = issue_login_challenge(self._client_ip())
            self._json({
                "ok": True,
                "auth_enabled": auth_enabled(),
                "https_only": DASHBOARD_HTTPS_ONLY,
                "csrf_header": csrf_header_name(),
                "session_cookie_name": session_cookie_name(),
                **challenge,
            })
            return

        if path == "/api/auth/me":
            if not auth_enabled():
                self._json({"ok": True, "authenticated": False, "auth_enabled": False, "user": None})
                return
            session = self._current_session()
            if not session:
                self._json({"ok": True, "authenticated": False, "auth_enabled": True, "user": None})
                return
            self._json({
                "ok": True,
                "authenticated": True,
                "auth_enabled": True,
                "csrf_token": session.get("csrf_token"),
                "user": get_user_public_profile(session.get("email")) or {
                    "email": session.get("email"),
                    "display_name": session.get("display_name"),
                    "role": session.get("role"),
                    "mfa_enabled": False,
                    "backup_codes_remaining": 0,
                },
            })
            return

        if path == "/api/auth/lookup":
            email = (qs.get("email", [""])[0] or "").strip().lower()
            self._json({"ok": True, **lookup_auth_user(email)})
            return

        if path.startswith("/api/v2/purchases/bargain/") and not path.endswith("/submit"):
            self._handle_purchase_bargain_vendor_get(path)
            return

        if path == "/api/auth/sessions":
            if not auth_enabled():
                self._json({"ok": False, "error": "auth_disabled"}, status=400)
                return
            session = self._current_session()
            if not session:
                self._json({"ok": False, "error": "auth_required"}, status=401)
                return
            current_id = session.get("id")
            rows = []
            for row in list_active_sessions(session.get("email")):
                row["current"] = row.get("id") == current_id
                rows.append(row)
            self._json({"ok": True, "sessions": rows})
            return

        if path == "/api/auth/users":
            if not auth_enabled():
                self._json({"ok": False, "error": "auth_disabled"}, status=400)
                return
            session = self._current_session()
            if not session:
                self._json({"ok": False, "error": "auth_required"}, status=401)
                return
            if (session.get("role") or "") != "admin":
                self._json({"ok": False, "error": "forbidden"}, status=403)
                return
            self._json({"ok": True, "users": list_auth_users_public()})
            return

        if path == "/api/employee_logins":
            q = qs.get("q", [""])[0]
            email = (qs.get("email", [""])[0] or "").strip().lower() or None
            users = list_auth_users_public()
            if q:
                ql = str(q).strip().lower()
                users = [
                    row for row in users
                    if ql in str(row.get("email") or "").lower()
                    or ql in str(row.get("display_name") or "").lower()
                    or ql in str(row.get("role") or "").lower()
                ]
            sessions = list_active_sessions(email)
            activity = list_auth_activity(email, limit=100)
            self._json({
                "ok": True,
                "auth_enabled": auth_enabled(),
                "users": users,
                "sessions": sessions,
                "activity": activity,
            })
            return

        if path == "/api/auth/mfa/status":
            if not auth_enabled():
                self._json({"ok": False, "error": "auth_disabled"}, status=400)
                return
            session = self._require_session_auth()
            if not session:
                return
            try:
                self._json({"ok": True, **get_mfa_status(session.get("email"))})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return

        api_secret_authorized = bool(API_SECRET_KEY and self.headers.get("Authorization", "") == f"Bearer {API_SECRET_KEY}")
        if self._session_auth_required(path) and not api_secret_authorized and not self._require_session_auth():
            return

        if path in self._NON_API_AUTH_PATHS and not self._verify_request_origin():
            return

        # --- API Endpoints ---
        if path == "/latest_id":
            self._json({"latest_id": get_latest_id()})
            return

        if path == "/events":
            since = int(qs.get("since", [0])[0])
            limit = int(qs.get("limit", [500])[0])
            limit = max(1, min(limit, 5000))
            stream_id_param = qs.get("stream_id", [None])[0]
            stream_url_param = qs.get("stream_url", [None])[0]
            if stream_id_param:
                stream_id = int(stream_id_param)
                events = get_events_since(since, stream_id=stream_id, limit=limit)
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
                if collector_stream_id is not None and stream_id == collector_stream_id:
                    _process_event_side_effects(events, stream_id=stream_id)
            elif stream_url_param:
                # Spectator stream — filter to that stream, never ingest into company data
                stream_id = get_stream_id(stream_url_param)
                events = get_events_since(since, stream_id=stream_id, limit=limit)
            else:
                # Our stream — apply company side-effects (winner ingestion)
                status = collector_status()
                if status.get("running") and status.get("stream_url"):
                    stream_id = get_stream_id(status.get("stream_url"))
                    company_session_id = status.get("session_id")
                    if stream_id is not None and company_session_id and status.get("stream_mode") == "our_stream":
                        try:
                            update_company_session(int(company_session_id), stream_id=int(stream_id))
                        except Exception:
                            pass
                else:
                    # Collector stopped — fall back to last saved stream_url so we
                    # never pass stream_id=None (which would return ALL streams' events
                    # and incorrectly ingest competitor data into company records).
                    saved = load_collector_state()
                    saved_url = saved.get("stream_url")
                    stream_id = get_stream_id(saved_url) if saved_url else None
                events = get_events_since(since, stream_id=stream_id, limit=limit)
                # Only ingest when we have a confirmed stream identity
                if stream_id is not None:
                    _process_event_side_effects(events, stream_id=stream_id)
            self._json({"events": events, "has_more": len(events) >= limit})
            return

        if path == "/recent":
            limit = int(qs.get("limit", [200])[0])
            stream_id_param = qs.get("stream_id", [None])[0]
            stream_url_param = qs.get("stream_url", [None])[0]
            if stream_id_param:
                stream_id = int(stream_id_param)
            elif stream_url_param:
                stream_id = get_stream_id(stream_url_param)
            else:
                status = collector_status()
                if status.get("running") and status.get("stream_url"):
                    stream_id = get_stream_id(status.get("stream_url"))
                else:
                    saved = load_collector_state()
                    saved_url = saved.get("stream_url")
                    stream_id = get_stream_id(saved_url) if saved_url else None
            events = get_recent_events(limit, stream_id=stream_id)
            self._json({"events": events})
            return

        if path == "/api/session_stats":
            self._handle_session_stats(qs)
            return

        if path == "/api/current_lot":
            company_session = _resolve_company_session(qs.get("session_id", [None])[0])
            if company_session:
                lot = get_current_company_lot(company_session["id"])
                self._json({"ok": True, "session_id": company_session["id"], "lot": lot or {}})
            else:
                self._json({"ok": True, "session_id": None, "lot": {}})
            return

        if path == "/api/current_lot/products":
            self._handle_lot_products(qs)
            return

        if path == "/api/obs/current":
            self._handle_obs_current()
            return

        if path == "/obs/demo":
            _serve_static(self, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "OBS", "demo.html")))
            return

        if path == "/obs/overlay":
            _serve_static(self, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "OBS", "overlay2.html")))
            return

        if path == "/api/live_top_buyers":
            # Only show buyers from the CURRENT live session (collector must be running)
            status = collector_status()
            if not status.get("running") or not status.get("session_id"):
                self._json({"buyers": [], "recent_winners": []})
                return
            try:
                company_session = get_company_session(int(status["session_id"]))
            except Exception:
                company_session = None
            if not company_session:
                self._json({"buyers": [], "recent_winners": []})
                return
            sid = company_session["id"]
            self._json(_live_top_buyers_payload(sid))
            return

        if path == "/api/buyer_groups":
            company_session = _resolve_company_session(qs.get("session_id", [None])[0])
            rows = list_buyer_groups(session_id=company_session["id"] if company_session else None)
            self._json({"rows": rows})
            return

        if path == "/api/buyer_lines":
            group_id = qs.get("group_id", [None])[0]
            if not group_id:
                self._json({"rows": []})
                return
            rows = list_buyer_group_lines(int(group_id))
            self._json({"rows": rows})
            return

        if path == "/api/product_profit":
            company_session = _resolve_company_session(qs.get("session_id", [None])[0])
            rows = get_product_profit_rows(session_id=company_session["id"] if company_session else None)
            self._json({"rows": rows})
            return

        if path == "/api/active_items":
            company_session = _resolve_company_session(qs.get("session_id", [None])[0])
            if not company_session:
                self._json({"rows": []})
                return
            lot = get_current_company_lot(company_session["id"])
            rows = list_lot_items(lot["id"]) if lot else []
            rows = [row for row in rows if row.get("status") in ("open", "active", "queued")]
            self._json({"rows": rows})
            return

        if path == "/api/auction_results":
            session_id_param = qs.get("session_id", [None])[0]
            scope_param = (qs.get("scope", [""])[0] or "").strip().lower()
            q = (qs.get("q", [""])[0] or "").strip()
            limit_p = int(qs.get("limit", ["500"])[0])
            # If session_id provided use it; otherwise default to active session
            if session_id_param:
                sid = int(session_id_param)
            elif scope_param == "all":
                sid = None  # explicitly request all sessions
            else:
                current = _current_company_session()
                sid = int(current["id"]) if current else None
            rows = list_auction_results(session_id=sid, limit=limit_p)
            if q:
                ql = q.lower()
                rows = [
                    r for r in rows
                    if ql in (r.get("winner_username") or "").lower()
                    or ql in (r.get("product_name") or "").lower()
                    or ql in str(r.get("lot_number") or "").lower()
                ]
            total_revenue = round(sum(r.get("sale_price") or 0 for r in rows), 2)
            total_fees = round(sum(r.get("fees") or 0 for r in rows), 2)
            total_profit  = round(sum(r.get("profit") or 0 for r in rows), 2)
            self._json({
                "rows": rows,
                "total": len(rows),
                "total_revenue": total_revenue,
                "total_fees": total_fees,
                "total_profit": total_profit,
            })
            return

        if path == "/api/winner_assignment/state":
            session = _resolve_company_session(qs.get("session_id", [None])[0]) or _current_company_session()
            if not session:
                self._json({"ok": True, "session": None, "rows": []})
                return
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
                        merged_events.sort(key=lambda e: e.get("created_at") or "")
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
                limit=int(qs.get("limit", ["200"])[0]),
            )
            # Hide stale provisional winner tickets when the same Whatnot lot
            # already has a confirmed assignment. This keeps the live queue from
            # showing early $1 / placeholder winner events alongside the later
            # final close for the same lot.
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
            self._json({"ok": True, "session": session, "rows": rows})
            return

        if path == "/api/products":
            rows = []
            for r in list_products(active_only=False):
                rows.append({
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "barcode": r.get("barcode"),
                    "default_code": r.get("sku"),
                })
            self._json({"rows": rows})
            return

        if path == "/api/products_full":
            rows = []
            for r in list_products(active_only=False):
                rows.append({
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "barcode": r.get("barcode"),
                    "default_code": r.get("sku"),
                    "standard_price": r.get("cost_price"),
                    "list_price": r.get("retail_price"),
                    "qty_available": r.get("on_hand_qty"),
                    "image_url": _product_image_url(r),
                })
            self._json({"rows": rows})
            return

        if path == "/api/live_discovery":
            self._handle_live_discovery(qs)
            return

        if path == "/api/cookies_status":
            exists = os.path.isfile(COLLECTOR_COOKIES_PATH)
            size = os.path.getsize(COLLECTOR_COOKIES_PATH) if exists else 0
            count = 0
            if exists and size > 0:
                try:
                    import json
                    with open(COLLECTOR_COOKIES_PATH, "r") as f:
                        data = json.load(f)
                        count = len(data) if isinstance(data, list) else 1
                except Exception:
                    pass
            self._json({"ok": True, "exists": exists, "path": COLLECTOR_COOKIES_PATH, "size": size, "cookie_count": count})
            return

        if path == "/api/stream_status":
            status = collector_status()
            self._json({"ok": True, **status, "tiktok_operator": _tiktok_operator_status()})
            return

        if path == "/api/tiktok_extractor/lot_state":
            state = load_collector_state() or {}
            lot_state = state.get("tiktok_extractor_lot_state") or {}
            if not isinstance(lot_state, dict):
                lot_state = {}
            stream_url = (qs.get("stream_url", [None])[0] or "").strip() or None
            if stream_url:
                entry = lot_state.get(stream_url) or {}
                if not isinstance(entry, dict):
                    entry = {}
                self._json({"ok": True, "stream_url": stream_url, "next_lot": entry.get("next_lot"), "updated_at": entry.get("updated_at")})
                return
            self._json({"ok": True, "streams": lot_state})
            return

        if path == "/api/collectors/status":
            self._json({"ok": True, **collectors_status()})
            return

        if path == "/api/spectator/priority_status":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/fee_settings":
            try:
                settings = get_setting_map()
            except Exception:
                settings = {}
            fee_pct = float(settings.get("platform_fee_pct", 10.9))
            fixed_fee = float(settings.get("fixed_fee", 0.50))
            self._json({
                "ok": True,
                "fee_pct": fee_pct,
                "fixed_fee": fixed_fee,
                "description": f"{fee_pct}% of sale price + ${fixed_fee:.2f} fixed per transaction",
            })
            return

        if path == "/api/spectator/streams":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/spectator/insights":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/spectator/listings":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/spectator/status":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/spectator/users":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/spectator/user_detail":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/spectator/diagnostics":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/spectator/reconciled":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/facts/lots":
            stream_id_param = qs.get("stream_id", [None])[0]
            streamer_name_param = (qs.get("streamer_name", [None])[0] or "").strip()
            confidence_param = (qs.get("confidence", [None])[0] or "").strip()
            from_param = (qs.get("from", [None])[0] or "").strip()
            to_param = (qs.get("to", [None])[0] or "").strip()
            limit_param = int(qs.get("limit", ["200"])[0] or 200)
            refresh_mode = (qs.get("refresh", ["auto"])[0] or "auto").strip().lower()
            try:
                stream_id_value = None
                if stream_id_param not in (None, ""):
                    try:
                        stream_id_value = int(stream_id_param)
                    except Exception:
                        self._json({"ok": False, "error": "invalid stream_id"}, status=400)
                        return
                if refresh_mode not in {"0", "false", "off", "none"}:
                    if stream_id_value:
                        materialize_stream_facts(stream_id_value)
                    elif streamer_name_param:
                        materialize_streamer_facts(streamer_name_param, limit=5)
                    elif refresh_mode in {"all", "full"}:
                        materialize_recent_stream_facts(limit=25)
                    elif refresh_mode in {"recent"}:
                        materialize_recent_stream_facts(limit=5)
                    else:
                        # Broad fact queries should stay fast by default and rely on
                        # already materialized rows instead of refreshing many streams.
                        pass
                rows = list_fact_lots(
                    stream_id=stream_id_value,
                    streamer_name=streamer_name_param or None,
                    confidence=confidence_param or None,
                    from_ts=from_param or None,
                    to_ts=to_param or None,
                    limit=limit_param,
                )
                totals = {
                    "rows": len(rows),
                    "revenue": round(sum(float(r.get("sale_price") or 0) for r in rows), 2),
                    "high_confidence": sum(1 for r in rows if (r.get("confidence_label") or "") == "high"),
                    "medium_confidence": sum(1 for r in rows if (r.get("confidence_label") or "") == "medium"),
                    "low_confidence": sum(1 for r in rows if (r.get("confidence_label") or "") == "low"),
                }
                self._json({"ok": True, "rows": rows, "totals": totals})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/facts/buyers":
            stream_id_param = qs.get("stream_id", [None])[0]
            streamer_name_param = (qs.get("streamer_name", [None])[0] or "").strip()
            tier_param = (qs.get("tier", [None])[0] or "").strip()
            q_param = (qs.get("q", [None])[0] or "").strip()
            min_spend_param = float(qs.get("min_spend", ["0"])[0] or 0)
            limit_param = int(qs.get("limit", ["200"])[0] or 200)
            refresh_mode = (qs.get("refresh", ["auto"])[0] or "auto").strip().lower()
            try:
                stream_id_value = None
                if stream_id_param not in (None, ""):
                    try:
                        stream_id_value = int(stream_id_param)
                    except Exception:
                        self._json({"ok": False, "error": "invalid stream_id"}, status=400)
                        return
                if refresh_mode not in {"0", "false", "off", "none"}:
                    if stream_id_value:
                        materialize_stream_buyer_facts(stream_id_value)
                    elif streamer_name_param:
                        materialize_streamer_buyer_facts(streamer_name_param, limit=5)
                    elif refresh_mode in {"all", "full"}:
                        materialize_recent_stream_buyer_facts(limit=25)
                    elif refresh_mode in {"recent"}:
                        materialize_recent_stream_buyer_facts(limit=5)
                    else:
                        pass
                rows = list_fact_buyers(
                    stream_id=stream_id_value,
                    streamer_name=streamer_name_param or None,
                    tier=tier_param or None,
                    q=q_param or None,
                    min_spend=min_spend_param,
                    limit=limit_param,
                )
                totals = {
                    "rows": len(rows),
                    "buyers": sum(1 for r in rows if float(r.get("total_spend") or 0) > 0),
                    "whales": sum(1 for r in rows if (r.get("buyer_tier") or "") == "whale"),
                    "total_spend": round(sum(float(r.get("total_spend") or 0) for r in rows), 2),
                    "total_wins": sum(int(r.get("lots_won") or 0) for r in rows),
                    "total_messages": sum(int(r.get("chat_messages") or 0) for r in rows),
                    "cross_stream_buyers": sum(1 for r in rows if int(r.get("streams_seen") or 0) >= 2),
                }
                self._json({"ok": True, "rows": rows, "totals": totals})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/facts/products":
            stream_id_param = qs.get("stream_id", [None])[0]
            streamer_name_param = (qs.get("streamer_name", [None])[0] or "").strip()
            q_param = (qs.get("q", [None])[0] or "").strip()
            min_sold_param = int(qs.get("min_sold", ["0"])[0] or 0)
            limit_param = int(qs.get("limit", ["200"])[0] or 200)
            refresh_mode = (qs.get("refresh", ["auto"])[0] or "auto").strip().lower()
            try:
                stream_id_value = None
                if stream_id_param not in (None, ""):
                    try:
                        stream_id_value = int(stream_id_param)
                    except Exception:
                        self._json({"ok": False, "error": "invalid stream_id"}, status=400)
                        return
                if refresh_mode not in {"0", "false", "off", "none"}:
                    if stream_id_value:
                        materialize_stream_product_facts(stream_id_value)
                    elif streamer_name_param:
                        materialize_streamer_product_facts(streamer_name_param, limit=5)
                    elif refresh_mode in {"all", "full"}:
                        materialize_recent_stream_product_facts(limit=25)
                    elif refresh_mode in {"recent"}:
                        materialize_recent_stream_product_facts(limit=5)
                rows = list_fact_products(
                    stream_id=stream_id_value,
                    streamer_name=streamer_name_param or None,
                    q=q_param or None,
                    min_sold=min_sold_param,
                    limit=limit_param,
                )
                totals = {
                    "rows": len(rows),
                    "times_sold": sum(int(r.get("times_sold") or 0) for r in rows),
                    "total_revenue": round(sum(float(r.get("total_revenue") or 0) for r in rows), 2),
                    "avg_confidence": round(
                        sum(float(r.get("resolver_confidence_avg") or 0) for r in rows) / len(rows),
                        3,
                    ) if rows else 0,
                }
                self._json({"ok": True, "rows": rows, "totals": totals})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/intelligence/live":
            stream_id_param = qs.get("stream_id", [None])[0]
            if stream_id_param in (None, ""):
                self._json({"ok": False, "error": "stream_id required"}, status=400)
                return
            signal_type_param = (qs.get("signal_type", [None])[0] or "").strip()
            limit_param = int(qs.get("limit", ["40"])[0] or 40)
            refresh_mode = (qs.get("refresh", ["auto"])[0] or "auto").strip().lower()
            try:
                try:
                    stream_id_value = int(stream_id_param)
                except Exception:
                    self._json({"ok": False, "error": "invalid stream_id"}, status=400)
                    return
                if refresh_mode not in {"0", "false", "off", "none"}:
                    materialize_stream_intelligence(stream_id_value)
                rows = list_intelligence_signals(
                    stream_id_value,
                    signal_type=signal_type_param or None,
                    limit=limit_param,
                )
                grouped = {}
                for row in rows:
                    grouped.setdefault(row["signal_type"], []).append(row)
                self._json({"ok": True, "rows": rows, "grouped": grouped})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/users/cross_stream":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/users/audience":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/users/profile":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/users/target_buyers":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/competitors/title_quality":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/competitors/detection_feed":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path in {"/api/competitors/resolve_products", "/api/competitors/product_resolution"}:
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        # ── Session Detail ─────────────────────────────────────────────────
        import re as _re
        _sid_match = _re.match(r'^/api/sessions/(\d+)/detail$', path)
        if _sid_match:
            sid = int(_sid_match.group(1))
            try:
                session = get_company_session(sid)
                if not session:
                    self._json({"ok": False, "error": "Session not found"}, status=404)
                    return
                results = list_auction_results(session_id=sid, limit=2000)
                lots = list_company_lots(session_id=sid)
                groups = list_buyer_groups(session_id=sid)
                # Top buyers
                buyer_map = {}
                for r in results:
                    u = r.get("winner_username") or "?"
                    if u not in buyer_map:
                        buyer_map[u] = {"username": u, "lots": 0, "revenue": 0.0, "profit": 0.0}
                    buyer_map[u]["lots"] += 1
                    buyer_map[u]["revenue"] = round(buyer_map[u]["revenue"] + (r.get("sale_price") or 0), 2)
                    buyer_map[u]["profit"] = round(buyer_map[u]["profit"] + (r.get("profit") or 0), 2)
                top_buyers = sorted(buyer_map.values(), key=lambda x: -x["revenue"])[:10]
                # Unsold lots
                unsold = [l for l in lots if l.get("status") not in ("sold",)]
                # Timeline (revenue per lot for chart)
                timeline = [{"lot": r.get("lot_number"), "revenue": r.get("sale_price") or 0,
                             "profit": r.get("profit") or 0, "sold_at": r.get("sold_at"),
                             "winner": r.get("winner_username")} for r in reversed(results)]
                self._json({
                    "ok": True,
                    "session": {**session, "name": session.get("name"), "status": session.get("status"),
                                "started_at": session.get("started_at"), "ended_at": session.get("ended_at"),
                                "total_revenue": session.get("total_revenue"), "total_profit": session.get("total_profit"),
                                "total_lots_sold": session.get("total_lots_sold"), "total_products_sold": session.get("total_products_sold")},
                    "results": results,
                    "lots": lots,
                    "groups": groups,
                    "top_buyers": top_buyers,
                    "unsold": unsold,
                    "timeline": timeline,
                })
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        # ── Bulk create sale orders ────────────────────────────────────────
        if path == "/api/sessions/bulk_sale_orders":
            payload = self._read_json()
            group_ids = payload.get("group_ids") or []
            if not group_ids:
                self._json({"ok": False, "error": "group_ids required"}, status=400)
                return
            created, skipped, errors = 0, 0, []
            for gid in group_ids:
                try:
                    groups_data = list_buyer_groups(session_id=None)
                    grp = next((g for g in groups_data if int(g["id"]) == int(gid)), None)
                    if not grp:
                        errors.append(f"Group {gid} not found")
                        continue
                    if grp.get("sale_order_id"):
                        skipped += 1
                        continue
                    so = create_sale_order(
                        session_id=grp.get("session_id"),
                        customer_id=grp.get("customer_id"),
                        buyer_group_id=int(gid),
                        whatnot_buyer_username=grp.get("whatnot_buyer_username") or grp.get("winner_username"),
                        state="draft",
                        subtotal=grp.get("total_revenue") or 0,
                        total_amount=grp.get("total_revenue") or 0,
                    )
                    created += 1
                except Exception as exc:
                    errors.append(f"Group {gid}: {exc}")
            self._json({"ok": True, "created": created, "skipped": skipped, "errors": errors})
            return

        # ── CSV Exports ────────────────────────────────────────────────────
        import csv as _csv
        import io as _io

        if path == "/api/export/auction_results.csv":
            sid_p = qs.get("session_id", [None])[0]
            rows = list_auction_results(session_id=int(sid_p) if sid_p else None, limit=10000)
            buf = _io.StringIO()
            w = _csv.writer(buf)
            w.writerow(["ID","Session","Lot #","Winner","Product","SKU","Barcode","Sale Price","Cost","Fees","Profit","Margin %","Sold At"])
            for r in rows:
                w.writerow([r.get("id"), r.get("session_id"), r.get("lot_number"),
                            r.get("winner_username"), r.get("product_name"), r.get("sku"), r.get("barcode"),
                            r.get("sale_price"), r.get("cost_price"), r.get("fees"),
                            r.get("profit"), round(r.get("margin_pct") or 0, 1), r.get("sold_at")])
            data = buf.getvalue().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=auction_results.csv")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/export/orders.csv":
            sid_p = qs.get("session_id", [None])[0]
            rows = list_buyer_groups(session_id=int(sid_p) if sid_p else None)
            buf = _io.StringIO()
            w = _csv.writer(buf)
            w.writerow(["ID","Session","Buyer","Revenue","Cost","Profit","Sale Order","Lots"])
            for r in rows:
                w.writerow([r.get("id"), r.get("session_id"),
                            r.get("whatnot_buyer_username") or r.get("winner_username"),
                            r.get("total_revenue"), r.get("total_cost"), r.get("total_profit"),
                            r.get("sale_order_id") or "", r.get("lot_count") or ""])
            data = buf.getvalue().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=buyer_orders.csv")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/export/reports.csv":
            sid_p = qs.get("session_id", [None])[0]
            rows = get_product_profit_rows(session_id=int(sid_p) if sid_p else None)
            buf = _io.StringIO()
            w = _csv.writer(buf)
            w.writerow(["Product","SKU","Barcode","Session","Times Sold","Avg Price","Revenue","Cost","Profit","Avg Margin %"])
            for r in rows:
                w.writerow([r.get("product_name"), r.get("sku"), r.get("barcode"),
                            r.get("session_name") or r.get("session_id_name"),
                            r.get("times_sold"), round(r.get("avg_winning_price") or 0, 2),
                            r.get("total_revenue"), r.get("total_cost"), r.get("total_profit"),
                            round(r.get("avg_margin") or 0, 1)])
            data = buf.getvalue().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=product_report.csv")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/export/users.csv":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        # ── Competitor Pricing Intelligence ────────────────────────────────
        if path == "/api/analytics/competitor_prices":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        # ── Alerts ─────────────────────────────────────────────────────────
        if path == "/api/alerts":
            try:
                settings = get_setting_map()
                margin_threshold = float(settings.get("alert_margin_threshold") or 0)
                buyer_lots_threshold = int(settings.get("alert_buyer_lots_threshold") or 0)
                alerts = []
                # Check margin on current session
                local_session = _current_company_session()
                if local_session and margin_threshold > 0:
                    rev = local_session.get("total_revenue") or 0
                    prof = local_session.get("total_profit") or 0
                    margin = (prof / rev * 100) if rev else 0
                    if margin < margin_threshold and rev > 0:
                        alerts.append({
                            "type": "margin", "severity": "warning",
                            "message": f"Session margin {margin:.1f}% is below threshold {margin_threshold:.0f}%",
                            "value": round(margin, 1), "threshold": margin_threshold,
                        })
                # Check buyer lot concentration
                if local_session and buyer_lots_threshold > 0:
                    results = list_auction_results(session_id=local_session["id"], limit=2000)
                    buyer_map = {}
                    for r in results:
                        u = r.get("winner_username") or "?"
                        buyer_map[u] = buyer_map.get(u, 0) + 1
                    for u, cnt in buyer_map.items():
                        if cnt >= buyer_lots_threshold:
                            alerts.append({
                                "type": "buyer_concentration", "severity": "info",
                                "message": f"@{u} has won {cnt} lots this session",
                                "username": u, "lots": cnt, "threshold": buyer_lots_threshold,
                            })
                # Low stock sold
                low_stock_prods = list_products(low_stock_only=True)
                if low_stock_prods:
                    names = [p.get("name", "") for p in low_stock_prods[:5]]
                    alerts.append({
                        "type": "low_stock", "severity": "warning",
                        "message": f"{len(low_stock_prods)} product(s) at or below low-stock threshold: {', '.join(names[:3])}{'…' if len(names) > 3 else ''}",
                        "count": len(low_stock_prods),
                    })
                self._json({"ok": True, "alerts": alerts, "count": len(alerts)})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/alerts/settings":
            try:
                settings = get_setting_map()
                self._json({
                    "ok": True,
                    "margin_threshold": float(settings.get("alert_margin_threshold") or 0),
                    "buyer_lots_threshold": int(settings.get("alert_buyer_lots_threshold") or 0),
                })
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/analytics/businesses":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/analytics/market_pulse":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/analytics/overview":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/sidecar/status":
            self._json({"ok": True, **get_sidecar_status()})
            return

        if path == "/api/sidecar/overview_summary":
            self._json(get_sidecar_overview_summary())
            return

        if path == "/api/sidecar/active_session_summary":
            account = (qs.get("account", [OUR_WHATNOT_ACCOUNT])[0] or OUR_WHATNOT_ACCOUNT).strip() or OUR_WHATNOT_ACCOUNT
            self._json(get_sidecar_active_session_summary(account=account))
            return

        if path == "/api/sidecar/pending_winners_summary":
            session_raw = (qs.get("session_id", [""])[0] or "").strip()
            session_id = int(session_raw) if session_raw else None
            self._json(get_sidecar_pending_winners_summary(session_id=session_id))
            return

        if path == "/api/sidecar/auction_results_summary":
            session_raw = (qs.get("session_id", [""])[0] or "").strip()
            session_id = int(session_raw) if session_raw else None
            self._json(get_sidecar_auction_results_summary(session_id=session_id))
            return

        if path == "/api/sidecar/inventory_summary":
            self._json(get_sidecar_inventory_summary())
            return

        if path == "/api/sidecar/parity_report":
            tables = [value.strip() for value in qs.get("table", []) if value.strip()]
            self._json(get_sidecar_parity_report(table_names=tables or None))
            return

        if path == "/api/company/intelligence":
            try:
                data = get_company_livestream_intelligence()
                self._json({"ok": True, **data})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path in ("/api/analytics/trends", "/api/analytics/buyer_overlap"):
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/collector/health":
            stream_id_param = qs.get("stream_id", [None])[0]
            try:
                sid = int(stream_id_param) if stream_id_param else None
            except ValueError:
                sid = None
            health = get_collector_health(stream_id=sid)
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
            self._json({
                "ok": True,
                "checked_at": now,
                "last_events": health,
                "ages_minutes": {k: _age_minutes(v) for k, v in health.items() if k != "total_events"},
                "warnings": warnings,
                "healthy": len(warnings) == 0,
            })
            return

        if path == "/api/failed_ingests":
            include_resolved = qs.get("resolved", ["0"])[0] == "1"
            self._json({"ok": True, "records": get_failed_ingests(include_resolved=include_resolved)})
            return

        if path == "/api/system/diagnostics":
            try:
                log_limit = int(qs.get("log_limit", ["200"])[0] or 200)
            except ValueError:
                log_limit = 200
            self._json(_build_system_diagnostics(log_limit=log_limit))
            return

        if path == "/api/session_history":
            try:
                rows = []
                for row in list_company_sessions(OUR_WHATNOT_ACCOUNT, limit=15):
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
                        "show_id": row.get("show_id"),
                    })
                self._json({"ok": True, "sessions": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/history/company_sessions":
            try:
                limit = int(qs.get("limit", ["15"])[0])
            except (TypeError, ValueError):
                limit = 15
            try:
                rows = get_company_stream_history(OUR_WHATNOT_ACCOUNT, limit=limit)
                self._json({"ok": True, "sessions": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/history/company_detail":
            stream_id_param = qs.get("stream_id", [None])[0]
            if not stream_id_param:
                self._json({"ok": False, "error": "stream_id required"}, status=400)
                return
            try:
                detail = get_company_stream_detail(int(stream_id_param))
                report_rows = []
                usernames = sorted({
                    (row.get("winner_username") or "").strip()
                    for row in detail.get("winners", [])
                    if (row.get("winner_username") or "").strip()
                })
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
                        "item_count": item_count,
                        "product_names": product_name,
                        "sold_at": row.get("sold_at"),
                        "profile_made": bool(partner),
                        "profile_name": partner.get("display_name") if partner else None,
                        "profile_created_at": partner.get("created_at") if partner else None,
                        "sale_order_made": username.lower() in sale_order_users if username else False,
                    })
                detail["report_rows"] = report_rows
                self._json({"ok": True, **detail})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/analytics/chat_signals":
            stream_id_param = qs.get("stream_id", [None])[0]
            try:
                sid = int(stream_id_param) if stream_id_param and str(stream_id_param) != "0" else None
                data = get_analytics_chat_signals(stream_id=sid)
                self._json({"ok": True, **data})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/analytics/timing":
            streamer_name_param = qs.get("streamer_name", [None])[0]
            try:
                data = get_analytics_timing(
                    streamer_name=streamer_name_param if streamer_name_param else None
                )
                self._json({"ok": True, **data})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/analytics/products_intel":
            streamer_name_param = qs.get("streamer_name", [None])[0]
            try:
                data = get_analytics_products_intel(
                    streamer_name=streamer_name_param if streamer_name_param else None
                )
                self._json({"ok": True, **data})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/analytics/shop_products":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/analytics/shop_scrape_status":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        # ---------------------------------------------------------------
        # Lots endpoints
        # ---------------------------------------------------------------

        if path == "/api/lots":
            session_id_param = qs.get("session_id", [None])[0]
            status_param = qs.get("status", [None])[0]
            try:
                session = _resolve_company_session(session_id_param)
                rows = list_company_lots(session_id=session["id"] if session else None, status=status_param or None, limit=500)
                for row in rows:
                    row["session_id_name"] = row.get("session_name")
                self._json({"ok": True, "rows": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/lots/products":
            lot_id_param = qs.get("lot_id", [None])[0]
            if not lot_id_param:
                self._json({"ok": False, "error": "lot_id required"}, status=400)
                return
            try:
                rows = list_lot_items(int(lot_id_param))
                for row in rows:
                    row["cost"] = row.get("unit_cost")
                    row["on_hand_qty"] = row.get("on_hand_qty")
                self._json({"ok": True, "rows": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        # ---------------------------------------------------------------
        # Sale Orders endpoints
        # ---------------------------------------------------------------

        if path == "/api/packing_scanner/order":
            tracking = (qs.get("tracking", [""])[0] or "").strip()
            if not tracking:
                self._json({"ok": False, "error": "tracking required"}, status=400)
                return
            try:
                order = _lookup_packing_scanner_order(tracking)
                if not order:
                    self._json({"ok": False, "error": "order_not_found"}, status=404)
                    return
                self._json({"ok": True, "order": order, "events": _list_packing_scanner_events(tracking)})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/packing_scanner/session":
            session_id_param = qs.get("session_id", [None])[0]
            try:
                summary = _packing_scanner_session_summary(session_id=session_id_param)
                self._json({"ok": True, "session": summary})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/sale_orders":
            session_id_param = qs.get("session_id", [None])[0]
            q = (qs.get("q", [""])[0] or "").strip()
            source = (qs.get("source", [""])[0] or "").strip().lower()
            status = (qs.get("status", [""])[0] or "").strip().lower()
            fast = (qs.get("summary", ["0"])[0] or "").strip().lower() in ("1", "true", "yes")
            try:
                limit_param = max(1, min(int(qs.get("limit", ["250"])[0] or 250), 5000))
            except Exception:
                limit_param = 250
            try:
                offset_param = max(0, int(qs.get("offset", ["0"])[0] or 0))
            except Exception:
                offset_param = 0
            try:
                if fast:
                    rows = list_sale_orders_fast(
                        session_id=session_id_param or None,
                        q=q or None,
                        order_source=source or None,
                        status=status or None,
                        limit=limit_param,
                        offset=offset_param,
                    )
                    summary = sale_order_list_summary(
                        session_id=session_id_param or None,
                        q=q or None,
                        order_source=source or None,
                        status=status or None,
                    )
                    base_summary = sale_order_list_summary(
                        session_id=session_id_param or None,
                        q=q or None,
                        order_source=source or None,
                    )
                else:
                    rows = list_sale_orders(session_id=session_id_param or None, q=q or None, order_source=source or None)
                    summary = None
                    base_summary = None
                def _sale_order_financial_final(row):
                    return (
                        row.get("state") != "cancel"
                        and (
                            str(row.get("fulfillment_status") or "").strip().lower() == "delivered"
                            or str(row.get("tracking_status") or "").strip().lower() == "delivered"
                            or bool(str(row.get("delivered_at") or "").strip())
                        )
                    )

                for r in rows:
                    linked_revenue = float(r.get("linked_revenue") or 0)
                    line_revenue = float(r.get("line_revenue") or r.get("subtotal") or r.get("total_amount") or 0)
                    order_revenue = linked_revenue or line_revenue
                    order_cost = float(r.get("linked_cost") or r.get("line_cost") or 0)
                    order_fees = float(r.get("linked_fees") or r.get("line_fees") or 0)
                    linked_profit = r.get("linked_profit")
                    order_profit = float(linked_profit) if linked_profit not in (None, "") else float(r.get("line_profit") or 0)
                    if not linked_revenue and r.get("line_profit") not in (None, ""):
                        order_profit = float(r.get("line_profit") or 0)
                    order_margin_pct = float(r.get("linked_margin_pct") or 0)
                    if not order_margin_pct and order_revenue:
                        order_margin_pct = round((order_profit / order_revenue) * 100.0, 1)
                    if not _sale_order_financial_final(r):
                        order_revenue = 0.0
                        order_cost = 0.0
                        order_fees = 0.0
                        order_profit = 0.0
                        order_margin_pct = 0.0
                    r["name"] = r.get("order_number")
                    r["date_order"] = r.get("ordered_at")
                    r["partner_id_name"] = r.get("display_name")
                    r["whatnot_session_id"] = r.get("session_id")
                    r["whatnot_session_id_name"] = r.get("session_name")
                    r["amount_untaxed"] = r.get("subtotal")
                    r["amount_total"] = r.get("total_amount")
                    r["linked_revenue"] = order_revenue
                    r["linked_cost"] = order_cost
                    r["linked_fees"] = order_fees
                    r["linked_profit"] = order_profit
                    r["linked_margin_pct"] = order_margin_pct
                    r["order_revenue"] = order_revenue
                    r["order_cost"] = order_cost
                    r["order_fees"] = order_fees
                    r["order_profit"] = order_profit
                    r["order_margin_pct"] = order_margin_pct
                    r["tracking_url"] = _tracking_url(r.get("tracking_carrier"), r.get("tracking_number"))
                confirmed_rows = [r for r in rows if _sale_order_financial_final(r)]
                draft_rows = [r for r in rows if r.get("state") in ("draft", "sent")]
                cancel_rows = [r for r in rows if r.get("state") == "cancel"]
                packed_rows = [r for r in rows if r.get("fulfillment_status") == "packed"]
                shipped_rows = [r for r in rows if r.get("fulfillment_status") == "shipped"]
                paid_rows = [r for r in rows if r.get("payment_status") == "paid"]
                if summary:
                    total = summary["total_amount"]
                    confirmed_count = summary["confirmed_count"]
                    draft_count = summary["draft_count"]
                    cancel_count = summary["cancel_count"]
                    packed_count = summary["packed_count"]
                    shipped_count = summary["shipped_count"]
                    paid_count = summary["paid_count"]
                    confirmed_amount = summary["confirmed_amount"]
                    draft_amount = summary["draft_amount"]
                    cancel_amount = summary["cancel_amount"]
                else:
                    total = round(sum(r.get("amount_total") or 0 for r in rows), 2)
                    confirmed_count = len(confirmed_rows)
                    draft_count = len(draft_rows)
                    cancel_count = len(cancel_rows)
                    packed_count = len(packed_rows)
                    shipped_count = len(shipped_rows)
                    paid_count = len(paid_rows)
                    confirmed_amount = round(sum(r.get("amount_total") or 0 for r in confirmed_rows), 2)
                    draft_amount = round(sum(r.get("amount_total") or 0 for r in draft_rows), 2)
                    cancel_amount = round(sum(r.get("amount_total") or 0 for r in cancel_rows), 2)
                confirmed_revenue = round(sum(r.get("linked_revenue") or 0 for r in confirmed_rows), 2)
                confirmed_cost = round(sum(r.get("linked_cost") or 0 for r in confirmed_rows), 2)
                confirmed_fees = round(sum(r.get("linked_fees") or 0 for r in confirmed_rows), 2)
                confirmed_profit = round(sum(r.get("linked_profit") or 0 for r in confirmed_rows), 2)
                confirmed_results_count = sum(int(r.get("linked_results_count") or 0) for r in confirmed_rows)
                confirmed_products_sold = sum(int(r.get("linked_products_sold") or 0) for r in confirmed_rows)
                confirmed_margin_pct = round((confirmed_profit / confirmed_revenue) * 100.0, 1) if confirmed_revenue else 0.0
                cancel_revenue = round(sum(r.get("linked_revenue") or 0 for r in cancel_rows), 2)
                cancel_cost = round(sum(r.get("linked_cost") or 0 for r in cancel_rows), 2)
                cancel_fees = round(sum(r.get("linked_fees") or 0 for r in cancel_rows), 2)
                cancel_profit = round(sum(r.get("linked_profit") or 0 for r in cancel_rows), 2)
                self._json({
                    "ok": True,
                    "rows": rows,
                    "limit": limit_param if fast else None,
                    "offset": offset_param if fast else 0,
                    "total_count": summary["total_count"] if summary else len(rows),
                    "has_more": (offset_param + len(rows)) < summary["total_count"] if summary else False,
                    "base_summary": base_summary,
                    "total_amount": total,
                    "confirmed_count": confirmed_count,
                    "draft_count": draft_count,
                    "cancel_count": cancel_count,
                    "packed_count": packed_count,
                    "shipped_count": shipped_count,
                    "paid_count": paid_count,
                    "confirmed_amount": confirmed_amount,
                    "draft_amount": draft_amount,
                    "cancel_amount": cancel_amount,
                    "confirmed_revenue": confirmed_revenue,
                    "confirmed_cost": confirmed_cost,
                    "confirmed_fees": confirmed_fees,
                    "confirmed_profit": confirmed_profit,
                    "confirmed_margin_pct": confirmed_margin_pct,
                    "confirmed_results_count": confirmed_results_count,
                    "confirmed_products_sold": confirmed_products_sold,
                    "cancel_revenue": cancel_revenue,
                    "cancel_cost": cancel_cost,
                    "cancel_fees": cancel_fees,
                    "cancel_profit": cancel_profit,
                })
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/in_house_sales":
            q = (qs.get("q", [""])[0] or "").strip()
            try:
                rows = list_in_house_sales(q=q or None, limit=1000)
                summary = in_house_sales_summary()
                employees = list_employee_accounts(q=q or None, limit=200)
                self._json({"ok": True, "rows": rows, "employees": employees, **summary})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/in_house_orders":
            status = (qs.get("status", [""])[0] or "").strip()
            token = (qs.get("token", [""])[0] or "").strip()
            employee_id = (qs.get("employee_id", [""])[0] or "").strip()
            try:
                rows = list_in_house_orders(
                    status=status or None,
                    token=token or None,
                    employee_id=int(employee_id) if employee_id else None,
                    limit=300,
                )
                self._json({"ok": True, "rows": rows, "summary": in_house_orders_summary()})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                msg = str(exc)
                self._json({"ok": False, "error": msg}, status=503 if "company_db_postgres_runtime_required" in msg else 500)
            return

        if path == "/api/in_house_orders/detail":
            order_id = (qs.get("id", [""])[0] or "").strip()
            if not order_id:
                self._json({"ok": False, "error": "id required"}, status=400)
                return
            try:
                order = get_in_house_order(int(order_id))
                if not order:
                    self._json({"ok": False, "error": "order not found"}, status=404)
                    return
                self._json({"ok": True, "order": order})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/in_house_buyers":
            q = (qs.get("q", [""])[0] or "").strip()
            try:
                rows = list_in_house_buyer_profiles(q=q or None, limit=200)
                self._json({"ok": True, "rows": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/internal_pos/me":
            token = (qs.get("token", [""])[0] or "").strip()
            if not token:
                self._json({"ok": True, "guest": True, "employee": {"employee_name": "Guest Self Checkout", "role": "guest"}})
                return
            try:
                employee = get_employee_pos_token(token)
                if not employee:
                    self._json({"ok": False, "error": "invalid employee POS token"}, status=404)
                    return
                self._json({"ok": True, "employee": employee})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/internal_pos/products":
            q = (qs.get("q", [""])[0] or "").strip()
            code = (qs.get("code", [""])[0] or "").strip()
            try:
                rows = list_internal_pos_products(q=q or None, code=code or None, limit=80)
                self._json({"ok": True, "rows": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/internal_pos/buyers":
            q = (qs.get("q", [""])[0] or "").strip()
            try:
                rows = list_in_house_buyer_profiles(q=q or None, limit=50)
                self._json({"ok": True, "rows": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/internal_pos/orders/mine":
            token = (qs.get("token", [""])[0] or "").strip()
            if not token:
                self._json({"ok": False, "error": "token required"}, status=400)
                return
            try:
                rows = list_in_house_orders(token=token, limit=100)
                self._json({"ok": True, "rows": rows, "summary": in_house_orders_summary()})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/internal_pos/orders/history":
            employee_id = (qs.get("employee_id", [""])[0] or "").strip()
            buyer_name = (qs.get("buyer_name", [""])[0] or "").strip()
            buyer_phone = (qs.get("buyer_phone", [""])[0] or "").strip()
            buyer_email = (qs.get("buyer_email", [""])[0] or "").strip()
            try:
                rows = list_in_house_orders(
                    employee_id=int(employee_id) if employee_id else None,
                    buyer_name=buyer_name or None,
                    limit=100,
                )
                if buyer_name:
                    rows = [row for row in rows if _guest_in_house_order_access_allowed(row, buyer_name=buyer_name, buyer_phone=buyer_phone, buyer_email=buyer_email)]
                self._json({"ok": True, "rows": rows, "summary": in_house_orders_summary()})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/internal_pos/orders/detail":
            order_id = (qs.get("id", [""])[0] or "").strip()
            buyer_name = (qs.get("buyer_name", [""])[0] or "").strip()
            buyer_phone = (qs.get("buyer_phone", [""])[0] or "").strip()
            buyer_email = (qs.get("buyer_email", [""])[0] or "").strip()
            if not order_id or not buyer_name:
                self._json({"ok": False, "error": "id and buyer_name required"}, status=400)
                return
            try:
                order = get_in_house_order(int(order_id))
                if not order or not _guest_in_house_order_access_allowed(order, buyer_name=buyer_name, buyer_phone=buyer_phone, buyer_email=buyer_email):
                    self._json({"ok": False, "error": "order not found"}, status=404)
                    return
                self._json({"ok": True, "order": order})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/company/mega_dashboard":
            try:
                self._json(get_mega_dashboard_summary())
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions":
            try:
                limit = int(qs.get("limit", [80])[0] or 80)
                include_rows = (qs.get("summary", ["0"])[0] or "").strip().lower() not in {"1", "true", "yes"}
                self._json({"ok": True, "rows": _list_tiktok_go_live_sessions(limit=limit, include_rows=include_rows)})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/next_sequence":
            try:
                self._json({"ok": True, "sequence": _next_tiktok_go_live_sequence()})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path in {"/api/tiktok_live_sessions/export_all.csv", "/api/export/tiktok_go_live_sessions.csv"}:
            try:
                limit = int(qs.get("limit", [1000])[0] or 1000)
                csv_text, row_count, session_count = _build_tiktok_go_live_all_sessions_csv(limit=limit)
                payload = csv_text.encode("utf-8-sig")
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                filename = f"tiktok-go-live-all-sessions-{stamp}.csv"
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("X-Export-Rows", str(row_count))
                self.send_header("X-Export-Sessions", str(session_count))
                self.send_header("Content-Length", str(len(payload)))
                _send_security_headers(self)
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/search_order":
            order_id = (qs.get("order_id", [""])[0] or "").strip()
            if not order_id:
                self._json({"ok": False, "error": "order_id required"}, status=400)
                return
            try:
                rows = list_sale_orders_fast(order_source="tiktok_live", q=order_id, limit=25)
                matches = []
                for order in rows:
                    session_id = int(order.get("session_id") or 0)
                    session = get_company_session(session_id) if session_id else None
                    matches.append({
                        "order_id": order.get("id"),
                        "order_number": order.get("order_number") or "",
                        "external_order_ref": order.get("external_order_ref") or "",
                        "session_id": session_id or None,
                        "session_key": f"server-go-live-{session_id}" if session_id else "",
                        "session_name": (session or {}).get("name") or order.get("session_name") or "",
                        "lot_no": _extract_tiktok_live_lot_number_from_order(order),
                        "buyer": order.get("display_name") or order.get("whatnot_buyer_username") or "",
                        "total_amount": order.get("total_amount") or order.get("subtotal") or 0,
                        "payment_status": order.get("payment_status") or "",
                        "fulfillment_status": order.get("fulfillment_status") or "",
                        "ordered_at": order.get("ordered_at") or order.get("created_at") or "",
                    })
                self._json({"ok": True, "matches": matches, "count": len(matches)})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/detail":
            session_id_param = (qs.get("session_id", [""])[0] or "").strip()
            if not session_id_param:
                self._json({"ok": False, "error": "session_id required"}, status=400)
                return
            try:
                session = get_company_session(int(session_id_param))
                if not session or not _is_tiktok_go_live_session_row(session):
                    self._json({"ok": False, "error": "session_not_found"}, status=404)
                    return
                self._json({"ok": True, "session": _serialize_tiktok_go_live_session(session, include_rows=True)})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/active":
            try:
                fast = (qs.get("fast", ["0"])[0] or "").strip().lower() in {"1", "true", "yes"}
                sync = (qs.get("sync", ["0"])[0] or "").strip().lower() in {"1", "true", "yes"}
                self._json({
                    "ok": True,
                    "session": _get_active_tiktok_go_live_session(live_api_enrich=(sync or not fast)),
                    "fast": fast and not sync,
                })
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/google_sheet_backup_status":
            session_id_param = (qs.get("session_id", [""])[0] or "").strip()
            if not session_id_param:
                self._json({"ok": False, "error": "session_id required"}, status=400)
                return
            try:
                self._json(get_tiktok_live_sheet_backup_status(int(session_id_param)))
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/google_sheets/full_backup_status":
            try:
                self._json(get_full_workbook_backup_status())
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_labels/artifacts":
            session_key = qs.get("session_key", [""])[0]
            try:
                artifact = _public_tiktok_label_artifact(_latest_tiktok_label_artifact(session_key))
                self._json({"ok": True, "artifact": artifact})
            except Exception as exc:
                print(f"[tiktok_live_labels] artifact lookup failed for {session_key!r}: {exc}")
                self._json({"ok": True, "artifact": None, "warning": "artifact_lookup_unavailable"})
            return

        if path == "/api/tiktok_live_labels/artifact":
            artifact = _get_tiktok_label_artifact(qs.get("id", [""])[0])
            if not artifact:
                self._json({"ok": False, "error": "label_pdf_not_found"}, status=404)
                return
            safe_name = _safe_tiktok_label_filename(artifact.get("filename"))
            payload = artifact.get("output_pdf") or b""
            if not payload:
                self._json({"ok": False, "error": "label_pdf_payload_missing"}, status=404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
            self.send_header("Cache-Control", "private, max-age=31536000")
            self.send_header("Content-Length", str(len(payload)))
            _send_security_headers(self)
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/api/picklists":
            session_id_param = qs.get("session_id", [None])[0]
            try:
                rows = list_pick_lists(session_id=int(session_id_param) if session_id_param else None)
                self._json({"ok": True, "pick_lists": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/picklists/detail":
            pl_id = qs.get("id", [None])[0]
            if not pl_id:
                self._json({"ok": False, "error": "id required"}, status=400)
                return
            try:
                pl = get_pick_list(int(pl_id))
                items = list_pick_list_items(int(pl_id))
                # Re-match product names from current auction results so any
                # edits made in Auction Results are reflected here, not frozen.
                if pl:
                    session_id_for_match = pl.get("session_id")
                    auction_rows = list_auction_results(
                        session_id=int(session_id_for_match) if session_id_for_match else None,
                        limit=9999,
                    )
                    # Build lot → auction result lookup (by lot_number)
                    lot_lookup = {}
                    for ar in auction_rows:
                        ln = str(ar.get("lot_number") or "").strip()
                        if ln and ln not in lot_lookup:
                            lot_lookup[ln] = ar
                    # Update each item with fresh auction result data
                    for item in items:
                        ln = str(item.get("lot_number") or "").strip()
                        ar = lot_lookup.get(ln)
                        if ar:
                            item["product_name"] = ar.get("product_name") or item.get("product_name") or "Unknown"
                            item["barcode"] = ar.get("barcode") or item.get("barcode") or ""
                            item["sku"] = ar.get("sku") or item.get("sku") or ""
                            item["sale_price"] = ar.get("sale_price") if ar.get("sale_price") is not None else item.get("sale_price", 0)
                            item["winner_username"] = ar.get("winner_username") or item.get("username")
                            item["matched"] = 1
                self._json({"ok": True, "pick_list": pl, "items": items})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_picklist":
            session_id_param = qs.get("session_id", [None])[0]
            ordered_date = (qs.get("ordered_date", [""])[0] or "").strip()
            try:
                self._json(_build_sale_order_picklist_payload(
                    int(session_id_param) if session_id_param else None,
                    order_source="tiktok_live",
                    ordered_date=ordered_date or None,
                ))
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/sale_orders/lines":
            order_id_param = qs.get("order_id", [None])[0]
            if not order_id_param:
                self._json({"ok": False, "error": "order_id required"}, status=400)
                return
            try:
                local_rows = list_sale_order_lines(int(order_id_param))
                rows = []
                for r in local_rows:
                    rows.append({
                        "id": r["id"],
                        "product_id": r.get("product_id"),
                        "product_id_name": r.get("product_name"),
                        "name": r.get("description"),
                        "barcode": r.get("barcode"),
                        "sku": r.get("sku"),
                        "unit_cost": r.get("unit_cost"),
                        "retail_price": r.get("retail_price"),
                        "product_uom_qty": r.get("qty"),
                        "price_unit": r.get("unit_price"),
                        "price_subtotal": r.get("subtotal"),
                        "whatnot_inventory_applied": r.get("inventory_applied"),
                        "lot_number": r.get("lot_number"),
                        "sold_at": r.get("sold_at"),
                        "buyer_username": r.get("buyer_username"),
                        "buyer_line_product_name": r.get("buyer_line_product_name"),
                        "on_hand_qty": r.get("on_hand_qty"),
                    })
                self._json({"ok": True, "rows": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        # ---------------------------------------------------------------
        # Customers endpoints
        # ---------------------------------------------------------------

        if path == "/api/customers":
            q = (qs.get("q", [""])[0] or "").strip()
            has_orders_only = (qs.get("has_orders", ["0"])[0] or "").strip().lower() in {"1", "true", "yes"}
            platform = (qs.get("platform", ["all"])[0] or "all").strip().lower()
            limit_raw = qs.get("limit", [None])[0]
            offset_raw = qs.get("offset", ["0"])[0]
            limit_param = None
            try:
                if limit_raw not in (None, "", "all"):
                    limit_param = max(1, min(int(limit_raw or 100), 1000))
            except Exception:
                limit_param = 100
            try:
                offset_param = max(0, int(offset_raw or 0))
            except Exception:
                offset_param = 0
            try:
                rows = list_customers(q=q or None, has_orders_only=has_orders_only, platform=platform, limit=limit_param, offset=offset_param)
                for r in rows:
                    r["name"] = r.get("display_name")
                self._json({
                    "ok": True,
                    "rows": rows,
                    "limit": limit_param,
                    "offset": offset_param,
                    "has_more": bool(limit_param and len(rows) >= limit_param),
                })
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/customers/reviews/status":
            self._json({"ok": False, "error": "reviews_feature_removed"}, status=410)
            return

        if path == "/api/customers/reviews":
            self._json({"ok": False, "error": "reviews_feature_removed"}, status=410)
            return

        if path == "/api/customers/detail":
            customer_id_param = qs.get("customer_id", [None])[0]
            if not customer_id_param:
                self._json({"ok": False, "error": "customer_id required"}, status=400)
                return
            try:
                customer = get_customer(int(customer_id_param))
                if not customer:
                    self._json({"ok": False, "error": "customer_not_found"}, status=404)
                    return
                customer["name"] = customer.get("display_name")
                analytics = get_customer_analytics(int(customer_id_param))
                self._json({"ok": True, "customer": customer, **analytics})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/customers/profile_lookup":
            customer_id_param = qs.get("customer_id", [None])[0]
            username_p = (qs.get("username", [None])[0] or "").strip()
            if not customer_id_param and not username_p:
                self._json({"ok": False, "error": "customer_id or username required"}, status=400)
                return
            try:
                def _extract_tiktok_order_id(order):
                    raw = str(order.get("external_order_ref") or "").strip()
                    if not raw:
                        return None
                    if raw.lower().startswith("tiktok_live:"):
                        parts = [part for part in raw.split(":") if part]
                        return parts[-2] if len(parts) >= 3 else None
                    if raw.lower().startswith("tiktok_shop:"):
                        parts = [part for part in raw.split(":") if part]
                        return parts[-1] if len(parts) >= 2 else None
                    return raw if raw.isdigit() else None

                def _extract_order_products(order):
                    products = []
                    for line in (order.get("lines") or []):
                        name = str(line.get("description") or line.get("product_name") or line.get("name") or "").strip()
                        if name:
                            products.append(name)
                    if not products:
                        joined = str(order.get("product_names") or "").strip()
                        if joined:
                            products = [part.strip() for part in joined.split(",") if part.strip()]
                    return products

                customer = None
                if customer_id_param:
                    customer = get_customer(int(customer_id_param))
                if not customer and username_p:
                    customer = get_customer_by_username(username_p)
                analytics = {"sessions": [], "products": [], "summary": {}}
                orders = []
                if customer:
                    customer["name"] = customer.get("display_name")
                    analytics = get_customer_analytics(int(customer["id"]))
                    orders = list_customer_orders(int(customer["id"]))
                    customer["identities"] = analytics.get("identities") or []
                    for r in orders:
                        r["name"] = r.get("order_number")
                        r["date_order"] = r.get("ordered_at")
                        r["amount_total"] = r.get("total_amount")
                        r["whatnot_session_id"] = r.get("session_id")
                        r["whatnot_session_id_name"] = r.get("session_name")
                        try:
                            r["lines"] = list_sale_order_lines(int(r["id"])) or []
                        except Exception:
                            r["lines"] = []
                virtual_orders = _recent_tiktok_live_virtual_orders_for_username(
                    username_p or (customer.get("whatnot_username") if customer else ""),
                    existing_refs=[order.get("external_order_ref") for order in orders],
                )
                if virtual_orders:
                    orders = sorted(
                        list(orders or []) + virtual_orders,
                        key=lambda row: str(row.get("ordered_at") or row.get("date_order") or row.get("created_at") or ""),
                        reverse=True,
                    )
                    virtual_revenue = round(sum(float(order.get("total_amount") or 0) for order in virtual_orders), 2)
                    virtual_profit = 0.0
                    for order in virtual_orders:
                        line_cost = sum(
                            float(line.get("unit_cost") or line.get("cost_price") or 0) * float(line.get("qty") or line.get("product_uom_qty") or 0)
                            for line in (order.get("lines") or [])
                        )
                        virtual_profit += float(order.get("total_amount") or 0) - line_cost
                    analytics["summary"] = {
                        **(analytics.get("summary") or {}),
                        "purchase_count": int((analytics.get("summary") or {}).get("purchase_count") or 0) + len(virtual_orders),
                        "total_revenue": round(float((analytics.get("summary") or {}).get("total_revenue") or 0) + virtual_revenue, 2),
                        "total_profit": round(float((analytics.get("summary") or {}).get("total_profit") or 0) + virtual_profit, 2),
                    }
                identity_rows = list((analytics.get("identities") or [])) if analytics else []
                if customer:
                    if not customer.get("email"):
                        customer["email"] = next((str(row.get("email") or "").strip() for row in identity_rows if str(row.get("email") or "").strip()), None)
                    if not customer.get("phone"):
                        customer["phone"] = next((str(row.get("phone") or "").strip() for row in identity_rows if str(row.get("phone") or "").strip()), None)
                tiktok_order_ids = {
                    order_id for order_id in (_extract_tiktok_order_id(order) for order in (orders or [])) if order_id
                }
                return_rows = []
                if tiktok_order_ids:
                    try:
                        returns_payload = list_tracked_tiktok_returns(limit=5000, processed=None, q=None, monitor_only=False) or {}
                        return_rows = [
                            row for row in (returns_payload.get("rows") or [])
                            if str(row.get("order_id") or "").strip() in tiktok_order_ids
                        ]
                    except Exception:
                        return_rows = []
                cancelled_orders = [
                    order for order in (orders or [])
                    if str(order.get("state") or "").strip().lower() == "cancel"
                ]
                recent_products = []
                cancelled_products = []
                seen_recent = set()
                seen_cancelled = set()
                for order in (orders or []):
                    target = cancelled_products if str(order.get("state") or "").strip().lower() == "cancel" else recent_products
                    seen = seen_cancelled if target is cancelled_products else seen_recent
                    for product_name in _extract_order_products(order):
                        key = product_name.lower()
                        if key in seen:
                            continue
                        seen.add(key)
                        target.append({
                            "product_name": product_name,
                            "order_number": order.get("order_number"),
                            "ordered_at": order.get("ordered_at") or order.get("date_order") or order.get("created_at"),
                            "state": order.get("state"),
                            "source": order.get("order_source"),
                        })
                analytics["summary"] = {
                    **(analytics.get("summary") or {}),
                    "sale_order_count": len(orders or []),
                    "cancelled_order_count": len(cancelled_orders),
                    "return_count": len(return_rows),
                }
                audience = get_audience_user_profile(username_p or (customer.get("whatnot_username") if customer else None)) if (username_p or (customer and customer.get("whatnot_username"))) else None
                if not customer and not audience and not virtual_orders:
                    self._json({"ok": False, "error": "customer_not_found"}, status=404)
                    return
                if not customer:
                    uname = (username_p or (audience or {}).get("username") or "").strip().lstrip("@")
                    customer = {
                        "id": None,
                        "name": None,
                        "display_name": None,
                        "whatnot_username": uname or None,
                        "identities": [],
                        "sale_order_count": 0,
                        "session_count": 0,
                        "total_spent": 0,
                        "total_profit": 0,
                        "total_revenue": 0,
                        "purchase_count": 0,
                        "last_purchase_at": audience.get("last_seen") if audience else None,
                    }
                self._json({
                    "ok": True,
                    "customer": customer,
                    "sessions": analytics.get("sessions") or [],
                    "products": analytics.get("products") or [],
                    "summary": analytics.get("summary") or {},
                    "identities": identity_rows,
                    "orders": orders,
                    "return_rows": return_rows,
                    "recent_products": recent_products[:8],
                    "cancelled_products": cancelled_products[:8],
                    "audience": audience or {},
                })
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/customers/orders":
            partner_id_param = qs.get("partner_id", [None])[0]
            if not partner_id_param:
                self._json({"ok": False, "error": "partner_id required"}, status=400)
                return
            try:
                orders = list_customer_orders(int(partner_id_param))
                for r in orders:
                    r["name"] = r.get("order_number")
                    r["date_order"] = r.get("ordered_at")
                    r["amount_total"] = r.get("total_amount")
                    r["whatnot_session_id"] = r.get("session_id")
                    r["whatnot_session_id_name"] = r.get("session_name")
                total_spent = round(sum(o.get("amount_total") or 0 for o in orders), 2)
                total_profit = round(sum(o.get("order_profit") or 0 for o in orders), 2)
                self._json({"ok": True, "orders": orders, "total_spent": total_spent, "total_profit": total_profit})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        # ---------------------------------------------------------------
        # Reports endpoints
        # ---------------------------------------------------------------

        if path == "/api/reports/product_profit":
            session_id_param = qs.get("session_id", [None])[0]
            q = (qs.get("q", [""])[0] or "").strip()
            try:
                rows = get_product_profit_rows(session_id=session_id_param or None, q=q or None)
                for r in rows:
                    r["session_id_name"] = r.get("session_name")
                self._json({"ok": True, "rows": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        # ---------------------------------------------------------------
        # Orders & Inventory endpoints
        # ---------------------------------------------------------------

        if path == "/api/sessions/list":
            try:
                local_company_rows = list_company_sessions(OUR_WHATNOT_ACCOUNT, limit=200)
                rows = []
                for row in local_company_rows:
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
                self._json({"ok": True, "sessions": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/orders":
            session_id_param = qs.get("session_id", [None])[0]
            q = (qs.get("q", [""])[0] or "").strip().lower()
            try:
                local_company_session = _current_company_session()
                effective_session_id = session_id_param or (local_company_session["id"] if local_company_session else None)
                rows = list_buyer_groups(session_id=effective_session_id or None, q=q or None)
                for r in rows:
                    r["session_id_id"] = r.get("session_id")
                    sess = get_company_session(r["session_id"]) if r.get("session_id") else None
                    r["session_id_name"] = sess.get("name") if sess else None
                    r["partner_id"] = r.get("customer_id")
                    r["partner_id_id"] = r.get("customer_id")
                    r["partner_id_name"] = r.get("display_name")
                    r["sale_order_id_id"] = r.get("sale_order_id")
                    r["sale_order_id_name"] = None
                total_revenue = round(sum(r.get("total_revenue") or 0 for r in rows), 2)
                total_profit = round(sum(r.get("total_profit") or 0 for r in rows), 2)
                total_cost = round(sum(r.get("total_cost") or 0 for r in rows), 2)
                avg_margin = round(total_profit / total_revenue * 100.0, 1) if total_revenue else 0.0
                self._json({
                    "ok": True, "rows": rows,
                    "total_orders": len(rows),
                    "total_revenue": total_revenue,
                    "total_cost": total_cost,
                    "total_profit": total_profit,
                    "avg_margin": avg_margin,
                })
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/inventory":
            try:
                low_stock_threshold = int(qs.get("low_stock", ["3"])[0])
                active_param = (qs.get("active", ["true"])[0] or "").strip().lower()
                compact = (qs.get("compact", ["0"])[0] or "").strip().lower() in ("1", "true", "yes")
                limit_raw = qs.get("limit", [None])[0]
                offset_raw = qs.get("offset", ["0"])[0]
                limit_param = None
                try:
                    if limit_raw not in (None, "", "all"):
                        limit_param = max(1, min(int(limit_raw or 200), 1000))
                except Exception:
                    limit_param = 200
                try:
                    offset_param = max(0, int(offset_raw or 0))
                except Exception:
                    offset_param = 0
                active_only = active_param in ("true", "1", "active")
                if compact:
                    rows = _inventory_compact_rows(
                        active_only=active_only,
                        include_inactive=active_param in ("false", "0", "inactive"),
                    )
                else:
                    rows = list_products(active_only=active_only, low_stock_only=False)
                if active_param in ("false", "0", "inactive"):
                    rows = [row for row in rows if not row.get("active")]
                rows = [_inventory_list_row(r, low_stock_threshold) for r in rows]
                total_count = len(rows)
                if compact:
                    total_products = len(rows)
                    low_stock_count = sum(1 for row in rows if row.get("low_stock"))
                    out_of_stock_count = sum(1 for row in rows if float(row.get("qty_available") or 0) <= 0)
                    total_stock_value = round(sum(float(row.get("stock_value") or 0) for row in rows), 2)
                    summary = {
                        "total_products": total_products,
                        "total_stock_value": total_stock_value,
                        "low_stock_count": low_stock_count,
                        "out_of_stock_count": out_of_stock_count,
                        "missing_barcode_count": sum(1 for row in rows if not row.get("barcode")),
                        "missing_image_count": 0,
                        "unverified_notes_count": 0,
                    }
                else:
                    summary = inventory_summary()
                if limit_param is not None:
                    rows = rows[offset_param:offset_param + limit_param]
                self._json({
                    "ok": True,
                    "rows": rows,
                    "limit": limit_param,
                    "offset": offset_param,
                    "total_count": total_count,
                    "has_more": (offset_param + len(rows)) < total_count if limit_param is not None else False,
                    "total_products": summary["total_products"],
                    "total_stock_value": summary["total_stock_value"],
                    "low_stock_count": summary["low_stock_count"],
                    "out_of_stock_count": summary.get("out_of_stock_count", 0),
                    "missing_barcode_count": summary.get("missing_barcode_count", 0),
                    "missing_image_count": summary.get("missing_image_count", 0),
                    "unverified_notes_count": summary.get("unverified_notes_count", 0),
                })
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/inventory/categories":
            try:
                rows = list_categories()
                self._json({"ok": True, "rows": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/inventory/vendors":
            try:
                rows = list_vendors()
                self._json({"ok": True, "rows": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/purchases/orders":
            try:
                status_param = qs.get("status", [None])[0]
                search_query = qs.get("q", [None])[0]
                limit_param = int(qs.get("limit", ["250"])[0])
                payload = list_purchase_orders(status=status_param, q=search_query, limit=limit_param)
                self._json({"ok": True, **payload})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/purchases/order_detail":
            order_id_param = qs.get("order_id", [None])[0] or qs.get("id", [None])[0]
            if not order_id_param:
                self._json({"ok": False, "error": "order_id required"}, status=400)
                return
            try:
                detail = get_purchase_order_detail(int(order_id_param))
                if not detail:
                    self._json({"ok": False, "error": "purchase_order_not_found"}, status=404)
                    return
                self._json({"ok": True, **detail})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/purchases/order_pdf":
            order_id_param = qs.get("order_id", [None])[0] or qs.get("id", [None])[0]
            if not order_id_param:
                self._json({"ok": False, "error": "order_id required"}, status=400)
                return
            try:
                artifact = build_purchase_pdf(int(order_id_param))
                if not artifact:
                    self._json({"ok": False, "error": "purchase_order_not_found"}, status=404)
                    return
                safe_name = str(artifact.get("filename") or f"purchase-order-{order_id_param}.pdf").replace('"', "")
                payload = artifact.get("content") or b""
                if not payload:
                    self._json({"ok": False, "error": "purchase_order_pdf_missing"}, status=404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                _send_security_headers(self)
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        bargain_match = re.fullmatch(r"/api/v2/purchases/orders/(\d+)/bargain", path)
        if bargain_match:
            try:
                sessions = get_bargain_sessions_for_order(int(bargain_match.group(1)))
                self._json({"ok": True, "sessions": sessions})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                msg = str(exc)
                self._json({"ok": False, "error": msg}, status=503 if "company_db_postgres_runtime_required" in msg else 500)
            return

        if path == "/api/inventory/movements":
            product_id_param = qs.get("product_id", [None])[0]
            limit_param = int(qs.get("limit", ["50"])[0])
            try:
                rows = list_inventory_movements(product_id=product_id_param or None, limit=limit_param)
                for r in rows:
                    r["name"] = r.get("reason") or r.get("movement_type") or "Stock move"
                    r["product_uom_qty"] = abs(float(r.get("qty_delta") or 0))
                    r["date"] = r.get("created_at")
                    r["location_id_name"] = r.get("reference_type") or "Inventory"
                    r["location_dest_id_name"] = "Customer" if float(r.get("qty_delta") or 0) < 0 else "On Hand"
                self._json({"ok": True, "rows": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/inventory/audit":
            product_id_param = qs.get("product_id", [None])[0]
            limit_param = int(qs.get("limit", ["50"])[0])
            try:
                rows = list_inventory_audit_logs(product_id=product_id_param or None, limit=limit_param)
                self._json({"ok": True, "rows": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/inventory/integrity_audit":
            limit_param = int(qs.get("limit", ["100"])[0] or "100")
            try:
                audit = get_inventory_integrity_audit(limit=limit_param)
                self._json({"ok": True, **audit})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/inventory/product_detail":
            product_id_param = qs.get("product_id", [None])[0]
            if not product_id_param:
                self._json({"ok": False, "error": "product_id required"}, status=400)
                return
            try:
                detail = get_product_detail(int(product_id_param))
                if not detail:
                    self._json({"ok": False, "error": "product_not_found"}, status=404)
                    return
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
                self._json({"ok": True, **detail, "product": product})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/company/prep":
            try:
                data = get_inventory_prep_overview()
                self._json({"ok": True, **data})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        # --- Static Files (Vite build) ---
        if os.path.isdir(VITE_DIST_PATH):
            # SPA fallback: serve index.html for any non-API, non-file path
            file_path = os.path.join(VITE_DIST_PATH, path.lstrip("/"))
            if os.path.isfile(file_path):
                _serve_static(self, file_path)
                return
            # SPA fallback for routes like /operator, /session, etc.
            index_path = os.path.join(VITE_DIST_PATH, "index.html")
            if os.path.isfile(index_path):
                _serve_static(self, index_path)
                return

        self.send_response(404)
        self.end_headers()

    # -------------------------------------------------------------------
    # POST routes
    # -------------------------------------------------------------------
    def do_POST(self):
        self._req_started_at = time.perf_counter()
        self._req_method = "POST"
        self._req_path = self.path
        self._req_perf_pending = True
        try:
            self._do_POST_inner()
        except self.RequestTooLargeError:
            pass

    def _do_POST_inner(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/auth/login":
            if not self._verify_request_origin():
                return
            payload = self._read_json()
            challenge_ok, challenge_error = consume_login_challenge(
                payload.get("login_challenge"),
                client_ip=self._client_ip(),
                honeypot_value=payload.get("website") or payload.get("company") or "",
            )
            if not challenge_ok:
                refreshed = issue_login_challenge(self._client_ip())
                self._json(
                    {"ok": False, "error": challenge_error, "message": "Unable to sign in right now.", **refreshed},
                    status=400,
                )
                return
            ok, message, session, user = authenticate_user(
                payload.get("email"),
                payload.get("password"),
                payload.get("otp_code"),
                client_ip=self._client_ip(),
                user_agent=self.headers.get("User-Agent", ""),
            )
            if not ok:
                refreshed = issue_login_challenge(self._client_ip())
                self._json({"ok": False, "error": "invalid_credentials", "message": message, **(user or {}), **refreshed}, status=401)
                return
            self._json(
                {
                    "ok": True,
                    "authenticated": True,
                    "csrf_token": session.get("csrf_token"),
                    "user": user,
                },
                extra_headers=[self._set_session_cookie_header(session["id"])],
            )
            return

        if path == "/api/auth/logout":
            session = self._current_session()
            if session and not self._verify_csrf(session):
                return
            if session:
                destroy_session(session.get("id"))
            self._json(
                {"ok": True},
                extra_headers=[
                    self._set_session_cookie_header("", clear=True),
                    ("Clear-Site-Data", "\"cache\",\"storage\""),
                ],
            )
            return

        if path.startswith("/api/v2/purchases/bargain/") and path.endswith("/submit"):
            self._handle_purchase_bargain_vendor_submit(path)
            return

        if path == "/api/auth/sessions/revoke_all":
            session = self._require_session_auth()
            if not session:
                return
            if not self._verify_csrf(session):
                return
            revoked = revoke_user_sessions(session.get("email"), reason="logout_all_devices")
            self._json(
                {"ok": True, "revoked": revoked},
                extra_headers=[self._set_session_cookie_header("", clear=True)],
            )
            return

        if path == "/api/auth/password/change":
            session = self._require_session_auth()
            if not session:
                return
            if not self._verify_csrf(session):
                return
            payload = self._read_json()
            try:
                user = change_password(
                    session.get("email"),
                    current_password=payload.get("current_password"),
                    new_password=payload.get("new_password"),
                )
                self._json(
                    {"ok": True, "user": user, "message": "Password updated. Please sign in again."},
                    extra_headers=[
                        self._set_session_cookie_header("", clear=True),
                        ("Clear-Site-Data", "\"cache\",\"storage\""),
                    ],
                )
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return

        if path == "/api/auth/users/upsert":
            session = self._require_session_auth()
            if not session:
                return
            if not self._verify_csrf(session):
                return
            if (session.get("role") or "") != "admin":
                self._json({"ok": False, "error": "forbidden"}, status=403)
                return
            payload = self._read_json()
            try:
                user = upsert_auth_user(
                    payload.get("email"),
                    display_name=payload.get("display_name") or "",
                    role=payload.get("role") or "staff",
                    password=payload.get("password") or "",
                    active=bool(payload.get("active", True)),
                    actor_email=session.get("email"),
                )
                self._json({"ok": True, "user": user})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return

        if path == "/api/auth/users/revoke_sessions":
            session = self._require_session_auth()
            if not session:
                return
            if not self._verify_csrf(session):
                return
            if (session.get("role") or "") != "admin":
                self._json({"ok": False, "error": "forbidden"}, status=403)
                return
            payload = self._read_json()
            target_email = payload.get("email") or ""
            if not target_email:
                self._json({"ok": False, "error": "email required"}, status=400)
                return
            try:
                revoked = revoke_user_sessions(target_email, reason="admin_revoke")
                self._json({"ok": True, "revoked": revoked, "email": target_email})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return

        if path == "/api/employee_logins/upsert":
            payload = self._read_json()
            actor_session = self._current_session()
            actor_email = actor_session.get("email") if actor_session else "local_admin"
            try:
                user = upsert_auth_user(
                    payload.get("email"),
                    display_name=payload.get("display_name") or "",
                    role=payload.get("role") or "staff",
                    password=payload.get("password") or "",
                    active=bool(payload.get("active", True)),
                    actor_email=actor_email,
                )
                self._json({"ok": True, "user": user})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return

        if path == "/api/employee_logins/revoke_sessions":
            payload = self._read_json()
            target_email = payload.get("email") or ""
            if not target_email:
                self._json({"ok": False, "error": "email required"}, status=400)
                return
            try:
                revoked = revoke_user_sessions(target_email, reason="employee_management_revoke")
                self._json({"ok": True, "revoked": revoked, "email": target_email})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return

        if path == "/api/auth/mfa/setup":
            session = self._require_session_auth()
            if not session:
                return
            if not self._verify_csrf(session):
                return
            try:
                payload = begin_totp_setup(session.get("email"))
                self._json({"ok": True, **payload})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return

        if path == "/api/auth/mfa/confirm":
            session = self._require_session_auth()
            if not session:
                return
            if not self._verify_csrf(session):
                return
            payload = self._read_json()
            try:
                data = confirm_totp_setup(session.get("email"), payload.get("otp_code"))
                self._json({"ok": True, **data})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return

        if path == "/api/auth/mfa/disable":
            session = self._require_session_auth()
            if not session:
                return
            if not self._verify_csrf(session):
                return
            payload = self._read_json()
            try:
                data = disable_totp(session.get("email"), payload.get("otp_code"))
                self._json({"ok": True, **data})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return

        session = None
        if API_SECRET_KEY and self.headers.get("Authorization", "") == f"Bearer {API_SECRET_KEY}":
            session = {"api_secret": True}
        else:
            if self._session_auth_required(path):
                session = self._require_session_auth()
                if not session:
                    return
                if not self._verify_request_origin():
                    return
                if not self._verify_csrf(session):
                    return
            # OBS preview routes use their own lightweight flow and should not
            # trigger the generic auth fallback that logs the operator out.
            elif not path.startswith("/api/obs/") and not self._check_auth():
                return

        if path == "/api/scan":
            self._handle_scan()
            return

        if path == "/api/users/follow":
            self._json({"ok": False, "error": "whatnot_follow_retired"}, status=410)
            return

        if path == "/api/customers/reviews/sync":
            self._json({"ok": False, "error": "reviews_feature_removed"}, status=410)
            return

        if path == "/api/obs/demo/scan":
            self._handle_obs_demo_scan()
            return

        if path == "/api/obs/demo/clear":
            _clear_demo_scan_state()
            self._json({"ok": True})
            return

        if path == "/api/winner_assignment/scan":
            payload = self._read_json()
            barcode = (payload.get("barcode") or "").strip()
            assignment_id = payload.get("assignment_id")
            session = _resolve_company_session(payload.get("session_id")) or _current_company_session()
            if not barcode:
                self._json({"ok": False, "error": "missing_barcode"}, status=400)
                return
            if not session:
                self._json({"ok": False, "error": "no_company_session"}, status=400)
                return
            product = find_product_by_code(barcode)
            if not product:
                self._json({"ok": False, "error": "product_not_found"}, status=404)
                return
            if not assignment_id:
                queue_rows = list_pending_winner_assignments(int(session["id"]), statuses=("pending", "assigned"), limit=25)
                target = next((row for row in queue_rows if row.get("status") == "pending"), None) or (queue_rows[0] if queue_rows else None)
                assignment_id = target.get("id") if target else None
            if not assignment_id:
                self._json({"ok": False, "error": "no_pending_winner"}, status=409)
                return
            # Allow adding more products to a confirmed lot:
            # If the operator scans another barcode for the same winner ticket,
            # temporarily undo the confirm, add the item, and let the UI confirm again.
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
                self._json({"ok": False, "error": "assign_failed"}, status=500)
                return
            assigned["image_url"] = _product_image_url(product)
            self._json({"ok": True, "assignment": assigned})
            return

        if path == "/api/winner_assignment/confirm":
            payload = self._read_json()
            assignment_id = payload.get("assignment_id")
            if not assignment_id:
                self._json({"ok": False, "error": "assignment_id required"}, status=400)
                return
            confirmed = confirm_pending_winner_assignment(int(assignment_id))
            if not confirmed:
                self._json({"ok": False, "error": "confirm_failed"}, status=400)
                return
            product = get_product(int(confirmed["assigned_product_id"])) if confirmed.get("assigned_product_id") else None
            confirmed["image_url"] = _product_image_url(product) if product else None
            self._json({"ok": True, "assignment": confirmed})
            return

        if path == "/api/winner_assignment/undo":
            payload = self._read_json()
            assignment_id = payload.get("assignment_id")
            if not assignment_id:
                self._json({"ok": False, "error": "assignment_id required"}, status=400)
                return
            assignment = undo_confirm_pending_winner_assignment(int(assignment_id))
            if not assignment:
                self._json({"ok": False, "error": "undo_failed"}, status=400)
                return
            product = get_product(int(assignment["assigned_product_id"])) if assignment.get("assigned_product_id") else None
            assignment["image_url"] = _product_image_url(product) if product else None
            self._json({"ok": True, "assignment": assignment})
            return

        if path == "/api/winner_assignment/item/delete":
            payload = self._read_json()
            assignment_id = payload.get("assignment_id")
            item_id = payload.get("item_id")
            if not assignment_id or not item_id:
                self._json({"ok": False, "error": "assignment_id and item_id required"}, status=400)
                return
            assignment = remove_pending_winner_assignment_item(int(assignment_id), int(item_id))
            if not assignment:
                self._json({"ok": False, "error": "remove_failed"}, status=400)
                return
            self._json({"ok": True, "assignment": assignment})
            return

        if path == "/api/winner_assignment/status":
            payload = self._read_json()
            assignment_id = payload.get("assignment_id")
            status = payload.get("status")
            notes = payload.get("notes")
            if not assignment_id or not status:
                self._json({"ok": False, "error": "assignment_id and status required"}, status=400)
                return
            assignment = update_pending_winner_assignment_status(int(assignment_id), status, notes=notes)
            if not assignment:
                self._json({"ok": False, "error": "status_update_failed"}, status=400)
                return
            self._json({"ok": True, "assignment": assignment})
            return

        if path == "/api/winner_assignment/lot":
            payload = self._read_json()
            assignment_id = payload.get("assignment_id")
            lot_number = str(payload.get("lot_number") or "").strip()
            if not assignment_id or not lot_number:
                self._json({"ok": False, "error": "assignment_id and lot_number required"}, status=400)
                return
            assignment = update_pending_winner_assignment_lot_number(int(assignment_id), lot_number)
            if not assignment:
                self._json({"ok": False, "error": "lot_update_failed"}, status=400)
                return
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
            self._json({"ok": True, "assignment": assignment, "tiktok_next_lot": next_lot})
            return

        if path == "/api/winner_assignment/delete":
            payload = self._read_json()
            assignment_id = payload.get("assignment_id")
            if not assignment_id:
                self._json({"ok": False, "error": "assignment_id required"}, status=400)
                return
            ok = delete_pending_winner_assignment(int(assignment_id))
            if not ok:
                self._json({"ok": False, "error": "delete_failed"}, status=400)
                return
            self._json({"ok": True, "deleted_assignment_id": int(assignment_id)})
            return

        if path == "/api/current_lot/set":
            payload = self._read_json()
            lot_number = str(payload.get("lot_number") or "").strip()
            company_session = _resolve_company_session(payload.get("session_id"))
            if company_session:
                if not lot_number:
                    self._json({"ok": False, "error": "missing_lot_number"}, status=400)
                    return
                lot = ensure_company_bucket(company_session["id"])
                lot = rename_company_lot(lot["id"], lot_number)
                self._json({"ok": True, "session_id": company_session["id"], "lot": lot})
                return
            self._json({"ok": False, "error": "no_company_session"}, status=400)
            return

        if path == "/api/current_lot/awaiting":
            payload = self._read_json()
            company_session = _current_company_session()
            if company_session:
                lot = get_current_company_lot(company_session["id"])
                if not lot:
                    self._json({"ok": False, "error": "no_current_lot"}, status=400)
                    return
                update_company_lot(lot["id"], status="awaiting_auction")
                lot = get_current_company_lot(company_session["id"])
                self._json({"ok": True, "lot": lot})
                return
            self._json({"ok": False, "error": "no_company_session"}, status=400)
            return

        if path == "/api/current_lot/select_product":
            payload = self._read_json()
            item_id = payload.get("item_id")
            company_session = _current_company_session()
            if company_session:
                lot = get_current_company_lot(company_session["id"])
                if not lot:
                    self._json({"ok": False, "error": "no_current_lot"}, status=400)
                    return
                item = get_lot_item(int(item_id)) if item_id else None
                if not item or int(item.get("lot_id") or 0) != int(lot["id"]):
                    self._json({"ok": False, "error": "invalid_lot_item"}, status=400)
                    return
                selected = _sync_selected_lot_item(company_session["id"], lot["id"], item["id"])
                self._json({"ok": True, "active_item": selected})
                return
            self._json({"ok": False, "error": "no_company_session"}, status=400)
            return

        if path == "/api/current_lot/remove_candidate":
            payload = self._read_json()
            item_id = payload.get("item_id")
            company_session = _current_company_session()
            if company_session:
                lot = get_current_company_lot(company_session["id"])
                if not lot:
                    self._json({"ok": False, "error": "no_current_lot"}, status=400)
                    return
                item = get_lot_item(int(item_id)) if item_id else None
                if not item or int(item.get("lot_id") or 0) != int(lot["id"]):
                    self._json({"ok": False, "error": "invalid_lot_item"}, status=400)
                    return
                update_lot_item(item["id"], status="dropped")
                selected = _sync_selected_lot_item(company_session["id"], lot["id"])
                self._json({"ok": True, "active_item": selected})
                return
            self._json({"ok": False, "error": "no_company_session"}, status=400)
            return

        if path == "/api/current_lot/drop":
            payload = self._read_json()
            company_session = _current_company_session()
            if company_session:
                lot = get_current_company_lot(company_session["id"])
                if not lot:
                    self._json({"ok": False, "error": "no_current_lot"}, status=400)
                    return
                _clear_live_obs_scan(company_session["id"])
                clear_shared_scan_for_session(company_session["id"])
                _clear_demo_scan_state()
                update_company_lot(lot["id"], status="released", closed_at=datetime.now(timezone.utc).isoformat())
                update_company_session(company_session["id"], current_lot_number=None)
                _clear_live_obs_tray(company_session["id"])
                _finalize_released_lot_async(lot["id"])
                self._json({"ok": True, "lot": {}})
                return
            self._json({"ok": False, "error": "no_company_session"}, status=400)
            return

        if path == "/api/current_lot/reuse":
            payload = self._read_json()
            company_session = _current_company_session()
            if company_session:
                lot = latest_reusable_lot(company_session["id"])
                if not lot:
                    self._json({"ok": False, "error": "no_current_lot"}, status=400)
                    return
                mark_lot_items_status(lot["id"], from_statuses=("dropped",), to_status="open")
                update_company_lot(lot["id"], status="open", closed_at=None)
                update_company_session(company_session["id"], current_lot_number=lot.get("lot_number"))
                clear_shared_scan_for_session(company_session["id"])
                _clear_demo_scan_state()
                self._json({"ok": True, "lot": get_current_company_lot(company_session["id"])})
                return
            self._json({"ok": False, "error": "no_company_session"}, status=400)
            return

        if path == "/api/current_lot/clear":
            payload = self._read_json()
            company_session = _current_company_session()
            if company_session:
                update_company_session(company_session["id"], current_lot_number=None)
                clear_shared_scan_for_session(company_session["id"])
                _clear_demo_scan_state()
                self._json({"ok": True})
                return
            self._json({"ok": False, "error": "no_company_session"}, status=400)
            return

        if path == "/api/active_item_status":
            payload = self._read_json()
            active_item_id = payload.get("active_item_id")
            status = payload.get("status")
            if not (active_item_id and status):
                self._json({"ok": False, "error": "missing_params"}, status=400)
                return
            company_session = _current_company_session()
            if company_session:
                row = update_lot_item(int(active_item_id), status=status)
                if row:
                    # Enrich with full product data for OBS overlay
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
                    _set_demo_scan(None)
                self._json({"ok": bool(row)})
                return
            self._json({"ok": False, "error": "no_company_session"}, status=400)
            return

        if path == "/api/reassign":
            payload = self._read_json()
            auction_result_id = payload.get("auction_result_id")
            active_item_id = payload.get("active_item_id")
            if not (auction_result_id and active_item_id):
                self._json({"ok": False, "error": "missing_params"}, status=400)
                return
            self._json({"ok": False, "error": "not_supported"}, status=400)
            return

        if path == "/api/ingest_winner":
            self._handle_ingest_winner()
            return

        if path == "/api/stream_start":
            self._handle_stream_start()
            return

        if path == "/api/stream_stop":
            status = stop_live_collector()
            self._json({"ok": True, **status})
            return

        if path == "/api/live_collector/start":
            self._handle_stream_start()
            return

        if path == "/api/live_collector/stop":
            status = stop_live_collector()
            self._json({"ok": True, **status})
            return

        if path == "/api/tiktok_operator/config":
            payload = self._read_json()
            enabled = bool(payload.get("enabled"))
            streamer = (payload.get("streamer") or "").strip().lstrip("@")
            if enabled and not streamer:
                self._json({"ok": False, "error": "streamer_required"}, status=400)
                return
            stream_url = f"tiktok:{streamer}" if streamer else None

            state = load_collector_state() or {}
            if enabled:
                prev_stream_url = (state.get("tiktok_operator_stream_url") or "").strip() or None
                # Always start a fresh dedicated company session for TikTok operator mode.
                # Reusing an old session can surface stale pending winner tickets and
                # looks like "random" lots/users.
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
                session_id = _ensure_tiktok_operator_session(stream_url, streamer=streamer)
                state["tiktok_operator_enabled"] = True
                state["tiktok_operator_streamer"] = streamer
                state["tiktok_operator_stream_url"] = stream_url
                state["tiktok_operator_session_id"] = int(session_id) if session_id else None
                # Cursor:
                # - keep continuity across restarts for the same streamer
                # - but when enabling for the first time (or switching streamer), start from "now"
                #   to avoid flooding the queue with historical wins.
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
                            recent = get_recent_events(limit=1, stream_id=int(sid))
                            latest_id = max((int(row.get("id") or 0) for row in recent), default=0)
                        except Exception:
                            latest_id = 0
                    state["tiktok_operator_last_ingested_event_id"] = int(latest_id)
                else:
                    state.setdefault("tiktok_operator_last_ingested_event_id", 0)
                save_collector_state(state)
                self._json({"ok": True, "tiktok_operator": _tiktok_operator_status()})
                return

            # Disable
            state["tiktok_operator_enabled"] = False
            state["tiktok_operator_streamer"] = streamer or state.get("tiktok_operator_streamer")
            state["tiktok_operator_stream_url"] = stream_url or state.get("tiktok_operator_stream_url")
            save_collector_state(state)
            self._json({"ok": True, "tiktok_operator": _tiktok_operator_status()})
            return

        if path == "/api/tiktok_extractor/lot_state":
            payload = self._read_json()
            stream_url = str(payload.get("stream_url") or "").strip()
            if not stream_url:
                self._json({"ok": False, "error": "stream_url_required"}, status=400)
                return
            next_lot_raw = payload.get("next_lot")
            next_lot = None
            if next_lot_raw not in (None, "", False):
                try:
                    next_lot = int(next_lot_raw)
                except Exception:
                    self._json({"ok": False, "error": "invalid_next_lot"}, status=400)
                    return
                if next_lot <= 0:
                    self._json({"ok": False, "error": "invalid_next_lot"}, status=400)
                    return
            state = load_collector_state() or {}
            lot_state = state.get("tiktok_extractor_lot_state") or {}
            if not isinstance(lot_state, dict):
                lot_state = {}
            if next_lot is None:
                lot_state.pop(stream_url, None)
            else:
                lot_state[stream_url] = {
                    "next_lot": next_lot,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            state["tiktok_extractor_lot_state"] = lot_state
            save_collector_state(state)
            self._json({"ok": True, "stream_url": stream_url, "next_lot": next_lot})
            return

        if path == "/api/spectator/start":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/spectator/stop":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/spectator/priority_start":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/spectator/priority_stop":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        if path == "/api/upload_cookies":
            self._handle_upload_cookies()
            return

        if path == "/api/picklist/upload":
            self._handle_picklist_upload()
            return

        if path == "/api/tiktok_live_labels/enrich_pdf":
            self._handle_tiktok_live_label_enrich_pdf()
            return

        if path == "/api/whatnot_labels/enrich_pdf":
            self._handle_whatnot_picklist_enrich_pdf()
            return

        if path == "/api/tiktok_live_sessions/start":
            payload = self._read_json()
            try:
                active_session = _get_active_tiktok_go_live_session(live_api_enrich=False)
                if active_session and active_session.get("serverSessionId"):
                    self._json({"ok": True, "session": active_session, "already_active": True})
                    return
                lot_count = max(1, min(1000, int(payload.get("lot_count") or 1)))
                next_sequence = _next_tiktok_go_live_sequence()
                requested_sequence = int(payload.get("sequence") or 0)
                sequence = requested_sequence if requested_sequence >= next_sequence else next_sequence
                note = str(payload.get("live_name") or "").strip()
                date_label = datetime.now().strftime("%A - %b %d")
                name = f"Go Live Session - {sequence} (date : {date_label})"
                if note:
                    name = f"{name} - {note}"
                show_id = f"{_TIKTOK_GO_LIVE_SHOW_PREFIX}{datetime.now().strftime('%Y%m%d-%H%M%S')}-{sequence}"
                session = create_company_session(
                    show_id=show_id,
                    whatnot_account=OUR_WHATNOT_ACCOUNT,
                    name=name,
                    status="live",
                )
                for lot_no in range(1, lot_count + 1):
                    create_company_lot(session["id"], str(lot_no), status="open")
                _append_tiktok_go_live_journal(
                    session,
                    "session_started",
                    extra={"lot_count": lot_count, "sequence": sequence, "note": note},
                )
                _write_tiktok_go_live_snapshot(session)
                enqueue_tiktok_live_sheet_backup(session.get("id"), "session_started")
                _clear_tiktok_go_live_session_cache()
                serialized = _serialize_tiktok_go_live_session(session)
                export_path = _write_tiktok_go_live_operator_csv(serialized)
                self._json({"ok": True, "session": serialized, "exportPath": export_path})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/google_sheets/full_backup":
            try:
                self._json(sync_full_workbook_backup_to_google_sheet())
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/scan_lot":
            payload = self._read_json()
            session_id = payload.get("session_id")
            lot_no = str(payload.get("lot_no") or "").strip()
            barcode = str(payload.get("barcode") or "").replace("\r", "").replace("\n", "").replace("\t", "").strip()
            review_later = bool(payload.get("review_later")) or barcode.lower() == "review_later"
            if not session_id or not lot_no:
                self._json({"ok": False, "error": "session_id and lot_no required"}, status=400)
                return
            try:
                session = get_company_session(int(session_id))
                if not session:
                    self._json({"ok": False, "error": "session not found"}, status=404)
                    return
                lot = create_company_lot(int(session_id), lot_no, status="open")
                product = None if review_later else (find_product_by_code(barcode) if barcode else None)
                _release_tiktok_live_pending_reservations(
                    list_lot_items(int(lot["id"])),
                    reason=f"TikTok LIVE rescan replaced lot {lot_no}",
                )
                item = replace_lot_items_for_scan(
                    lot["id"],
                    product_id=product.get("id") if product else None,
                    barcode="" if review_later else barcode,
                    sku=(product.get("default_code") or product.get("sku") or "") if product else "",
                    product_name=("Review later" if review_later else (product.get("name") if product else "")),
                    notes="review_later" if review_later else "",
                    unit_cost=float(product.get("cost_price") or 0) if product else 0,
                    qty_snapshot=1,
                    status="open",
                )
                update_company_lot(lot["id"], status="open")
                row = {
                    "lotNo": lot_no,
                    "barcode": "" if review_later else barcode,
                    "productName": "Review later" if review_later else (product.get("name") if product else ""),
                    "notes": str(item.get("notes") or "").strip() if item else "",
                    "sku": (product.get("default_code") or product.get("sku") or "") if product else "",
                    "cost": float(product.get("cost_price") or 0) if product else 0,
                    "productId": product.get("id") if product else None,
                    "matched": bool(product),
                    "itemId": item.get("id") if item else None,
                    "reviewLater": review_later,
                    "statusLabel": "Review later" if review_later else "",
                    "statusFamily": "review_later" if review_later else "",
                }
                _append_tiktok_go_live_journal(
                    session,
                    "lot_review_later" if review_later else "lot_scanned",
                    lot_no=lot_no,
                    item=item,
                    row=row,
                    extra={"matched": bool(product), "review_later": review_later},
                )
                _write_tiktok_go_live_snapshot(session)
                enqueue_tiktok_live_sheet_backup(session.get("id"), "lot_scanned")
                _clear_tiktok_go_live_session_cache()
                # Eagerly enrich the row with TikTok order data so the buyer
                # fills in the scan response itself — no need to wait for the
                # next active-session poll.
                if not review_later:
                    try:
                        enriched_rows = _enrich_tiktok_go_live_rows_with_pending_orders(session, [row])
                        if enriched_rows:
                            row = enriched_rows[0]
                            _materialize_tiktok_go_live_live_rows(session, [row])
                            row = (_enrich_tiktok_go_live_rows_with_sale_orders(session, [row]) or [row])[0]
                    except Exception:
                        pass
                serialized = _serialize_tiktok_go_live_session(session)
                export_path = _write_tiktok_go_live_operator_csv(serialized)
                self._json({"ok": True, "row": row, "session": serialized, "exportPath": export_path})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/clear_lot":
            payload = self._read_json()
            session_id = payload.get("session_id")
            lot_no = str(payload.get("lot_no") or "").strip()
            if not session_id or not lot_no:
                self._json({"ok": False, "error": "session_id and lot_no required"}, status=400)
                return
            try:
                session = get_company_session(int(session_id))
                if not session:
                    self._json({"ok": False, "error": "session not found"}, status=404)
                    return
                lot = create_company_lot(int(session_id), lot_no, status="open")
                _release_tiktok_live_pending_reservations(
                    list_lot_items(int(lot["id"])),
                    reason=f"TikTok LIVE lot {lot_no} cleared",
                )
                replace_lot_items_for_scan(
                    lot["id"],
                    product_id=None,
                    barcode="",
                    sku="",
                    product_name="",
                    unit_cost=0,
                    qty_snapshot=1,
                    status="open",
                )
                update_company_lot(lot["id"], status="open")
                row = {
                    "lotNo": lot_no,
                    "barcode": "",
                    "productName": "",
                    "notes": "",
                    "sku": "",
                    "cost": 0,
                    "productId": None,
                    "matched": False,
                    "itemId": None,
                }
                _append_tiktok_go_live_journal(
                    session,
                    "lot_cleared",
                    lot_no=lot_no,
                    row=row,
                )
                _write_tiktok_go_live_snapshot(session)
                enqueue_tiktok_live_sheet_backup(session.get("id"), "lot_cleared")
                _clear_tiktok_go_live_session_cache()
                serialized = _serialize_tiktok_go_live_session(session)
                export_path = _write_tiktok_go_live_operator_csv(serialized)
                self._json({"ok": True, "row": row, "session": serialized, "exportPath": export_path})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/import_sheet":
            payload = self._read_json()
            session_id = payload.get("session_id")
            csv_text = str(payload.get("csv_text") or "").strip()
            sheet_url = str(payload.get("sheet_url") or "").strip()
            if not session_id:
                self._json({"ok": False, "error": "session_id required"}, status=400)
                return
            if not csv_text and not sheet_url:
                self._json({"ok": False, "error": "csv_text or sheet_url required"}, status=400)
                return
            try:
                session = get_company_session(int(session_id))
                if not session:
                    self._json({"ok": False, "error": "session not found"}, status=404)
                    return
                if not csv_text and sheet_url:
                    csv_text = _download_sheet_csv_text(sheet_url)
                parsed_rows = _parse_tiktok_sheet_rows(csv_text)
                if not parsed_rows:
                    self._json({"ok": False, "error": "no usable lot rows found in sheet"}, status=400)
                    return

                touched_lots = {}
                first_seen_lots = set()
                matched_rows = 0
                unmatched_rows = 0
                imported_rows = 0
                for parsed_row in parsed_rows:
                    lot_no = str(parsed_row.get("lot_number") or "").strip()
                    if not lot_no:
                        continue
                    lot = touched_lots.get(lot_no)
                    if not lot:
                        lot = create_company_lot(int(session_id), lot_no, status="open")
                        touched_lots[lot_no] = lot
                    product = find_product_by_code(parsed_row.get("barcode")) if parsed_row.get("barcode") else None
                    if lot_no not in first_seen_lots:
                        replace_lot_items_for_scan(
                            lot["id"],
                            product_id=product.get("id") if product else None,
                            barcode=parsed_row.get("barcode") or "",
                            sku=(product.get("default_code") or product.get("sku") or "") if product else "",
                            product_name=(product.get("name") or parsed_row.get("product_name") or "") if product or parsed_row.get("product_name") else "",
                            unit_cost=float(product.get("cost_price") or 0) if product else 0,
                            qty_snapshot=1,
                            status="open",
                        )
                        first_seen_lots.add(lot_no)
                    else:
                        add_lot_item(
                            lot["id"],
                            product_id=product.get("id") if product else None,
                            barcode=parsed_row.get("barcode") or "",
                            sku=(product.get("default_code") or product.get("sku") or "") if product else "",
                            product_name=(product.get("name") or parsed_row.get("product_name") or "") if product or parsed_row.get("product_name") else "",
                            unit_cost=float(product.get("cost_price") or 0) if product else 0,
                            qty_snapshot=1,
                            status="open",
                        )
                    update_company_lot(lot["id"], status="open")
                    imported_rows += 1
                    if product:
                        matched_rows += 1
                    else:
                        unmatched_rows += 1

                rows = []
                for lot_no in sorted(touched_lots.keys(), key=lambda value: int(value) if str(value).isdigit() else str(value)):
                    lot = touched_lots[lot_no]
                    items = list_lot_items(lot["id"])
                    primary = items[0] if items else {}
                    rows.append(_tiktok_go_live_row_from_lot({
                        **dict(primary or {}),
                        "lot_number": lot_no,
                        "_all_items": items,
                    }))

                _append_tiktok_go_live_journal(
                    session,
                    "sheet_imported",
                    extra={
                        "imported_rows": imported_rows,
                        "matched_rows": matched_rows,
                        "unmatched_rows": unmatched_rows,
                        "sheet_url": sheet_url,
                    },
                )
                _write_tiktok_go_live_snapshot(session)
                enqueue_tiktok_live_sheet_backup(session.get("id"), "sheet_imported")
                self._json({
                    "ok": True,
                    "summary": {
                        "imported_rows": imported_rows,
                        "matched_rows": matched_rows,
                        "unmatched_rows": unmatched_rows,
                        "lots_touched": len(touched_lots),
                    },
                    "rows": rows,
                    "session": _serialize_tiktok_go_live_session(session),
                })
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/configure_sheet_sync":
            payload = self._read_json()
            session_id = payload.get("session_id")
            sheet_url = str(payload.get("sheet_url") or "").strip()
            enabled = bool(payload.get("enabled", True))
            if not session_id:
                self._json({"ok": False, "error": "session_id required"}, status=400)
                return
            try:
                session = get_company_session(int(session_id))
                if not session:
                    self._json({"ok": False, "error": "session not found"}, status=404)
                    return
                config = _set_tiktok_go_live_sheet_sync(int(session_id), {
                    "sheet_url": sheet_url,
                    "enabled": enabled,
                })
                sync_result = _auto_sync_tiktok_go_live_sheet_session(session, force=True) if enabled and sheet_url else {"updated": False}
                enqueue_tiktok_live_sheet_backup(session.get("id"), "sheet_sync_configured")
                self._json({
                    "ok": True,
                    "config": config,
                    "sync": sync_result,
                    "session": _serialize_tiktok_go_live_session(session),
                })
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/update_lot_note":
            payload = self._read_json()
            session_id = payload.get("session_id")
            lot_no = str(payload.get("lot_no") or "").strip()
            item_id = payload.get("item_id")
            notes = str(payload.get("notes") or "").strip()
            if not session_id or not lot_no:
                self._json({"ok": False, "error": "session_id and lot_no required"}, status=400)
                return
            try:
                session = get_company_session(int(session_id))
                if not session:
                    self._json({"ok": False, "error": "session not found"}, status=404)
                    return
                lot = create_company_lot(int(session_id), lot_no, status="open")
                item = get_lot_item(int(item_id)) if item_id else None
                if not item or int(item.get("lot_id") or 0) != int(lot["id"]):
                    items = list_lot_items(lot["id"])
                    item = items[0] if items else None
                if not item:
                    self._json({"ok": False, "error": "lot item not found"}, status=404)
                    return
                updated = update_lot_item(int(item["id"]), notes=notes)
                row = _tiktok_go_live_row_from_lot({
                    **dict(updated or {}),
                    "lot_number": lot_no,
                })
                _append_tiktok_go_live_journal(
                    session,
                    "lot_note_updated",
                    lot_no=lot_no,
                    item=updated,
                    row=row,
                    extra={"note_length": len(notes)},
                )
                _write_tiktok_go_live_snapshot(session)
                enqueue_tiktok_live_sheet_backup(session.get("id"), "lot_note_updated")
                _clear_tiktok_go_live_session_cache()
                serialized = _serialize_tiktok_go_live_session(session)
                export_path = _write_tiktok_go_live_operator_csv(serialized)
                self._json({"ok": True, "row": row, "session": serialized, "exportPath": export_path})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/end":
            payload = self._read_json()
            session_id = payload.get("session_id")
            if not session_id:
                self._json({"ok": False, "error": "session_id required"}, status=400)
                return
            try:
                session = end_company_session(int(session_id))
                recovery_result = _materialize_tiktok_go_live_sale_orders_from_api(session)
                _append_tiktok_go_live_journal(session, "session_ended")
                _write_tiktok_go_live_snapshot(session)
                enqueue_tiktok_live_sheet_backup(session.get("id"), "session_ended")
                _clear_tiktok_go_live_session_cache()
                serialized = _serialize_tiktok_go_live_session(session)
                export_path = _write_tiktok_go_live_operator_csv(serialized)
                self._json({"ok": True, "session": serialized, "recovery": recovery_result, "exportPath": export_path})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/delete_empty":
            payload = self._read_json()
            session_id = payload.get("session_id")
            if not session_id:
                self._json({"ok": False, "error": "session_id required"}, status=400)
                return
            try:
                lots = list_company_lots(session_id=int(session_id), limit=2000)
                scanned = 0
                for lot in lots:
                    for item in list_lot_items(lot["id"]):
                        if str(item.get("barcode") or "").strip():
                            scanned += 1
                if scanned:
                    self._json({"ok": False, "error": "session has scanned lots; cannot delete as empty"}, status=409)
                    return
                session = get_company_session(int(session_id))
                if session:
                    _append_tiktok_go_live_journal(session, "session_deleted_empty")
                    _write_tiktok_go_live_snapshot(session)
                delete_company_session_tree(int(session_id))
                _clear_tiktok_go_live_session_cache()
                self._json({"ok": True, "deleted": True, "session_id": int(session_id)})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/apply_inventory":
            payload = self._read_json()
            session_id = payload.get("session_id")
            if not session_id:
                self._json({"ok": False, "error": "session_id required"}, status=400)
                return
            try:
                session = get_company_session(int(session_id))
                if not session:
                    self._json({"ok": False, "error": "session not found"}, status=404)
                    return
                result = apply_tiktok_live_session_inventory(int(session_id))
                enqueue_tiktok_live_sheet_backup(session.get("id"), "inventory_applied")
                self._json(result)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_sessions/replace_lot_product":
            payload = self._read_json()
            session_id = payload.get("session_id")
            lot_number = payload.get("lot_number") or payload.get("lot_no") or payload.get("lotNo")
            query = payload.get("query") or payload.get("barcode") or payload.get("product")
            product_id = payload.get("product_id")
            if not session_id or not lot_number:
                self._json({"ok": False, "error": "session_id and lot_number required"}, status=400)
                return
            if not product_id and not str(query or "").strip():
                self._json({"ok": False, "error": "barcode, product name, or product_id required"}, status=400)
                return
            try:
                result = replace_tiktok_live_lot_product(
                    int(session_id),
                    str(lot_number).strip(),
                    product_id=int(product_id) if product_id else None,
                    query=str(query or "").strip() or None,
                )
                session = get_company_session(int(session_id))
                if session:
                    _write_tiktok_go_live_snapshot(session)
                    enqueue_tiktok_live_sheet_backup(session.get("id"), "lot_product_replaced")
                _clear_tiktok_go_live_session_cache()
                self._json(result)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/retry_ingest":
            payload = self._read_json()
            failed_id = payload.get("failed_id")
            if not failed_id:
                self._json({"ok": False, "error": "failed_id required"}, status=400)
                return
            records = get_failed_ingests(include_resolved=True)
            record = next((r for r in records if r["id"] == failed_id), None)
            if not record:
                self._json({"ok": False, "error": "not found"}, status=404)
                return
            if record["resolved"]:
                self._json({"ok": True, "already_resolved": True})
                return
            if record["retry_count"] >= MAX_INGEST_RETRIES:
                self._json({
                    "ok": False,
                    "error": "max_retries_exceeded",
                    "message": f"This ingest has failed {record['retry_count']} times. Use 'Dismiss' to clear it and handle manually.",
                }, status=400)
                return
            # Re-fetch the original event from the Postgres-backed event store to retry.
            try:
                original_event = get_event_by_id(record["event_id"])
                if original_event:
                    p = json.loads(original_event["payload"] or "{}")
                    ok = _maybe_ingest_winner_event(
                        record["event_id"], record["sold_at"], p,
                        failed_ingest_id=failed_id,
                        stream_id=original_event.get("stream_id"),
                    )
                else:
                    # Event not found, try with stored data
                    ok = _maybe_ingest_winner_event(
                        record["event_id"],
                        record["sold_at"],
                        {"winner_username": record["winner_username"],
                         "sale_price": record["sale_price"],
                         "lot_number": record["lot_number"]},
                        failed_ingest_id=failed_id,
                    )
            except Exception as exc:
                increment_retry_count(failed_id, error_message=str(exc))
                self._json({"ok": False, "error": str(exc)}, status=500)
                return
            self._json({"ok": ok, "resolved": ok})
            return

        if path == "/api/mark_ingest_resolved":
            payload = self._read_json()
            failed_id = payload.get("failed_id")
            if not failed_id:
                self._json({"ok": False, "error": "failed_id required"}, status=400)
                return
            mark_failed_ingest_resolved(failed_id)
            self._json({"ok": True})
            return

        if path == "/api/retry_all_ingests":
            pending = [r for r in get_failed_ingests(include_resolved=False) if not r["resolved"] and not r.get("needs_review")]
            succeeded = 0
            failed = 0
            for record in pending:
                try:
                    event = get_event_by_id(record["event_id"])
                    if event:
                        payload = json.loads(event.get("payload") or "{}")
                        ok = _maybe_ingest_winner_event(
                            event["id"], event.get("created_at"), payload,
                            failed_ingest_id=record["id"],
                            stream_id=event.get("stream_id"),
                        )
                    else:
                        ok = _maybe_ingest_winner_event(
                            record["event_id"],
                            record.get("sold_at") or record.get("created_at"),
                            {
                                "winner_username": record["winner_username"],
                                "sale_price": record["sale_price"],
                                "lot_number": record.get("lot_number"),
                            },
                            failed_ingest_id=record["id"],
                        )
                    if ok:
                        succeeded += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1
            self._json({"ok": True, "succeeded": succeeded, "failed": failed, "total": len(pending)})
            return

        if path == "/api/dismiss_all_ingests":
            pending = [r for r in get_failed_ingests(include_resolved=False) if not r["resolved"]]
            for record in pending:
                mark_failed_ingest_resolved(record["id"])
            self._json({"ok": True, "dismissed": len(pending)})
            return

        if path == "/api/system/clear_demo_scan":
            _clear_demo_scan_state()
            self._json({"ok": True})
            return

        bargain_create_match = re.fullmatch(r"/api/v2/purchases/orders/(\d+)/bargain", path)
        if bargain_create_match:
            payload = self._read_json()
            try:
                result = create_bargain_session(
                    int(bargain_create_match.group(1)),
                    ttl_hours=int(payload.get("ttl_hours") or 48),
                )
                self._json({"ok": True, **(result or {})})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                msg = str(exc)
                self._json({"ok": False, "error": msg}, status=503 if "company_db_postgres_runtime_required" in msg else 500)
            return

        bargain_action_match = re.fullmatch(r"/api/v2/purchases/orders/(\d+)/bargain/(\d+)/(accept|reject)", path)
        if bargain_action_match:
            session_id = int(bargain_action_match.group(2))
            action = bargain_action_match.group(3)
            try:
                result = accept_bargain(session_id) if action == "accept" else reject_bargain(session_id)
                self._json({"ok": True, **(result or {})})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                msg = str(exc)
                self._json({"ok": False, "error": msg}, status=503 if "company_db_postgres_runtime_required" in msg else 500)
            return

        if path == "/api/purchases/orders/create":
            payload = self._read_json()
            session = self._current_session() or {}
            actor = session.get("username") or session.get("email") or session.get("user_id") or "dashboard"
            try:
                detail = create_purchase_order(
                    vendor_name=payload.get("vendor_name"),
                    lines=payload.get("lines") or [],
                    status=payload.get("status") or "draft",
                    order_date=payload.get("order_date"),
                    expected_date=payload.get("expected_date"),
                    notes=payload.get("notes"),
                    shipping_cost=payload.get("shipping_cost") or 0,
                    tax_cost=payload.get("tax_cost") or 0,
                    misc_cost=payload.get("misc_cost") or 0,
                    created_by=actor,
                )
                self._json({"ok": True, **detail})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/purchases/orders/update":
            payload = self._read_json()
            order_id = payload.get("order_id") or payload.get("id")
            if not order_id:
                self._json({"ok": False, "error": "order_id required"}, status=400)
                return
            try:
                detail = update_purchase_order(
                    int(order_id),
                    vendor_name=payload.get("vendor_name"),
                    status=payload.get("status"),
                    order_date=payload.get("order_date"),
                    expected_date=payload.get("expected_date"),
                    notes=payload.get("notes"),
                    shipping_cost=payload.get("shipping_cost"),
                    tax_cost=payload.get("tax_cost"),
                    misc_cost=payload.get("misc_cost"),
                    lines=payload.get("lines") or [],
                )
                self._json({"ok": True, **detail})
            except ValueError as exc:
                msg = str(exc)
                self._json({"ok": False, "error": msg}, status=404 if "not_found" in msg else 400)
            except Exception as exc:
                msg = str(exc)
                self._json({"ok": False, "error": msg}, status=503 if "company_db_postgres_runtime_required" in msg else 500)
            return

        if path == "/api/purchases/orders/delete":
            payload = self._read_json()
            order_id = payload.get("order_id") or payload.get("id")
            if not order_id:
                self._json({"ok": False, "error": "order_id required"}, status=400)
                return
            try:
                result = delete_purchase_order(int(order_id))
                self._json({"ok": True, **(result or {})})
            except ValueError as exc:
                msg = str(exc)
                self._json({"ok": False, "error": msg}, status=404 if "not_found" in msg else 400)
            except Exception as exc:
                msg = str(exc)
                self._json({"ok": False, "error": msg}, status=503 if "company_db_postgres_runtime_required" in msg else 500)
            return

        if path == "/api/purchases/orders/receive":
            payload = self._read_json()
            order_id = payload.get("order_id") or payload.get("id")
            if not order_id:
                self._json({"ok": False, "error": "order_id required"}, status=400)
                return
            session = self._current_session() or {}
            actor = session.get("username") or session.get("email") or session.get("user_id") or "dashboard"
            try:
                result = receive_purchase_order(
                    int(order_id),
                    payload.get("receipts") or [],
                    received_by=actor,
                )
                self._json({"ok": True, **result})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                msg = str(exc)
                self._json({"ok": False, "error": msg}, status=503 if "company_db_postgres_runtime_required" in msg else 500)
            return

        if path == "/api/sessions/create":
            payload = self._read_json()
            name = (payload.get("name") or "").strip()
            if not name:
                self._json({"ok": False, "error": "name required"}, status=400)
                return
            try:
                result = create_company_session(
                    show_id=payload.get("show_id"),
                    whatnot_account=payload.get("whatnot_account") or OUR_WHATNOT_ACCOUNT,
                    name=name,
                    status=payload.get("status", "live"),
                )
                self._json({"ok": True, "id": result.get("id"), "session": result})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/alerts/settings" and method == "POST":
            payload = self._read_json()
            try:
                if "margin_threshold" in payload:
                    upsert_setting("alert_margin_threshold", str(payload["margin_threshold"]))
                if "buyer_lots_threshold" in payload:
                    upsert_setting("alert_buyer_lots_threshold", str(payload["buyer_lots_threshold"]))
                self._json({"ok": True})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/sessions/update":
            payload = self._read_json()
            session_id = payload.get("session_id") or payload.get("id")
            if not session_id:
                self._json({"ok": False, "error": "session_id required"}, status=400)
                return
            try:
                vals = {}
                if payload.get("name") is not None:
                    vals["name"] = payload.get("name")
                if payload.get("status") is not None:
                    vals["status"] = payload.get("status")
                if payload.get("whatnot_account") is not None:
                    vals["whatnot_account"] = payload.get("whatnot_account")
                if payload.get("show_id") is not None:
                    vals["show_id"] = payload.get("show_id")
                if payload.get("end_time") is not None:
                    vals["ended_at"] = payload.get("end_time")
                result = update_company_session(int(session_id), **vals)
                self._json({"ok": bool(result), "session": result})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/sale_orders/update":
            payload = self._read_json()
            order_id = payload.get("order_id") or payload.get("id")
            if not order_id:
                self._json({"ok": False, "error": "order_id required"}, status=400)
                return
            try:
                current = get_sale_order(int(order_id))
                if not current:
                    self._json({"ok": False, "error": "order_not_found"}, status=404)
                    return
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
                    vals.setdefault("fulfillment_status", "delivered")
                new_state = vals.get("state")
                # Cancelled orders should not be shipped/packed/paid
                if new_state == "cancel":
                    vals["fulfillment_status"] = "pending"
                    vals["payment_status"] = "unpaid"
                order = update_sale_order(int(order_id), **vals)
                # Apply/reverse inventory when order state changes
                if new_state and current.get("state") != new_state:
                    if new_state == "sale":
                        apply_sale_order_inventory(int(order_id))
                    elif new_state == "cancel" and str(current.get("order_source") or "").strip().lower() != "tiktok_live":
                        reverse_sale_order_inventory(int(order_id))
                if order:
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
                self._json({"ok": bool(order), "order": order})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/auction_results/update":
            payload = self._read_json()
            result_id = payload.get("result_id") or payload.get("id")
            if not result_id:
                self._json({"ok": False, "error": "result_id required"}, status=400)
                return
            try:
                current = get_auction_result(int(result_id))
                if not current:
                    self._json({"ok": False, "error": "result_not_found"}, status=404)
                    return
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
                self._json({"ok": bool(result), "result": result})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/auction_results/create":
            payload = self._read_json()
            session_id = payload.get("session_id")
            lot_number = payload.get("lot_number")
            winner_username = str(payload.get("winner_username") or payload.get("customer_name") or "").strip()
            if not session_id:
                self._json({"ok": False, "error": "session_id required"}, status=400)
                return
            if not lot_number:
                self._json({"ok": False, "error": "lot_number required"}, status=400)
                return
            if not winner_username:
                self._json({"ok": False, "error": "winner_username required"}, status=400)
                return
            try:
                customer = get_customer_by_username(winner_username)
                if not customer:
                    customer = upsert_customer(winner_username, display_name=winner_username)
                result = record_auction_result(
                    int(session_id),
                    lot_number=str(lot_number).strip(),
                    winner_username=winner_username,
                    customer_id=customer.get("id") if customer else None,
                    sale_price=float(payload.get("sale_price") or 0),
                    fees=float(payload.get("fees") or 0),
                    cost_price=float(payload.get("cost_price") or 0),
                    product_name=(payload.get("product_name") or "").strip() or None,
                    barcode=(payload.get("barcode") or "").strip() or None,
                    sku=(payload.get("sku") or "").strip() or None,
                    products_sold_count=int(payload.get("products_sold_count") or 1),
                    source_event_id=(payload.get("source_event_id") or f"manual-{int(session_id)}-{str(lot_number).strip()}-{winner_username.lower()}"),
                )
                self._json({"ok": True, "result": result})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/sale_orders/bulk_update":
            payload = self._read_json()
            order_ids = payload.get("order_ids") or []
            if not order_ids:
                self._json({"ok": False, "error": "order_ids required"}, status=400)
                return
            try:
                vals = {}
                if payload.get("state") is not None:
                    vals["state"] = payload.get("state")
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
                if payload.get("delivered_at") is not None:
                    vals["delivered_at"] = payload.get("delivered_at")
                if payload.get("mark_packed"):
                    vals["packed_at"] = datetime.now(timezone.utc).isoformat()
                    vals["fulfillment_status"] = "packed"
                if payload.get("mark_shipped"):
                    now = datetime.now(timezone.utc).isoformat()
                    vals["shipped_at"] = now
                    vals["fulfillment_status"] = "shipped"
                if vals.get("tracking_status") == "delivered":
                    vals.setdefault("delivered_at", datetime.now(timezone.utc).isoformat())
                    vals.setdefault("fulfillment_status", "delivered")
                new_state = vals.get("state")
                # Cancelled orders should not be shipped/packed/paid
                if new_state == "cancel":
                    vals["fulfillment_status"] = "pending"
                    vals["payment_status"] = "unpaid"
                # Capture current states before bulk update for inventory tracking
                pre_states = {}
                pre_sources = {}
                if new_state in ("sale", "cancel"):
                    for oid in order_ids:
                        try:
                            o = get_sale_order(int(oid))
                            if o:
                                pre_states[int(oid)] = o.get("state")
                                pre_sources[int(oid)] = str(o.get("order_source") or "").strip().lower()
                        except Exception:
                            pass
                rows = bulk_update_sale_orders(order_ids, **vals)
                for row in rows:
                    row["name"] = row.get("order_number")
                    row["date_order"] = row.get("ordered_at")
                    row["partner_id_name"] = row.get("display_name")
                    row["whatnot_session_id_name"] = row.get("session_name")
                    row["amount_total"] = row.get("total_amount")
                    row["amount_untaxed"] = row.get("subtotal")
                    row["order_revenue"] = row.get("linked_revenue") or 0
                    row["order_cost"] = row.get("linked_cost") or 0
                    row["order_fees"] = row.get("linked_fees") or 0
                    row["order_profit"] = row.get("linked_profit") or 0
                    row["order_margin_pct"] = row.get("linked_margin_pct") or 0
                    row["tracking_url"] = _tracking_url(row.get("tracking_carrier"), row.get("tracking_number"))
                # Apply/reverse inventory for each order whose state actually changed
                if new_state in ("sale", "cancel"):
                    for oid in order_ids:
                        try:
                            if pre_states.get(int(oid)) != new_state:
                                if new_state == "sale":
                                    apply_sale_order_inventory(int(oid))
                                elif new_state == "cancel" and pre_sources.get(int(oid)) != "tiktok_live":
                                    reverse_sale_order_inventory(int(oid))
                        except Exception:
                            pass
                self._json({"ok": True, "updated": len(rows), "rows": rows})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/packing_scanner/event":
            payload = self._read_json()
            try:
                event = _append_packing_scanner_event(payload)
                self._json({"ok": True, "event": event})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return

        if path == "/api/sale_orders/line/save":
            payload = self._read_json()
            order_id = payload.get("order_id")
            line_id = payload.get("line_id") or payload.get("id")
            if not order_id and not line_id:
                self._json({"ok": False, "error": "order_id or line_id required"}, status=400)
                return
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
                self._json({"ok": bool(line), "line": line})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/sale_orders/line/delete":
            payload = self._read_json()
            line_id = payload.get("line_id") or payload.get("id")
            if not line_id:
                self._json({"ok": False, "error": "line_id required"}, status=400)
                return
            try:
                ok = delete_sale_order_line(int(line_id))
                self._json({"ok": ok})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_shop_orders/create":
            payload = self._read_json()
            product_id = payload.get("product_id")
            if not product_id:
                self._json({"ok": False, "error": "product_id required"}, status=400)
                return
            try:
                product = get_product(int(product_id))
                if not product:
                    self._json({"ok": False, "error": "product_not_found"}, status=404)
                    return
                qty = max(1.0, float(payload.get("qty") or 1))
                unit_price = float(payload.get("unit_price") or 0)
                buyer_username = (payload.get("buyer_username") or "").strip() or None
                customer = upsert_customer(
                    buyer_username,
                    display_name=buyer_username,
                    platform="tiktok_shop",
                    platform_user_id=buyer_username,
                    identity_username=buyer_username,
                ) if buyer_username else None
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
                created = get_sale_order(int(order["id"]))
                lines = list_sale_order_lines(int(order["id"]))
                self._json({"ok": True, "order": created, "lines": lines})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_orders/create":
            payload = self._read_json()
            product_id = payload.get("product_id")
            if not product_id:
                self._json({"ok": False, "error": "product_id required"}, status=400)
                return
            try:
                product = get_product(int(product_id))
                if not product:
                    self._json({"ok": False, "error": "product_not_found"}, status=404)
                    return
                qty = max(1.0, float(payload.get("qty") or 1))
                unit_price = float(payload.get("unit_price") or 0)
                buyer_username = (payload.get("buyer_username") or "").strip() or None
                external_order_ref = (payload.get("external_order_ref") or "").strip() or None
                ordered_at = payload.get("ordered_at") or datetime.now(timezone.utc).isoformat()
                notes = (payload.get("notes") or "").strip() or "TikTok LIVE order"
                description = (payload.get("description") or product.get("name") or "").strip() or product.get("name")
                order = create_sale_order(
                    session_id=None,
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
                created = get_sale_order(int(order["id"]))
                lines = list_sale_order_lines(int(order["id"]))
                self._json({"ok": True, "order": created, "lines": lines})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_shop_orders/import_csv":
            payload = self._read_json()
            csv_text = payload.get("csv_text") or ""
            xlsx_base64 = payload.get("xlsx_base64") or ""
            commit = bool(payload.get("commit"))
            if not csv_text.strip() and xlsx_base64:
                csv_text = _xlsx_base64_to_csv_text(xlsx_base64)
                if not csv_text.strip():
                    self._json({"ok": False, "error": "csv_text or xlsx_base64 required"}, status=400)
                    return
            try:
                target_session = get_company_session(int(target_session_id)) if target_session_id else None
                target_session_ended = str((target_session or {}).get("status") or "").strip().lower() in {"ended", "archived"}
                products = list_products(active_only=False, low_stock_only=False)
                existing_refs = {
                    (row.get("external_order_ref") or "").strip()
                    for row in list_sale_orders(order_source="tiktok_shop")
                    if (row.get("external_order_ref") or "").strip()
                }
                csv_rows = list(csv.DictReader(io.StringIO(csv_text)))
                batch_lines = []
                for raw_row in csv_rows:
                    mapped_for_batch = _tiktok_normalized_row(raw_row)
                    if _is_tiktok_export_description_row(mapped_for_batch):
                        continue
                    batch_lines.append({
                        "seller_sku": (mapped_for_batch.get("seller_sku") or "").strip(),
                        "product_name": (mapped_for_batch.get("combined_listing") or mapped_for_batch.get("product_name") or "").strip(),
                        "created_at": mapped_for_batch.get("created_at"),
                        "paid_at": mapped_for_batch.get("paid_at"),
                        "updated_at": mapped_for_batch.get("updated_at"),
                    })
                live_batch_by_title = _tiktok_live_generic_batch_map(batch_lines)
                preview_rows = []
                imported = []
                csv_seen_rows = set()
                unique_orders = set()
                unique_packages = set()
                missing_seller_sku_rows = 0
                missing_barcode_rows = 0
                duplicate_row_keys = 0
                barcode_mismatch_rows = 0
                live_listing_rows = 0
                for idx, row in enumerate(csv_rows, start=2):
                    mapped = _tiktok_normalized_row(row)
                    if _is_tiktok_export_description_row(mapped):
                        continue
                    product_name = (mapped.get("combined_listing") or mapped.get("product_name") or "").strip()
                    buyer_username = (mapped.get("buyer_username") or "").strip() or None
                    seller_sku = (mapped.get("seller_sku") or "").strip()
                    barcode = (mapped.get("barcode") or "").strip()
                    qty = max(1.0, _parse_tiktok_float(mapped.get("quantity"), 1))
                    unit_price = _parse_tiktok_float(mapped.get("unit_price_original"), 0)
                    subtotal = _parse_tiktok_float(mapped.get("subtotal_before_discount"), unit_price * qty)
                    if unit_price <= 0 and qty > 0:
                        unit_price = round(subtotal / qty, 2)
                    external_order_ref = _build_tiktok_external_ref(mapped, source="tiktok_shop", row_number=idx)
                    is_live_listing = _is_tiktok_live_generic_listing({
                        "seller_sku": seller_sku,
                        "product_name": product_name,
                    })
                    product, matched_by, score, warning = _tiktok_match_product(products, mapped)
                    is_cancelled = _is_tiktok_cancelled(mapped, unit_price=unit_price, subtotal=subtotal)
                    status = "ready"
                    order_id = (mapped.get("external_order_id") or "").strip()
                    package_id = (mapped.get("external_package_id") or "").strip()
                    row_key = (order_id, seller_sku, barcode)
                    if order_id:
                        unique_orders.add(order_id)
                    if package_id:
                        unique_packages.add(package_id)
                    if not seller_sku:
                        missing_seller_sku_rows += 1
                    if not barcode:
                        missing_barcode_rows += 1
                    if external_order_ref and external_order_ref in existing_refs:
                        status = "duplicate"
                    elif row_key in csv_seen_rows and row_key != ("", "", ""):
                        duplicate_row_keys += 1
                        status = "duplicate"
                    elif is_live_listing:
                        live_listing_rows += 1
                        status = "live_listing_rejected"
                    elif is_cancelled:
                        status = "cancelled"
                    elif not product:
                        status = "unmatched"
                    else:
                        csv_seen_rows.add(row_key)
                    if warning == "barcode_mismatch":
                        barcode_mismatch_rows += 1
                    preview = {
                        "row_number": idx,
                        "order_id": order_id,
                        "external_order_ref": external_order_ref,
                        "seller_sku": seller_sku,
                        "barcode": barcode,
                        "package_id": package_id,
                        "tracking_number": (mapped.get("tracking_number") or "").strip() or None,
                        "order_status": (mapped.get("order_status") or "").strip() or None,
                        "buyer_username": buyer_username,
                        "product_name": product_name,
                        "qty": qty,
                        "unit_price": unit_price,
                        "subtotal": subtotal,
                        "order_total": _parse_tiktok_float(mapped.get("order_total"), subtotal),
                        "matched_product_id": product.get("id") if product else None,
                        "matched_inventory_name": product.get("name") if product else None,
                        "matched_by": matched_by,
                        "match_score": score,
                        "warning": "live_listing_use_tiktok_live_import" if is_live_listing else warning,
                        "is_cancelled": is_cancelled,
                        "status": status,
                    }
                    preview_rows.append(preview)
                    if commit and status in ("ready", "cancelled"):
                        customer_key = _tiktok_customer_key(mapped, source="tiktok_shop")
                        address_parts = [
                            mapped.get("address_line_1"),
                            mapped.get("address_line_2"),
                            mapped.get("city"),
                            mapped.get("state"),
                            mapped.get("zipcode"),
                            mapped.get("country"),
                        ]
                        address = ", ".join([part for part in address_parts if part])
                        customer = upsert_customer(
                            customer_key,
                            display_name=(mapped.get("recipient_name") or mapped.get("buyer_nickname") or mapped.get("buyer_username") or None),
                            email=(mapped.get("email") or None),
                            phone=(mapped.get("phone") or None),
                            address=address or None,
                            notes=(mapped.get("buyer_message") or None),
                            platform="tiktok_shop",
                            platform_user_id=(mapped.get("buyer_username") or mapped.get("external_order_id") or customer_key),
                            identity_username=(mapped.get("buyer_username") or mapped.get("buyer_nickname") or None),
                        ) if customer_key else None
                        order = create_sale_order(
                            session_id=None,
                            customer_id=customer.get("id") if customer else None,
                            buyer_group_id=None,
                            whatnot_buyer_username=buyer_username,
                            state="cancel" if status == "cancelled" else "sale",
                            subtotal=0,
                            total_amount=0,
                            ordered_at=_parse_tiktok_datetime(mapped.get("paid_at")) or _parse_tiktok_datetime(mapped.get("created_at")) or datetime.now(timezone.utc).isoformat(),
                            notes=_build_tiktok_order_note(row),
                            order_source="tiktok_shop",
                            external_order_ref=external_order_ref or None,
                            fulfillment_status=_tiktok_fulfillment_status(mapped, is_cancelled=status == "cancelled"),
                            payment_status=_tiktok_payment_status(mapped, is_cancelled=status == "cancelled"),
                        )
                        add_sale_order_line(
                            int(order["id"]),
                            product_id=int(product["id"]),
                            description=product.get("name") or product_name,
                            qty=qty,
                            unit_price=unit_price,
                            inventory_applied=0,
                        )
                        if status != "cancelled" and (not target_session_id or target_session_ended):
                            apply_sale_order_inventory(int(order["id"]))
                        imported.append({
                            "order_id": order["id"],
                            "order_number": order["order_number"],
                            "external_order_ref": external_order_ref,
                        })
                        if external_order_ref:
                            existing_refs.add(external_order_ref)
                summary = {
                    "total_rows": len(preview_rows),
                    "unique_orders": len(unique_orders),
                    "unique_packages": len(unique_packages),
                    "ready_rows": sum(1 for row in preview_rows if row["status"] == "ready"),
                    "cancelled_rows": sum(1 for row in preview_rows if row["status"] == "cancelled"),
                    "duplicate_rows": sum(1 for row in preview_rows if row["status"] == "duplicate"),
                    "unmatched_rows": sum(1 for row in preview_rows if row["status"] == "unmatched"),
                    "live_listing_rejected_rows": live_listing_rows,
                    "missing_seller_sku_rows": missing_seller_sku_rows,
                    "missing_barcode_rows": missing_barcode_rows,
                    "duplicate_row_keys": duplicate_row_keys,
                    "barcode_mismatch_rows": barcode_mismatch_rows,
                    "imported_rows": len(imported),
                }
                self._json({"ok": True, "rows": preview_rows, "summary": summary, "imported": imported})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/tiktok_live_orders/import_csv":
            payload = self._read_json()
            csv_text = payload.get("csv_text") or ""
            xlsx_base64 = payload.get("xlsx_base64") or ""
            lot_map_csv_text = payload.get("lot_map_csv_text") or ""
            target_session_id = payload.get("session_id") or None
            commit = bool(payload.get("commit"))
            if not csv_text.strip() and xlsx_base64:
                csv_text = _xlsx_base64_to_csv_text(xlsx_base64)
            if not csv_text.strip():
                self._json({"ok": False, "error": "csv_text or xlsx_base64 required"}, status=400)
                return
            try:
                products = list_products(active_only=False, low_stock_only=False)
                lot_map = _build_tiktok_live_lot_map(lot_map_csv_text, products)
                existing_refs = {
                    (row.get("external_order_ref") or "").strip()
                    for row in list_sale_orders(order_source="tiktok_live")
                    if (row.get("external_order_ref") or "").strip()
                }
                reader = csv.DictReader(io.StringIO(csv_text))
                preview_rows = []
                imported = []
                csv_seen_rows = set()
                unique_orders = set()
                unique_packages = set()
                missing_seller_sku_rows = 0
                missing_barcode_rows = 0
                duplicate_row_keys = 0
                barcode_mismatch_rows = 0
                for idx, row in enumerate(csv_rows, start=2):
                    mapped = _tiktok_normalized_row(row)
                    if _is_tiktok_export_description_row(mapped):
                        continue
                    original_product_name = (mapped.get("combined_listing") or mapped.get("product_name") or "").strip()
                    product_name = original_product_name
                    seller_sku = (mapped.get("seller_sku") or "").strip()
                    live_lot_number = _tiktok_live_final_lot_number_for_line(
                        {
                            "seller_sku": seller_sku,
                            "product_name": original_product_name,
                            "created_at": mapped.get("created_at"),
                            "paid_at": mapped.get("paid_at"),
                            "updated_at": mapped.get("updated_at"),
                        },
                        live_batch_by_title,
                    )
                    lot_number = live_lot_number or (seller_sku or _extract_lot_number(row) or "").strip()
                    lot_match = lot_map.get(_normalize_lot_number(lot_number))
                    external_order_ref = _build_tiktok_external_ref(mapped, source="tiktok_live", row_number=idx)
                    buyer_username = (mapped.get("buyer_username") or "").strip() or None
                    qty = max(1.0, _parse_tiktok_float(mapped.get("quantity"), 1))
                    unit_price = _parse_tiktok_float(mapped.get("unit_price_original"), 0)
                    subtotal = _parse_tiktok_float(mapped.get("subtotal_before_discount"), unit_price * qty)
                    if unit_price <= 0 and qty > 0:
                        unit_price = round(subtotal / qty, 2)
                    order_id = (mapped.get("external_order_id") or "").strip()
                    if live_lot_number:
                        external_order_ref = f"tiktok_live:{order_id or 'row'}:{live_lot_number}"
                    package_id = (mapped.get("external_package_id") or "").strip()
                    barcode = (mapped.get("barcode") or "").strip()
                    product = lot_match.get("product") if lot_match else None
                    matched_by = "lot_map" if product else None
                    score = 100 if product else 0
                    warning = None
                    if not product:
                        product, matched_by, score, warning = _tiktok_match_product(products, mapped)
                    product_name = _resolved_tiktok_live_product_name(original_product_name, lot_match=lot_match, product=product)
                    status = "ready"
                    is_cancelled = _is_tiktok_cancelled(mapped, unit_price=unit_price, subtotal=subtotal)
                    row_key = (order_id, seller_sku, barcode)
                    if order_id:
                        unique_orders.add(order_id)
                    if package_id:
                        unique_packages.add(package_id)
                    if not seller_sku:
                        missing_seller_sku_rows += 1
                    if not barcode:
                        missing_barcode_rows += 1
                    if external_order_ref and external_order_ref in existing_refs:
                        status = "duplicate"
                    elif row_key in csv_seen_rows and row_key != ("", "", ""):
                        duplicate_row_keys += 1
                        status = "duplicate"
                    elif is_cancelled:
                        status = "cancelled"
                    elif not product:
                        status = "unmatched"
                    else:
                        csv_seen_rows.add(row_key)
                    if warning == "barcode_mismatch":
                        barcode_mismatch_rows += 1
                    preview = {
                        "row_number": idx,
                        "order_id": order_id,
                        "external_order_ref": external_order_ref,
                        "buyer_username": buyer_username,
                        "lot_number": lot_number,
                        "seller_sku": seller_sku,
                        "live_lot_number": live_lot_number or None,
                        "barcode": barcode,
                        "package_id": package_id,
                        "tracking_number": (mapped.get("tracking_number") or "").strip() or None,
                        "order_status": (mapped.get("order_status") or "").strip() or None,
                        "product_name": product_name,
                        "original_product_name": original_product_name if original_product_name != product_name else None,
                        "qty": qty,
                        "unit_price": unit_price,
                        "subtotal": subtotal,
                        "order_total": _parse_tiktok_float(mapped.get("order_total"), subtotal),
                        "lot_map_barcode": lot_match.get("barcode") if lot_match else None,
                        "lot_map_sku": lot_match.get("sku") if lot_match else None,
                        "matched_product_id": product.get("id") if product else None,
                        "matched_inventory_name": product.get("name") if product else None,
                        "matched_by": matched_by,
                        "match_score": score,
                        "warning": warning,
                        "is_cancelled": is_cancelled,
                        "status": status,
                    }
                    preview_rows.append(preview)
                    if commit and status in ("ready", "cancelled"):
                        customer_key = _tiktok_customer_key(mapped, source="tiktok_live")
                        address_parts = [
                            mapped.get("address_line_1"),
                            mapped.get("address_line_2"),
                            mapped.get("city"),
                            mapped.get("state"),
                            mapped.get("zipcode"),
                            mapped.get("country"),
                        ]
                        address = ", ".join([part for part in address_parts if part])
                        customer = upsert_customer(
                            customer_key,
                            display_name=(mapped.get("recipient_name") or mapped.get("buyer_nickname") or mapped.get("buyer_username") or None),
                            email=(mapped.get("email") or None),
                            phone=(mapped.get("phone") or None),
                            address=address or None,
                            notes=(mapped.get("buyer_message") or None),
                            platform="tiktok_live",
                            platform_user_id=(mapped.get("buyer_username") or mapped.get("external_order_id") or customer_key),
                            identity_username=(mapped.get("buyer_username") or mapped.get("buyer_nickname") or None),
                        ) if customer_key else None
                        order = create_sale_order(
                            session_id=int(target_session_id) if target_session_id else None,
                            customer_id=customer.get("id") if customer else None,
                            buyer_group_id=None,
                            whatnot_buyer_username=buyer_username,
                            state="cancel" if status == "cancelled" else "sale",
                            subtotal=0,
                            total_amount=0,
                            ordered_at=_parse_tiktok_datetime(mapped.get("paid_at")) or _parse_tiktok_datetime(mapped.get("created_at")) or datetime.now(timezone.utc).isoformat(),
                            notes=_build_tiktok_order_note(row),
                            order_source="tiktok_live",
                            external_order_ref=external_order_ref or None,
                            fulfillment_status=_tiktok_live_fulfillment_status(mapped, is_cancelled=status == "cancelled"),
                            payment_status=_tiktok_payment_status(mapped, is_cancelled=status == "cancelled"),
                        )
                        add_sale_order_line(
                            int(order["id"]),
                            product_id=int(product["id"]),
                            description=product.get("name") or product_name,
                            qty=qty,
                            unit_price=unit_price,
                            inventory_applied=0,
                        )
                        if status != "cancelled":
                            apply_sale_order_inventory(int(order["id"]))
                        imported.append({
                            "order_id": order["id"],
                            "order_number": order["order_number"],
                            "external_order_ref": external_order_ref,
                        })
                        if external_order_ref:
                            existing_refs.add(external_order_ref)
                summary = {
                    "total_rows": len(preview_rows),
                    "unique_orders": len(unique_orders),
                    "unique_packages": len(unique_packages),
                    "ready_rows": sum(1 for row in preview_rows if row["status"] == "ready"),
                    "cancelled_rows": sum(1 for row in preview_rows if row["status"] == "cancelled"),
                    "duplicate_rows": sum(1 for row in preview_rows if row["status"] == "duplicate"),
                    "unmatched_rows": sum(1 for row in preview_rows if row["status"] == "unmatched"),
                    "missing_seller_sku_rows": missing_seller_sku_rows,
                    "missing_barcode_rows": missing_barcode_rows,
                    "duplicate_row_keys": duplicate_row_keys,
                    "barcode_mismatch_rows": barcode_mismatch_rows,
                    "imported_rows": len(imported),
                }
                self._json({"ok": True, "rows": preview_rows, "summary": summary, "imported": imported})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/customers/update":
            payload = self._read_json()
            customer_id = payload.get("customer_id") or payload.get("id")
            if not customer_id:
                self._json({"ok": False, "error": "customer_id required"}, status=400)
                return
            try:
                current = get_customer(int(customer_id))
                if not current:
                    self._json({"ok": False, "error": "customer_not_found"}, status=404)
                    return
                customer = update_customer(
                    int(customer_id),
                    display_name=payload.get("display_name"),
                    email=payload.get("email"),
                    phone=payload.get("phone"),
                    notes=payload.get("notes"),
                )
                if customer:
                    customer["name"] = customer.get("display_name")
                self._json({"ok": bool(customer), "customer": customer})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/fee_settings/save":
            payload = self._read_json()
            try:
                if "platform_fee_pct" in payload:
                    upsert_setting("platform_fee_pct", float(payload["platform_fee_pct"]))
                if "fixed_fee" in payload:
                    upsert_setting("fixed_fee", float(payload["fixed_fee"]))
                self._json({"ok": True})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/recalc_fees":
            try:
                _settings = get_setting_map()
                _fee_pct = float(_settings.get("platform_fee_pct", 10.9))
                _fixed_fee = float(_settings.get("fixed_fee", 0.50))
                from .company_db import recalc_all_fees
                count = recalc_all_fees(fee_pct=_fee_pct, fixed_fee=_fixed_fee)
                self._json({"ok": True, "updated": count, "fee_pct": _fee_pct, "fixed_fee": _fixed_fee})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/company/sync_from_odoo":
            self._json(
                {
                    "ok": False,
                    "error": "odoo_sync_retired",
                    "message": "Odoo sync has been retired and is no longer supported.",
                },
                status=410,
            )
            return

        if path == "/api/inventory/categories":
            payload = self._read_json()
            try:
                cat = ensure_category(payload.get("name", ""))
                if not cat:
                    self._json({"ok": False, "error": "name required"}, status=400)
                    return
                self._json({"ok": True, "category": cat})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/inventory/categories/delete":
            payload = self._read_json()
            cat_id = payload.get("id")
            if not cat_id:
                self._json({"ok": False, "error": "id required"}, status=400)
                return
            try:
                delete_category(int(cat_id))
                self._json({"ok": True})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/inventory/product/delete":
            payload = self._read_json()
            product_id = payload.get("product_id") or payload.get("id")
            if not product_id:
                self._json({"ok": False, "error": "product_id required"}, status=400)
                return
            try:
                result = delete_product(int(product_id))
                self._json({"ok": True, **(result or {})})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/inventory/adjust_stock":
            payload = self._read_json()
            product_id = payload.get("product_id") or payload.get("id")
            if not product_id:
                self._json({"ok": False, "error": "product_id required"}, status=400)
                return
            try:
                product_id = int(product_id)
                product = get_product(product_id)
                if not product:
                    self._json({"ok": False, "error": "product not found"}, status=404)
                    return

                current_qty = float(product.get("on_hand_qty") or 0.0)
                expected_current = payload.get("expected_current_qty")
                if expected_current not in (None, ""):
                    expected_qty = float(expected_current or 0.0)
                    if abs(expected_qty - current_qty) > 0.0001:
                        self._json(
                            {
                                "ok": False,
                                "error": "stock_changed_since_loaded",
                                "current_qty": current_qty,
                                "expected_current_qty": expected_qty,
                            },
                            status=409,
                        )
                        return

                if "target_qty" in payload:
                    target_qty = float(payload.get("target_qty") or 0.0)
                    qty_delta = target_qty - current_qty
                else:
                    qty_delta = float(payload.get("qty_delta") or 0.0)
                    target_qty = current_qty + qty_delta
                if target_qty < -0.0001:
                    self._json({"ok": False, "error": "stock_cannot_go_negative"}, status=400)
                    return
                if abs(qty_delta) <= 0.0001:
                    row = product
                    stock_adjusted = False
                else:
                    adjustment_reason = str(payload.get("adjustment_reason") or payload.get("reason") or "").strip()
                    if not adjustment_reason:
                        self._json({"ok": False, "error": "adjustment_reason_required"}, status=400)
                        return
                    record_inventory_movement(
                        product_id,
                        "adjustment",
                        qty_delta,
                        reason=adjustment_reason,
                        reference_type="inventory_adjustment",
                        reference_id=product_id,
                    )
                    row = get_product(product_id)
                    stock_adjusted = True

                row = row or {}
                row["default_code"] = row.get("sku")
                row["standard_price"] = row.get("cost_price")
                row["list_price"] = row.get("retail_price")
                row["qty_available"] = row.get("on_hand_qty")
                row["type"] = row.get("product_type")
                row["categ_name"] = row.get("category_name")
                row["image_url"] = _product_image_url(row)
                self._json({"ok": True, "stock_adjusted": stock_adjusted, "product": row})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/inventory/product/update":
            payload = self._read_json()
            product_id = payload.get("product_id") or payload.get("id")
            try:
                name = (payload.get("name") or "").strip()
                if not product_id and not name:
                    self._json({"ok": False, "error": "name required"}, status=400)
                    return
                category_id = int(payload["categ_id"]) if payload.get("categ_id") else None
                if not category_id and payload.get("category_name"):
                    cat = ensure_category(payload.get("category_name"))
                    category_id = cat.get("id") if cat else None
                remote_image_128 = None
                if not payload.get("image_128") and payload.get("media_url"):
                    try:
                        remote_image_128 = _download_image_as_base64(payload.get("media_url"))
                    except Exception:
                        remote_image_128 = None

                if product_id:
                    auth_session = self._current_session()
                    audit_actor = (
                        auth_session.get("username")
                        or auth_session.get("email")
                        or auth_session.get("user_id")
                    ) if auth_session else None
                    existing_product = get_product(int(product_id))
                    if not existing_product:
                        self._json({"ok": False, "error": "product not found"}, status=404)
                        return

                    # Text fields that are explicitly cleared by the user are sent
                    # as empty string "". To distinguish "user cleared this" from
                    # "form never loaded this field", we use a special sentinel:
                    # only treat the payload value as intentional if it is not an
                    # empty string. If it IS empty, fall back to the existing DB
                    # value so a stale or partially-loaded form never wipes data.
                    # To deliberately clear a text field, the frontend must send
                    # the key mapped to None (null in JSON).
                    def _payload_or_existing(payload_key, existing_key=None, default=None):
                        if payload_key in payload:
                            val = payload.get(payload_key)
                            # Non-empty value sent → use it (user set or cleared it explicitly)
                            if val is not None and val != "":
                                return val
                            # null (None) sent → intentional clear
                            if val is None:
                                return None
                            # Empty string sent → treat as "not provided", keep DB value
                        lookup_key = existing_key or payload_key
                        if existing_product.get(lookup_key) is not None:
                            return existing_product.get(lookup_key)
                        return default

                    if "category_name" in payload and payload.get("category_name"):
                        effective_category_id = category_id
                    elif "categ_id" in payload:
                        effective_category_id = category_id
                    else:
                        effective_category_id = existing_product.get("category_id")

                    notes_verified = 1 if _payload_or_existing("notes_verified", "notes_verified", 0) else 0
                    if "notes_verified" in payload:
                        if notes_verified:
                            notes_verified_at = existing_product.get("notes_verified_at") or datetime.now(timezone.utc).isoformat()
                        else:
                            notes_verified_at = None
                    else:
                        notes_verified_at = existing_product.get("notes_verified_at")

                    update_fields = dict(
                        name=name or existing_product.get("name"),
                        sku=_payload_or_existing("default_code", "sku"),
                        barcode=_payload_or_existing("barcode"),
                        category_id=effective_category_id,
                        brand=_payload_or_existing("brand"),
                        gender=_payload_or_existing("gender"),
                        supplier_name=_payload_or_existing("supplier_name"),
                        storage_bin=_payload_or_existing("storage_bin"),
                        product_type=_payload_or_existing("type", "product_type", "product"),
                        cost_price=float(_payload_or_existing("standard_price", "cost_price", 0.0) or 0.0),
                        raw_cost=float(_payload_or_existing("raw_cost", "raw_cost", 0.0) or 0.0),
                        cost_plus_12=float(_payload_or_existing("cost_plus_12", "cost_plus_12", 0.0) or 0.0),
                        cost_plus_20=float(_payload_or_existing("cost_plus_20", "cost_plus_20", 0.0) or 0.0),
                        retail_price=float(_payload_or_existing("list_price", "retail_price", 0.0) or 0.0),
                        low_stock_threshold=float(_payload_or_existing("low_stock_threshold", "low_stock_threshold", 3.0) or 3.0),
                        active=1 if _payload_or_existing("active", "active", True) else 0,
                        notes=_payload_or_existing("notes"),
                        notes_verified=notes_verified,
                        notes_verified_at=notes_verified_at,
                        description=_payload_or_existing("description"),
                        size_oz=float(_payload_or_existing("size_oz", "size_oz", 0.0) or 0.0) if _payload_or_existing("size_oz", "size_oz") is not None else None,
                        size_ml=float(_payload_or_existing("size_ml", "size_ml", 0.0) or 0.0) if _payload_or_existing("size_ml", "size_ml") is not None else None,
                        volume_oz=float(_payload_or_existing("volume_oz", "volume_oz", 0.0) or 0.0) if _payload_or_existing("volume_oz", "volume_oz") is not None else None,
                        volume_ml=float(_payload_or_existing("volume_ml", "volume_ml", 0.0) or 0.0) if _payload_or_existing("volume_ml", "volume_ml") is not None else None,
                        script=_payload_or_existing("script"),
                        note_top=_payload_or_existing("note_top"),
                        note_mid=_payload_or_existing("note_mid"),
                        note_base=_payload_or_existing("note_base"),
                        media_url=_payload_or_existing("media_url"),
                        dupe_inspiration=_payload_or_existing("dupe_inspiration"),
                        dupe_confidence=_payload_or_existing("dupe_confidence"),
                        dupe_classification=_payload_or_existing("dupe_classification"),
                        dupe_notes=_payload_or_existing("dupe_notes"),
                    )
                    for field_name in TIKTOK_PRODUCT_FIELDS:
                        if field_name == "tiktok_quantity":
                            continue
                        update_fields[field_name] = _payload_or_existing(field_name)
                    if payload.get("image_128"):
                        update_fields["image_path"] = payload["image_128"]
                    elif remote_image_128:
                        update_fields["image_path"] = remote_image_128
                    row = set_product_details(
                        int(product_id),
                        audit_source="inventory_api",
                        audit_actor=str(audit_actor) if audit_actor is not None else None,
                        audit_context={
                            "path": path,
                            "product_id": int(product_id),
                            "client_ip": self._client_ip(),
                        },
                        **update_fields,
                    )
                    if payload.get("sds_pdf_base64"):
                        sds_path = _save_product_sds_pdf(int(product_id), payload.get("sds_pdf_base64"), payload.get("sds_pdf_filename"))
                        row = set_product_details(
                            int(product_id),
                            audit_source="inventory_api",
                            audit_actor=str(audit_actor) if audit_actor is not None else None,
                            audit_context={
                                "path": path,
                                "product_id": int(product_id),
                                "client_ip": self._client_ip(),
                            },
                            tiktok_sds_file_path=sds_path,
                        )
                else:
                    row = upsert_product(
                        name=name,
                        sku=payload.get("default_code"),
                        barcode=payload.get("barcode"),
                        category_id=category_id,
                        brand=payload.get("brand"),
                        gender=payload.get("gender"),
                        supplier_name=payload.get("supplier_name"),
                        storage_bin=payload.get("storage_bin"),
                        product_type=payload.get("type") or "product",
                        cost_price=float(payload.get("standard_price") or 0.0),
                        raw_cost=float(payload.get("raw_cost") or 0.0),
                        cost_plus_12=float(payload.get("cost_plus_12") or 0.0),
                        cost_plus_20=float(payload.get("cost_plus_20") or 0.0),
                        retail_price=float(payload.get("list_price") or 0.0),
                        notes=payload.get("notes"),
                        notes_verified=1 if payload.get("notes_verified") else 0,
                        notes_verified_at=datetime.now(timezone.utc).isoformat() if payload.get("notes_verified") else None,
                        description=payload.get("description"),
                        size_oz=float(payload.get("size_oz")) if payload.get("size_oz") not in (None, "") else None,
                        size_ml=float(payload.get("size_ml")) if payload.get("size_ml") not in (None, "") else None,
                        volume_oz=float(payload.get("volume_oz")) if payload.get("volume_oz") not in (None, "") else None,
                        volume_ml=float(payload.get("volume_ml")) if payload.get("volume_ml") not in (None, "") else None,
                        script=payload.get("script"),
                        note_top=payload.get("note_top"),
                        note_mid=payload.get("note_mid"),
                        note_base=payload.get("note_base"),
                        media_url=payload.get("media_url"),
                        dupe_inspiration=payload.get("dupe_inspiration"),
                        dupe_confidence=payload.get("dupe_confidence"),
                        dupe_classification=payload.get("dupe_classification"),
                        dupe_notes=payload.get("dupe_notes"),
                    )
                    if payload.get("image_128"):
                        row = set_product_details(int(row["id"]), image_path=payload.get("image_128"))
                    elif remote_image_128:
                        row = set_product_details(int(row["id"]), image_path=remote_image_128)
                    tiktok_fields = {
                        field_name: payload.get(field_name)
                        for field_name in TIKTOK_PRODUCT_FIELDS
                        if field_name in payload and field_name != "tiktok_quantity"
                    }
                    if tiktok_fields:
                        row = set_product_details(int(row["id"]), **tiktok_fields)
                    if payload.get("sds_pdf_base64"):
                        sds_path = _save_product_sds_pdf(int(row["id"]), payload.get("sds_pdf_base64"), payload.get("sds_pdf_filename"))
                        row = set_product_details(int(row["id"]), tiktok_sds_file_path=sds_path)

                stock_adjusted = False
                if row and "qty_available" in payload:
                    current_qty = float(row.get("on_hand_qty") or 0.0)
                    desired_qty = float(payload.get("qty_available") or 0.0)
                    delta = desired_qty - current_qty
                    if abs(delta) > 0.0001:
                        expected_current = payload.get("expected_current_qty")
                        if expected_current not in (None, ""):
                            expected_qty = float(expected_current or 0.0)
                            if abs(expected_qty - current_qty) > 0.0001:
                                self._json(
                                    {
                                        "ok": False,
                                        "error": "stock_changed_since_loaded",
                                        "current_qty": current_qty,
                                        "expected_current_qty": expected_qty,
                                    },
                                    status=409,
                                )
                                return
                        if product_id and not payload.get("stock_adjustment_intent") and not str(payload.get("adjustment_reason") or "").strip():
                            self._json({"ok": False, "error": "stock_adjustment_intent_required"}, status=400)
                            return
                        if desired_qty < -0.0001:
                            self._json({"ok": False, "error": "stock_cannot_go_negative"}, status=400)
                            return
                        adjustment_reason = str(payload.get("adjustment_reason") or "").strip() or "manual_adjustment"
                        record_inventory_movement(
                            int(row["id"]),
                            "adjustment",
                            delta,
                            reason=adjustment_reason,
                            reference_type="inventory",
                            reference_id=int(row["id"]),
                        )
                        stock_adjusted = True
                        row = get_product(int(row["id"]))

                row = row or {}
                row["default_code"] = row.get("sku")
                row["standard_price"] = row.get("cost_price")
                row["raw_cost"] = row.get("raw_cost")
                row["cost_plus_12"] = row.get("cost_plus_12")
                row["cost_plus_20"] = row.get("cost_plus_20")
                row["list_price"] = row.get("retail_price")
                row["qty_available"] = row.get("on_hand_qty")
                row["type"] = row.get("product_type")
                row["categ_name"] = row.get("category_name")
                row["image_url"] = _product_image_url(row)
                self._json({"ok": True, "stock_adjusted": stock_adjusted, "product": row})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/in_house_sales":
            payload = self._read_json()
            try:
                sale = create_in_house_sale(
                    employee_name=payload.get("employee_name"),
                    employee_id=payload.get("employee_id"),
                    product_id=payload.get("product_id"),
                    barcode=payload.get("barcode"),
                    sku=payload.get("sku"),
                    qty=payload.get("qty") or 1,
                    unit_price=payload.get("unit_price"),
                    notes=payload.get("notes"),
                    sold_at=payload.get("sold_at") or datetime.now(timezone.utc).isoformat(),
                )
                self._json({"ok": True, "sale": sale, **in_house_sales_summary()})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/in_house_sales/checkout":
            payload = self._read_json()
            try:
                receipt = complete_in_house_checkout(
                    employee_name=payload.get("employee_name"),
                    employee_id=payload.get("employee_id"),
                    lines=payload.get("lines") or [],
                    payment_method=payload.get("payment_method") or "cash",
                    notes=payload.get("notes"),
                    discount_amount=payload.get("discount_amount") or 0,
                    tax_amount=payload.get("tax_amount") or 0,
                    buyer_type=payload.get("buyer_type"),
                    buyer_phone=payload.get("buyer_phone"),
                    buyer_email=payload.get("buyer_email"),
                    approved_by=payload.get("approved_by") or "pos_auto",
                )
                self._json({
                    "ok": True,
                    "receipt": receipt,
                    "summary": in_house_orders_summary(),
                    "sales": in_house_sales_summary(),
                })
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/employees/pos_token/create":
            payload = self._read_json()
            try:
                token_row = create_employee_pos_token(
                    employee_id=payload.get("employee_id"),
                    employee_name=payload.get("employee_name"),
                    device_label=payload.get("device_label"),
                    expires_at=payload.get("expires_at"),
                )
                self._json({"ok": True, "token": token_row})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/employees/settings":
            payload = self._read_json()
            try:
                employee = update_employee_account_settings(
                    payload.get("employee_id"),
                    active=payload.get("active"),
                    auto_approve_in_house_orders=payload.get("auto_approve_in_house_orders"),
                    allow_self_service_returns=payload.get("allow_self_service_returns"),
                )
                self._json({"ok": True, "employee": employee})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/internal_pos/orders":
            payload = self._read_json()
            try:
                order = create_in_house_order(
                    token=payload.get("token"),
                    employee_id=payload.get("employee_id"),
                    employee_name=payload.get("employee_name"),
                    lines=payload.get("lines") or [],
                    payment_method=payload.get("payment_method") or ("payroll" if payload.get("token") else "cash"),
                    notes=payload.get("notes"),
                    discount_amount=payload.get("discount_amount") or 0,
                    tax_amount=payload.get("tax_amount") or 0,
                    buyer_type=payload.get("buyer_type"),
                    buyer_phone=payload.get("buyer_phone"),
                    buyer_email=payload.get("buyer_email"),
                )
                self._json({"ok": True, "order": order, "summary": in_house_orders_summary()})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/internal_pos/orders/update":
            payload = self._read_json()
            try:
                order = get_in_house_order(int(payload.get("id") or 0))
                if not order or not _guest_in_house_order_access_allowed(
                    order,
                    buyer_name=payload.get("buyer_name"),
                    buyer_phone=payload.get("buyer_phone"),
                    buyer_email=payload.get("buyer_email"),
                ):
                    self._json({"ok": False, "error": "order not found"}, status=404)
                    return
                if str(order.get("status") or "") not in {"pending_approval", "draft"}:
                    self._json({"ok": False, "error": "only pending drafts can be edited here"}, status=400)
                    return
                updated = update_in_house_order(
                    payload.get("id"),
                    employee_name=payload.get("buyer_name"),
                    payment_method=payload.get("payment_method"),
                    notes=payload.get("notes"),
                    discount_amount=payload.get("discount_amount"),
                    tax_amount=payload.get("tax_amount"),
                    buyer_type=payload.get("buyer_type"),
                    buyer_phone=payload.get("buyer_phone"),
                    buyer_email=payload.get("buyer_email"),
                    lines=payload.get("lines") or [],
                )
                self._json({"ok": True, "order": updated})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/internal_pos/orders/split":
            payload = self._read_json()
            try:
                order = get_in_house_order(int(payload.get("id") or 0))
                if not order or not _guest_in_house_order_access_allowed(
                    order,
                    buyer_name=payload.get("buyer_name"),
                    buyer_phone=payload.get("buyer_phone"),
                    buyer_email=payload.get("buyer_email"),
                ):
                    self._json({"ok": False, "error": "order not found"}, status=404)
                    return
                if str(order.get("status") or "") not in {"pending_approval", "draft"}:
                    self._json({"ok": False, "error": "only pending drafts can be split here"}, status=400)
                    return
                result = split_in_house_order(
                    payload.get("id"),
                    line_ids=payload.get("line_ids") or [],
                    line_items=payload.get("line_items") or [],
                )
                self._json({"ok": True, **result})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/internal_pos/orders/merge":
            payload = self._read_json()
            try:
                source = get_in_house_order(int(payload.get("source_id") or 0))
                target = get_in_house_order(int(payload.get("target_id") or 0))
                if (
                    not source
                    or not target
                    or not _guest_in_house_order_access_allowed(source, buyer_name=payload.get("buyer_name"), buyer_phone=payload.get("buyer_phone"), buyer_email=payload.get("buyer_email"))
                    or not _guest_in_house_order_access_allowed(target, buyer_name=payload.get("buyer_name"), buyer_phone=payload.get("buyer_phone"), buyer_email=payload.get("buyer_email"))
                ):
                    self._json({"ok": False, "error": "invoice not found"}, status=404)
                    return
                if str(source.get("status") or "") not in {"pending_approval", "draft"} or str(target.get("status") or "") not in {"pending_approval", "draft"}:
                    self._json({"ok": False, "error": "only pending drafts can be merged here"}, status=400)
                    return
                result = merge_in_house_orders(payload.get("source_id"), payload.get("target_id"))
                self._json({"ok": True, **result})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/in_house_orders/update":
            payload = self._read_json()
            try:
                order = update_in_house_order(
                    payload.get("id"),
                    employee_name=payload.get("employee_name"),
                    payment_method=payload.get("payment_method"),
                    notes=payload.get("notes"),
                    discount_amount=payload.get("discount_amount"),
                    tax_amount=payload.get("tax_amount"),
                    buyer_type=payload.get("buyer_type"),
                    buyer_phone=payload.get("buyer_phone"),
                    buyer_email=payload.get("buyer_email"),
                    lines=payload.get("lines") or [],
                )
                self._json({"ok": True, "order": order, "summary": in_house_orders_summary(), "sales": in_house_sales_summary()})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/in_house_orders/split":
            payload = self._read_json()
            try:
                result = split_in_house_order(
                    payload.get("id"),
                    line_ids=payload.get("line_ids") or [],
                    approved_by=payload.get("approved_by"),
                    line_items=payload.get("line_items") or [],
                )
                self._json({"ok": True, **result, "summary": in_house_orders_summary(), "sales": in_house_sales_summary()})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/in_house_orders/merge":
            payload = self._read_json()
            try:
                result = merge_in_house_orders(
                    payload.get("source_id"),
                    payload.get("target_id"),
                )
                self._json({"ok": True, **result, "summary": in_house_orders_summary(), "sales": in_house_sales_summary()})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/in_house_orders/approve":
            payload = self._read_json()
            try:
                order = approve_in_house_order(payload.get("id"), approved_by=payload.get("approved_by"))
                self._json({"ok": True, "order": order, "summary": in_house_orders_summary(), "sales": in_house_sales_summary()})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/in_house_orders/reject":
            payload = self._read_json()
            try:
                order = reject_in_house_order(
                    payload.get("id"),
                    rejected_by=payload.get("rejected_by"),
                    rejection_reason=payload.get("rejection_reason"),
                )
                self._json({"ok": True, "order": order, "summary": in_house_orders_summary()})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/in_house_orders/cancel":
            payload = self._read_json()
            try:
                order = cancel_in_house_order(payload.get("id"))
                self._json({"ok": True, "order": order, "summary": in_house_orders_summary()})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/orders/ensure_sale_order":
            payload = self._read_json()
            group_id = payload.get("group_id")
            if not group_id:
                self._json({"ok": False, "error": "group_id required"}, status=400)
                return
            try:
                group = next((g for g in list_buyer_groups() if int(g["id"]) == int(group_id)), None)
                if not group:
                    self._json({"ok": False, "error": "group_not_found"}, status=404)
                    return
                if group.get("sale_order_id"):
                    so_id = int(group["sale_order_id"])
                    so = next((o for o in list_sale_orders() if int(o["id"]) == so_id), None)
                    self._json({"ok": True, "sale_order_id": so_id, "sale_order_name": so.get("order_number") if so else str(so_id)})
                    return
                order = create_sale_order(
                    session_id=group.get("session_id"),
                    customer_id=group.get("customer_id"),
                    buyer_group_id=group.get("id"),
                    whatnot_buyer_username=group.get("buyer_username"),
                    state="draft",
                    ordered_at=datetime.now(timezone.utc).isoformat(),
                )
                self._json({"ok": True, "sale_order_id": order.get("id"), "sale_order_name": order.get("order_number")})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if path == "/api/analytics/scrape_shop":
            self._json({"ok": False, "error": "competitor_monitoring_retired"}, status=410)
            return

        self.send_response(404)
        self.end_headers()

    # -------------------------------------------------------------------
    # Complex handler methods
    # -------------------------------------------------------------------

    def _handle_session_stats(self, qs):
        local_company_session = _resolve_company_session(qs.get("session_id", [None])[0])
        if local_company_session:
            current_status = collector_status()
            current_stream_url = current_status.get("stream_url")
            current_stream_id = get_stream_id(current_stream_url) if current_stream_url else None
            if current_stream_id is not None:
                try:
                    # Session stats is one of the most frequently polled endpoints during live
                    # use, so keep winner/lot side-effects in sync here too instead of relying
                    # only on /events consumers to trigger ingestion.
                    recent_events = get_recent_events(100, stream_id=current_stream_id)
                    if recent_events:
                        _process_event_side_effects(recent_events, stream_id=current_stream_id)
                    update_company_session(int(local_company_session["id"]), stream_id=int(current_stream_id))
                    local_company_session = get_company_session(int(local_company_session["id"])) or local_company_session
                except Exception:
                    pass

            # TikTok operator mode: ingest TikTok winners into company session only when enabled.
            try:
                _ingest_tiktok_operator_winners(local_company_session)
            except Exception:
                pass

            session = {
                "id": local_company_session["id"],
                "name": local_company_session.get("name"),
                "total_products_sold": local_company_session.get("total_products_sold") or 0,
                "total_revenue": local_company_session.get("total_revenue") or 0.0,
                "total_profit": local_company_session.get("total_profit") or 0.0,
            }
            total_products = session.get("total_products_sold") or 0
            total_revenue = session.get("total_revenue") or 0.0
            avg_price = (total_revenue / total_products) if total_products else 0.0
            latest_db_winner = latest_db_event("auction_winner", stream_id=current_stream_id) if current_stream_id else {}
            latest_db_lot = latest_db_event("lot_update", stream_id=current_stream_id) if current_stream_id else {}
            latest_auction_state = latest_db_event("auction_state", stream_id=current_stream_id) if current_stream_id else {}
            current_lot = get_current_company_lot(local_company_session["id"]) or {}
            latest_auction = {}
            if local_company_session.get("total_lots_sold"):
                from .company_db import list_auction_results
                rows = list_auction_results(local_company_session["id"], limit=1)
                if rows:
                    latest_auction = rows[0]
            active_item = shared_scan_for_session(local_company_session["id"]) or {}
            self._json({
                "session": session,
                "current_lot": current_lot,
                "latest_auction": latest_auction,
                "latest_db_winner": latest_db_winner,
                "latest_db_lot": latest_db_lot,
                "latest_auction_state": latest_auction_state,
                "shared_scan": active_item,
                "active_item": active_item,
                "avg_price": avg_price,
                "current_stream_id": current_stream_id,
                "current_stream_url": current_stream_url,
            })
            return
        self._json({
            "session": {},
            "current_lot": {},
            "latest_auction": {},
            "latest_db_winner": {},
            "latest_db_lot": {},
            "latest_auction_state": {},
            "shared_scan": {},
            "active_item": {},
            "avg_price": 0.0,
            "current_stream_id": None,
            "current_stream_url": None,
        })

    def _handle_obs_current(self):
        """Return the current scanned product for the OBS overlay.
        Priority: live session scan → demo scan → nothing.
        """
        obs_scope = self._obs_scope_key()
        session = _current_company_session()
        active_lot = get_current_company_lot(session["id"]) if session else None
        live_tray = _get_live_obs_tray(session["id"], active_lot["id"]) if session and active_lot else []
        if _live_obs_product:
            self._json({
                "active": True,
                "demo": False,
                "product": _normalize_obs_product(_live_obs_product),
                "tray": live_tray,
            })
            return

        scan = None
        if session:
            scan = shared_scan_for_session(session["id"]) or None

        # Fall back to demo mode if no live scan
        if not scan:
            demo = _get_demo_scan(scope=obs_scope)
            if demo:
                self._json({"active": True, "demo": True, "product": demo, "tray": _get_demo_scan_tray(scope=obs_scope)})
            else:
                self._json({"active": False, "product": None})
            return

        # Enrich live scan with full product record
        product = None
        product_id = scan.get("product_id")
        if not product_id:
            barcode = scan.get("barcode") or scan.get("sku")
            if barcode:
                product = find_product_by_code(barcode)
        else:
            product = get_product(int(product_id))
        partner_price = self._partner_price_payload(product) if product else None
        self._json({
            "active": True,
            "demo": False,
            "product": {
                "name": _clean_product_name(scan.get("product_name") or (product.get("name") if product else "")),
                "on_hand_qty": scan.get("on_hand_qty") if scan.get("on_hand_qty") is not None else (product.get("on_hand_qty") if product else 0),
                "cost_price": scan.get("cost_price") or (product.get("cost_price") if product else 0),
                **_product_pricing_ladder(product or scan),
                "retail_price": partner_price.get("partner_price") if partner_price and partner_price.get("partner_price") is not None else (scan.get("retail_price") or (product.get("retail_price") if product else 0)),
                "base_retail_price": scan.get("retail_price") or (product.get("retail_price") if product else 0),
                "note_top": product.get("note_top") if product else None,
                "note_mid": product.get("note_mid") if product else None,
                "note_base": product.get("note_base") if product else None,
                "notes": product.get("notes") if product else None,
                "script": product.get("script") if product else None,
                "description": product.get("description") if product else None,
                "media_url": product.get("media_url") if product else None,
                "image_url": scan.get("image_url"),
                "dupe_research": _dupe_research_for_product(product),
                **(partner_price or {}),
            },
            "tray": live_tray,
        })

    def _handle_obs_demo_scan(self):
        """Scan a product into demo state — works without a live session."""
        obs_scope = self._obs_scope_key()
        payload = self._read_json()
        barcode = (payload.get("barcode") or "").strip()
        if not barcode:
            self._json({"ok": False, "error": "missing_barcode"}, status=400)
            return
        product = find_product_by_code(barcode)
        if not product:
            self._json({"ok": False, "error": "product_not_found"}, status=404)
            return
        partner_price = self._partner_price_payload(product)
        demo_product = {
            "name": _clean_product_name(product.get("name")),
            "product_name": _clean_product_name(product.get("name")),
            "product_id": product.get("id"),
            "barcode": product.get("barcode"),
            "sku": product.get("sku"),
            "on_hand_qty": product.get("on_hand_qty"),
            "cost_price": product.get("cost_price"),
            **_product_pricing_ladder(product),
            "retail_price": partner_price.get("partner_price") if partner_price and partner_price.get("partner_price") is not None else product.get("retail_price"),
            "base_retail_price": product.get("retail_price"),
            "note_top": product.get("note_top"),
            "note_mid": product.get("note_mid"),
            "note_base": product.get("note_base"),
            "gender": product.get("gender"),
            "notes": product.get("notes"),
            "media_url": product.get("media_url"),
            "image_url": _product_image_url(product),
            "dupe_research": _dupe_research_for_product(product),
            **(partner_price or {}),
        }
        preview_item, tray = _append_demo_scan(demo_product, max_items=TV_PREVIEW_MAX_ITEMS, scope=obs_scope)
        self._json({"ok": True, "product": preview_item, "rows": tray})

    def _handle_lot_products(self, qs):
        session = _resolve_company_session(qs.get("session_id", [None])[0])
        if session:
            lot = get_current_company_lot(session["id"])
            if not lot:
                self._json({"ok": True, "rows": [], "selected_item_id": None})
                return
            rows = []
            selected_item_id = None
            for row in list_lot_items(lot["id"]):
                if row.get("status") == "dropped":
                    continue
                row["cost"] = row.get("unit_cost")
                row["scanned_qty"] = int(row.get("qty_snapshot") or 1)
                row["selected"] = row.get("status") == "active"
                if row["selected"]:
                    selected_item_id = row.get("id")
                if row.get("product_id"):
                    prod = get_product(int(row["product_id"]))
                    row["image_url"] = _product_image_url(prod) if prod else None
                    if prod:
                        row["on_hand_qty"] = prod.get("on_hand_qty")
                        row["retail_price"] = prod.get("retail_price")
                        row["cost_price"] = prod.get("cost_price")
                        reserved_elsewhere = reserved_qty_for_product(session["id"], row["product_id"], exclude_lot_id=lot["id"])
                        available_qty = max(float(prod.get("on_hand_qty") or 0) - float(reserved_elsewhere or 0), 0)
                        row["qty_reserved"] = float(reserved_elsewhere or 0) + float(row["scanned_qty"] or 0)
                        row["qty_remaining"] = max(available_qty - max(int(row["scanned_qty"] or 0) - 1, 0), 0)
                        row.update(_product_pricing_ladder(prod))
                        row["note_top"] = prod.get("note_top")
                        row["note_mid"] = prod.get("note_mid")
                        row["note_base"] = prod.get("note_base")
                        row["dupe_research"] = _dupe_research_for_product(prod)
                rows.append(row)
            self._json({"ok": True, "lot": lot, "rows": rows, "selected_item_id": selected_item_id})
            return
        self._json({"ok": True, "lot": {}, "rows": [], "selected_item_id": None})

    def _handle_scan(self):
        payload = self._read_json()
        barcode = (payload.get("barcode") or "").strip()
        if not barcode:
            self._json({"ok": False, "error": "missing_barcode"}, status=400)
            return
        company_session = _current_company_session()
        if company_session:
            session_id = int(company_session["id"])
            command = barcode.upper()
            if command in {"RELEASE_BUCKET", "UNDO_RELEASE"}:
                if command == "RELEASE_BUCKET":
                    lot = get_current_company_lot(session_id)
                    if not lot:
                        self._json({"ok": False, "error": "no_current_lot"}, status=400)
                        return
                    _clear_live_obs_scan(company_session["id"])
                    clear_shared_scan_for_session(company_session["id"])
                    _clear_demo_scan_state()
                    update_company_lot(lot["id"], status="released", closed_at=datetime.now(timezone.utc).isoformat())
                    update_company_session(company_session["id"], current_lot_number=None)
                    _clear_live_obs_tray(company_session["id"])
                    _finalize_released_lot_async(lot["id"])
                    self._json({"ok": True, "command": "release_bucket", "lot_id": lot["id"]})
                    return

                reusable_lot = latest_reusable_lot(session_id)
                if not reusable_lot:
                    self._json({"ok": False, "error": "no_reusable_lot"}, status=400)
                    return
                mark_lot_items_status(reusable_lot["id"], from_statuses=("dropped",), to_status="open")
                update_company_lot(reusable_lot["id"], status="open", closed_at=None)
                update_company_session(company_session["id"], current_lot_number=reusable_lot.get("lot_number"))
                clear_shared_scan_for_session(company_session["id"])
                _clear_live_obs_scan(company_session["id"])
                _clear_demo_scan_state()
                reusable = get_current_company_lot(company_session["id"])
                if reusable:
                    _rebuild_live_obs_tray(company_session["id"], reusable["id"])
                self._json({"ok": True, "command": "undo_release", "lot": get_current_company_lot(company_session["id"])})
                return
            product = find_product_by_code(barcode)
            if not product:
                self._json({"ok": False, "error": "product_not_found"}, status=404)
                return
            on_hand = float(product.get("on_hand_qty") or 0)
            lot = ensure_company_bucket(session_id)
            if not lot:
                self._json({"ok": False, "error": "unable_to_open_lot"}, status=500)
                return
            lot_rows = [row for row in list_lot_items(lot["id"]) if row.get("status") in ("open", "active", "queued")]
            same_product_rows = [row for row in lot_rows if int(row.get("product_id") or 0) == int(product["id"])]
            current_lot_qty = sum(int(row.get("qty_snapshot") or 0) or 1 for row in same_product_rows)
            reserved_elsewhere = reserved_qty_for_product(session_id, product["id"], exclude_lot_id=lot["id"])
            available_qty = max(on_hand - reserved_elsewhere, 0)
            next_scan_qty = current_lot_qty + 1
            if next_scan_qty > available_qty:
                self._json({
                    "ok": False,
                    "error": "not_enough_stock",
                    "product_name": product.get("name", barcode),
                    "qty_available": on_hand,
                    "qty_reserved": reserved_elsewhere + current_lot_qty,
                    "scanned_qty": current_lot_qty,
                }, status=409)
                return
            for row in lot_rows:
                if row.get("status") == "active":
                    update_lot_item(row["id"], status="queued")
            item = None
            if same_product_rows:
                target = same_product_rows[-1]
                item = update_lot_item(
                    target["id"],
                    qty_snapshot=next_scan_qty,
                    status="active",
                    product_name=product.get("name"),
                    barcode=product.get("barcode"),
                    sku=product.get("sku"),
                )
                for duplicate in same_product_rows[:-1]:
                    if int(duplicate.get("id") or 0) == int(target.get("id") or 0):
                        continue
                    update_lot_item(duplicate["id"], status="dropped")
            else:
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
            active_item = _build_live_item_payload(
                lot,
                product,
                item=item,
                qty_remaining=max(available_qty - max(next_scan_qty - 1, 0), 0),
                scanned_qty=next_scan_qty,
                qty_reserved=reserved_elsewhere + next_scan_qty,
            )
            _clear_demo_scan_state()
            set_shared_scan_for_session(session_id, active_item)
            _set_live_obs_scan(session_id, active_item)
            _rebuild_live_obs_tray(session_id, lot["id"])
            self._json({"ok": True, "result": {"session_id": session_id, "active_item_id": item.get("id")}, "active_item": active_item})
            return
        # No active session — fall back to demo/preview mode
        product = find_product_by_code(barcode)
        if not product:
            self._json({"ok": False, "error": "product_not_found"}, status=404)
            return
        preview_item = {
            "name": _clean_product_name(product.get("name", "")),
            "product_name": _clean_product_name(product.get("name", "")),
            "product_id": product.get("id"),
            "barcode": product.get("barcode"),
            "sku": product.get("sku"),
            "cost_price": product.get("cost_price"),
            **_product_pricing_ladder(product),
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
        self._json({"ok": True, "preview": True, "active_item": preview_item, "rows": tray})
        return

    def _handle_ingest_winner(self):
        payload = self._read_json()
        winner_username = (payload.get("winner_username") or "").strip()
        lot_number = (payload.get("lot_number") or "").strip()
        event_id = payload.get("event_id")
        sale_price = payload.get("sale_price")
        if not winner_username or not lot_number or event_id is None:
            self._json({"ok": False, "error": "missing_params"}, status=400)
            return
        try:
            sale_price = float(sale_price)
        except (TypeError, ValueError):
            self._json({"ok": False, "error": "invalid_price"}, status=400)
            return
        local_company_session = _current_company_session()
        if local_company_session:
            ok = _maybe_ingest_winner_event(
                event_id,
                payload.get("sold_at") or datetime.now(timezone.utc).isoformat(),
                {
                    "winner_username": winner_username,
                    "lot_number": lot_number,
                    "sale_price": sale_price,
                },
            )
            self._json({"ok": bool(ok), "result": {"session_id": local_company_session["id"]} if ok else None})
            return
        self._json({"ok": False, "error": "no_company_session"}, status=400)

    def _handle_stream_start(self):
        payload = self._read_json()
        stream_url = (payload.get("stream_url") or "").strip()
        mode = "our_stream"
        if not stream_url:
            self._json({"ok": False, "error": "missing_stream_url"}, status=400)
            return
        try:
            status = start_live_collector(stream_url, mode=mode)
            self._json({"ok": True, **status})
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, status=500)

    def _handle_spectator_start(self):
        """Start one or more spectator-mode collectors (up to MAX_SPECTATOR_STREAMS).

        Body: {"stream_urls": ["url1", "url2", ...]}
              OR {"stream_url": "url"}   (single)
              Optional:
                replace_all: true  -> replace active spectator set with provided URLs
        """
        if not SPECTATOR_STARTS_ENABLED:
            self._json({"ok": False, "error": "spectator_starts_disabled"}, status=403)
            return
        payload = self._read_json()
        urls = payload.get("stream_urls") or []
        if not urls and payload.get("stream_url"):
            urls = [payload["stream_url"]]
        urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()]
        if not urls:
            self._json({"ok": False, "error": "stream_urls required"}, status=400)
            return
        replace_all = bool(payload.get("replace_all"))
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

        # Use multi-tab spectator: one browser, all URLs as tabs
        try:
            pid, log_path = start_spectator_batch(urls)
            results = [{"stream_url": u, "pid": pid, "running": True, "status": "started"} for u in urls]
            errors = []
            if capped:
                errors.append({"warning": f"limited_to_{MAX_SPECTATOR_STREAMS}_streams"})
        except Exception as exc:
            results = []
            errors = [{"error": str(exc)}]
        self._json({
            "ok": len(results) > 0,
            "started": results,
            "errors": errors,
            "streams": spectator_status(),
        })

    def _handle_spectator_stop(self):
        """Stop a specific spectator stream or all.

        Body: {"stream_url": "url"}  → stop specific
              {}                     → stop all spectators
        """
        payload = self._read_json()
        stream_url = (payload.get("stream_url") or "").strip() or None
        stopped = stop_spectator(stream_url)
        self._json({
            "ok": True,
            "stopped": stopped,
            "streams": spectator_status(),
        })

    def _handle_priority_spectator_start(self):
        if not SPECTATOR_STARTS_ENABLED:
            self._json({"ok": False, "error": "spectator_starts_disabled"}, status=403)
            return
        payload = self._read_json()
        urls = payload.get("stream_urls") or []
        if not urls and payload.get("stream_url"):
            urls = [payload["stream_url"]]
        urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()]
        if not urls:
            self._json({"ok": False, "error": "stream_urls required"}, status=400)
            return
        try:
            pid, _log_path = start_priority_spectator_batch(urls)
            results = [{"stream_url": u, "pid": pid, "running": True, "status": "started", "mode": "headed_priority"} for u in urls[:3]]
            errors = []
        except Exception as exc:
            results = []
            errors = [{"error": str(exc)}]
        self._json({
            "ok": len(results) > 0,
            "started": results,
            "errors": errors,
            "streams": priority_spectator_status(),
        })

    def _handle_priority_spectator_stop(self):
        payload = self._read_json()
        stream_url = (payload.get("stream_url") or "").strip() or None
        stopped = stop_priority_spectator(stream_url)
        self._json({
            "ok": True,
            "stopped": stopped,
            "streams": priority_spectator_status(),
        })

    def _handle_live_discovery(self, qs):
        """Fetch currently-live Whatnot streams for given tag pages.

        Query params:
          tags  — comma-separated tag slugs (default: fragrances,health_and_beauty)
        """
        import re
        import json as _json

        TAG_META = {
            "fragrances": {"label": "Fragrances & Perfume", "slug": "fragrances"},
            "health_and_beauty": {"label": "Health & Beauty", "slug": "health_and_beauty"},
        }

        tags_param = (qs.get("tags", ["fragrances,health_and_beauty"])[0] or "fragrances,health_and_beauty")
        requested_tags = [t.strip() for t in tags_param.split(",") if t.strip()]

        # Load cookies
        cookies = {}
        if os.path.isfile(COLLECTOR_COOKIES_PATH):
            try:
                with open(COLLECTOR_COOKIES_PATH, "r") as f:
                    raw = _json.load(f)
                if isinstance(raw, list):
                    cookies = {c["name"]: c["value"] for c in raw if "whatnot.com" in c.get("domain", "")}
            except Exception:
                pass

        try:
            from curl_cffi import requests as cffi_requests
        except ImportError:
            self._json({"ok": False, "error": "curl_cffi not installed. Run: pip3 install curl-cffi"}, status=500)
            return

        sess = cffi_requests.Session(impersonate="chrome124")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        results = {}
        errors = []

        for tag in requested_tags:
            meta = TAG_META.get(tag, {"label": tag, "slug": tag})
            url = f"https://www.whatnot.com/tag/{meta['slug']}"
            try:
                r = sess.get(url, headers=headers, cookies=cookies, timeout=20)
                if r.status_code != 200:
                    errors.append(f"{tag}: HTTP {r.status_code}")
                    results[tag] = []
                    continue

                html = r.text
                scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)

                # Find the large Apollo SSR data script
                large = max(
                    (s for s in scripts if "ApolloSSRDataTransport" in s and len(s) > 50_000),
                    key=len, default=None
                )
                if not large:
                    errors.append(f"{tag}: no Apollo data found")
                    results[tag] = []
                    continue

                fixed = large.replace(":undefined", ":null").replace(",undefined", ",null")
                m = re.match(
                    r'\(window\[Symbol\.for\("ApolloSSRDataTransport"\)\] \?\?= \[\]\)\.push\((.*)\)$',
                    fixed.strip(), re.DOTALL
                )
                if not m:
                    errors.append(f"{tag}: regex mismatch")
                    results[tag] = []
                    continue

                data = _json.loads(m.group(1))
                if not isinstance(data, dict):
                    errors.append(f"{tag}: unexpected data type {type(data).__name__}")
                    results[tag] = []
                    continue
                streams = []
                seen = set()

                rehydrate = data.get("rehydrate")
                if not isinstance(rehydrate, dict):
                    rehydrate = {}
                for val in rehydrate.values():
                    if not val or not isinstance(val, dict):
                        continue
                    data_inner = val.get("data")
                    if not isinstance(data_inner, dict):
                        continue
                    feed = data_inner.get("feed")
                    if not isinstance(feed, dict):
                        continue
                    objects = feed.get("objects")
                    if not isinstance(objects, dict):
                        continue
                    edges = objects.get("edges") or []
                    for edge in edges:
                        if not isinstance(edge, dict):
                            continue
                        node = edge.get("node")
                        if not isinstance(node, dict):
                            continue
                        obj = node.get("object")
                        if not isinstance(obj, dict) or not obj:
                            continue
                        seller = obj.get("user") or obj.get("seller")
                        if not isinstance(seller, dict):
                            continue
                        username = seller.get("username", "")
                        if not username or username in seen:
                            continue
                        seen.add(username)
                        stream_id = obj.get("id", "")
                        stream_url = f"https://www.whatnot.com/live/{stream_id}" if stream_id else f"https://www.whatnot.com/live/{username}"
                        streams.append({
                            "username": username,
                            "display_name": seller.get("displayName", username),
                            "title": obj.get("title", ""),
                            "url": stream_url,
                            "tag": tag,
                            "tag_label": meta["label"],
                            "viewers": obj.get("activeViewers"),
                        })

                results[tag] = streams

            except Exception as exc:
                errors.append(f"{tag}: {exc}")
                results[tag] = []

        # Flatten + deduplicate across tags (a stream can appear in both)
        all_streams = []
        seen_global = set()
        for tag in requested_tags:
            for s in results.get(tag, []):
                if s["username"] not in seen_global:
                    seen_global.add(s["username"])
                    all_streams.append(s)
                else:
                    # Add secondary tag label
                    for existing in all_streams:
                        if existing["username"] == s["username"] and s["tag_label"] not in existing["tag_label"]:
                            existing["tag_label"] += f" / {s['tag_label']}"
                            break

        self._json({
            "ok": True,
            "streams": all_streams,
            "by_tag": {tag: results.get(tag, []) for tag in requested_tags},
            "errors": errors,
            "total": len(all_streams),
        })

    def _handle_upload_cookies(self):
        """Accept a raw JSON cookies file upload and save to COLLECTOR_COOKIES_PATH."""
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            self._json({"ok": False, "error": "empty_body"}, status=400)
            return
        if length > 10 * 1024 * 1024:  # 10 MB guard
            self._json({"ok": False, "error": "file_too_large"}, status=400)
            return
        raw = self.rfile.read(length)
        # Validate it's valid JSON
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except Exception:
            self._json({"ok": False, "error": "invalid_json"}, status=400)
            return
        # Must be a list (Netscape/Playwright cookie array) or dict
        if not isinstance(parsed, (list, dict)):
            self._json({"ok": False, "error": "unexpected_format"}, status=400)
            return
        os.makedirs(os.path.dirname(os.path.abspath(COLLECTOR_COOKIES_PATH)), exist_ok=True)
        try:
            with open(COLLECTOR_COOKIES_PATH, "wb") as f:
                f.write(raw)
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, status=500)
            return
        count = len(parsed) if isinstance(parsed, list) else 1
        self._json({"ok": True, "saved_to": COLLECTOR_COOKIES_PATH, "cookie_count": count})

    def _handle_tiktok_live_label_enrich_pdf(self):
        """
        Accept a TikTok Shipping label + Packing slip PDF and overlay resolved
        product names into the blank packing-slip area.
        """
        qs = parse_qs(urlparse(self.path).query)
        session_id_param = qs.get("session_id", [None])[0]
        session_key = (qs.get("session_key", [""])[0] or "").strip()
        requested_name = (qs.get("filename", ["tiktok-live-labels.pdf"])[0] or "tiktok-live-labels.pdf").strip()
        lot_map_csv_text = ""
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            self._json({"ok": False, "error": "empty_body"}, status=400)
            return
        if length > 60 * 1024 * 1024:
            self._json({"ok": False, "error": "file_too_large"}, status=400)
            return
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" in content_type.lower():
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": content_type,
                    "CONTENT_LENGTH": str(length),
                },
            )
            pdf_field = form["pdf"] if "pdf" in form else None
            if pdf_field is None or not getattr(pdf_field, "file", None):
                self._json({"ok": False, "error": "missing_pdf"}, status=400)
                return
            raw = pdf_field.file.read()
            lot_map_csv_text = (form.getvalue("lot_map_csv_text") or "")
            requested_name = (form.getvalue("filename") or requested_name or getattr(pdf_field, "filename", "") or "tiktok-live-labels.pdf").strip()
            session_id_param = form.getvalue("session_id") or session_id_param
            session_key = (form.getvalue("session_key") or session_key or "").strip()
        else:
            raw = self.rfile.read(length)
        if not raw[:5].startswith(b"%PDF"):
            self._json({"ok": False, "error": "not_a_pdf"}, status=400)
            return

        try:
            output, annotated_pages, total_pages = _annotate_tiktok_label_pdf(raw, session_id=session_id_param, lot_map_csv_text=lot_map_csv_text)
        except Exception as exc:
            self._json({"ok": False, "error": f"pdf_label_enrich_error: {exc}"}, status=400)
            return
        if annotated_pages <= 0:
            try:
                from PyPDF2 import PdfReader
                sample_text = "\n".join(
                    (page.extract_text() or "")[:1000]
                    for page in PdfReader(io.BytesIO(raw)).pages[:3]
                ).lower()
            except Exception:
                sample_text = ""
            if "grab list" in sample_text or "pick list" in sample_text:
                self._json({
                    "ok": False,
                    "error": "This is a grab/pick list PDF. Upload the raw TikTok Shipping label + Packing slip PDF instead.",
                }, status=400)
                return
            self._json({
                "ok": False,
                "error": "No TikTok packing slips were found in this PDF, or no seller SKU/lot matches were found for this session.",
            }, status=400)
            return

        safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "", requested_name).strip() or "tiktok-live-labels.pdf"
        if not safe_name.lower().endswith(".pdf"):
            safe_name += ".pdf"
        if "with-product" not in safe_name.lower():
            safe_name = safe_name[:-4] + "-with-products.pdf"
        artifact = None
        if session_key:
            try:
                artifact = _save_tiktok_label_artifact(
                    session_key,
                    safe_name,
                    output,
                    annotated_pages,
                    total_pages,
                    original_pdf_bytes=raw,
                    original_filename=requested_name,
                )
            except Exception:
                artifact = None

        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
        self.send_header("X-YNF-Annotated-Pages", str(annotated_pages))
        self.send_header("X-YNF-Total-Pages", str(total_pages))
        if artifact:
            self.send_header("X-YNF-Label-Artifact-Id", str(artifact.get("id") or ""))
            self.send_header("X-YNF-Label-Artifact-Filename", str(artifact.get("filename") or safe_name))
        self.send_header("Content-Length", str(len(output)))
        _send_security_headers(self)
        self.end_headers()
        self.wfile.write(output)

    def _handle_whatnot_picklist_enrich_pdf(self):
        qs = parse_qs(urlparse(self.path).query)
        session_id_param = qs.get("session_id", [None])[0]
        requested_name = (qs.get("filename", ["whatnot-packing-slip.pdf"])[0] or "whatnot-packing-slip.pdf").strip()
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            self._json({"ok": False, "error": "empty_body"}, status=400)
            return
        if length > 60 * 1024 * 1024:
            self._json({"ok": False, "error": "file_too_large"}, status=400)
            return
        raw = self.rfile.read(length)
        if not raw[:5].startswith(b"%PDF"):
            self._json({"ok": False, "error": "not_a_pdf"}, status=400)
            return
        try:
            output, annotated_pages, total_pages = _annotate_whatnot_packing_slip_pdf(raw, session_id=session_id_param)
        except Exception as exc:
            self._json({"ok": False, "error": f"pdf_label_enrich_error: {exc}"}, status=400)
            return
        if annotated_pages <= 0:
            self._json({
                "ok": False,
                "error": "No Whatnot packing slip pages were found in this PDF, or no matched product names were available for overlay.",
            }, status=400)
            return
        safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "", requested_name).strip() or "whatnot-packing-slip.pdf"
        if not safe_name.lower().endswith(".pdf"):
            safe_name += ".pdf"
        if "with-product" not in safe_name.lower():
            safe_name = safe_name[:-4] + "-with-products.pdf"
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
        self.send_header("X-YNF-Annotated-Pages", str(annotated_pages))
        self.send_header("X-YNF-Total-Pages", str(total_pages))
        self.send_header("Content-Length", str(len(output)))
        _send_security_headers(self)
        self.end_headers()
        self.wfile.write(output)

    def _handle_picklist_upload(self):
        """
        Accept a Whatnot packing-slip PDF, parse it, match lots to auction results,
        and return an enriched pick list.

        Expects raw PDF bytes as the POST body (Content-Type: application/pdf).
        Optional query param: session_id — restrict auction result matching to that session.
        """
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            self._json({"ok": False, "error": "empty_body"}, status=400)
            return
        if length > 30 * 1024 * 1024:  # 30 MB guard
            self._json({"ok": False, "error": "file_too_large"}, status=400)
            return

        raw = self.rfile.read(length)

        # Validate it starts with PDF magic bytes
        if not raw[:5].startswith(b"%PDF"):
            self._json({"ok": False, "error": "not_a_pdf"}, status=400)
            return

        qs = parse_qs(urlparse(self.path).query)
        session_id_param = qs.get("session_id", [None])[0]

        try:
            shipments = parse_packing_slip_pdf(raw)
        except Exception as exc:
            self._json({"ok": False, "error": f"pdf_parse_error: {exc}"}, status=400)
            return

        if not shipments:
            self._json({"ok": False, "error": "no_packing_slips_found"}, status=400)
            return

        # Get auction results to match lot numbers
        sid = int(session_id_param) if session_id_param else None
        auction_rows = list_auction_results(session_id=sid, limit=9999)

        shipments = match_lots_to_products(shipments, auction_rows)

        # ── Resolve session ──
        effective_sid = sid
        if not effective_sid:
            sessions = list_company_sessions()
            ended = [s for s in sessions if s.get("status") == "ended"]
            if ended:
                effective_sid = ended[0]["id"]

        # ── Sync customers, orders, inventory, and save pick list ──
        customers_synced = 0
        orders_synced = 0
        inventory_deducted = 0
        payment_approvals = {"approved_lots": 0, "approved_orders": 0, "assignment_ids": []}

        if effective_sid:
            label_lots = [
                item.get("lot_number")
                for ship in shipments
                for item in (ship.get("items") or [])
                if item.get("lot_number")
            ]
            payment_approvals = approve_payments_from_picklist_lots(effective_sid, label_lots)

        for si, ship in enumerate(shipments):
            username = ship.get("username", "").strip()
            if not username:
                continue

            # 1. Upsert customer with name + address from packing slip
            cust = upsert_customer(
                whatnot_username=username,
                display_name=ship.get("buyer_name") or None,
                address=ship.get("address") or None,
            )
            ship["customer_id"] = cust["id"]
            customers_synced += 1

            # 2. Find or create sale order
            if effective_sid:
                # Use find_existing first to prevent duplicates
                so = find_existing_sale_order(effective_sid, username)
                if not so:
                    so = create_sale_order(
                        session_id=effective_sid,
                        customer_id=cust["id"],
                        whatnot_buyer_username=username,
                        state="sale",
                    )
                ship["sale_order_id"] = so["id"]
                ship["order_number"] = so.get("order_number")

                # Update order: tracking, status, payment — mark as confirmed
                tracking = ship.get("tracking_number")
                update_fields = {
                    "state": "sale",
                    "fulfillment_status": "shipped",
                    "payment_status": "paid",
                    "customer_id": cust["id"],
                    "shipped_at": datetime.now(timezone.utc).isoformat(),
                }
                if tracking:
                    update_fields["tracking_number"] = tracking
                    update_fields["tracking_status"] = "shipped"
                    update_fields["tracking_last_checked_at"] = datetime.now(timezone.utc).isoformat()
                if ship.get("shipping_method"):
                    update_fields["tracking_carrier"] = (ship.get("shipping_method") or "").strip().lower()
                update_sale_order(so["id"], **update_fields)
                orders_synced += 1

                # 3. Add order lines (skip duplicates)
                existing_lines = list_sale_order_lines(so["id"])
                existing_lot_keys = set()
                for ln in existing_lines:
                    desc = (ln.get("description") or "").strip()
                    existing_lot_keys.add(desc)

                for item in ship["items"]:
                    if not item.get("matched"):
                        continue
                    desc = item.get("product_name") or f"Lot #{item['lot_number']}"
                    if desc.strip() in existing_lot_keys:
                        continue
                    existing_lot_keys.add(desc.strip())

                    product_id = None
                    if item.get("barcode"):
                        prod = find_product_by_code(item["barcode"])
                        if prod:
                            product_id = prod["id"]
                    elif item.get("sku"):
                        prod = find_product_by_code(item["sku"])
                        if prod:
                            product_id = prod["id"]

                    add_sale_order_line_for_item(
                        so["id"],
                        product_id=product_id,
                        description=desc,
                        qty=1,
                        unit_price=item.get("price", 0),
                        lot_id=item.get("lot_id"),
                        auction_result_id=item.get("auction_result_id"),
                    )

                    # 4. Deduct inventory for matched items with a product_id
                    if product_id:
                        try:
                            record_inventory_movement(
                                product_id, "out", -1,
                                reason=f"Packing slip: Lot #{item['lot_number']} → @{username}",
                                reference_type="sale_order",
                                reference_id=so["id"],
                            )
                            inventory_deducted += 1
                        except Exception:
                            pass  # skip if already deducted

        # ── Cancel session orders whose lots never appeared in the uploaded PDF ──
        orders_cancelled = _cancel_missing_picklist_orders(effective_sid, shipments)

        # ── Compute summary stats ──
        total_lots = sum(len(s["items"]) for s in shipments)
        matched = sum(1 for s in shipments for i in s["items"] if i.get("matched"))
        unmatched = total_lots - matched

        # ── Save pick list record ──
        pick_list = create_pick_list(
            session_id=effective_sid,
            filename=qs.get("filename", [None])[0],
            total_shipments=len(shipments),
            total_lots=total_lots,
            matched_lots=matched,
            unmatched_lots=unmatched,
            total_revenue=sum(s["total_price"] for s in shipments),
            customers_synced=customers_synced,
            orders_synced=orders_synced,
            inventory_deducted=inventory_deducted,
        )

        # Save individual items
        for si, ship in enumerate(shipments):
            for item in ship["items"]:
                add_pick_list_item(
                    pick_list_id=pick_list["id"],
                    shipment_index=si,
                    username=ship.get("username"),
                    buyer_name=ship.get("buyer_name"),
                    address=ship.get("address"),
                    tracking_number=ship.get("tracking_number"),
                    shipping_method=ship.get("shipping_method"),
                    ship_date=ship.get("ship_date"),
                    weight=ship.get("weight"),
                    lot_number=item.get("lot_number"),
                    product_name=item.get("product_name"),
                    barcode=item.get("barcode"),
                    sku=item.get("sku"),
                    sale_price=item.get("price", 0),
                    order_id=item.get("order_id"),
                    matched=1 if item.get("matched") else 0,
                    sale_order_id=ship.get("sale_order_id"),
                    customer_id=ship.get("customer_id"),
                )

        self._json({
            "ok": True,
            "pick_list_id": pick_list["id"],
            "shipments": shipments,
            "summary": {
                "total_shipments": len(shipments),
                "total_lots": total_lots,
                "matched": matched,
                "unmatched": unmatched,
                "total_revenue": sum(s["total_price"] for s in shipments),
                "customers_synced": customers_synced,
                "orders_synced": orders_synced,
                "inventory_deducted": inventory_deducted,
                "orders_cancelled": orders_cancelled,
                "payments_approved": payment_approvals.get("approved_lots", 0),
                "payment_approval_orders": payment_approvals.get("approved_orders", 0),
                "session_id": effective_sid,
                "pick_list_id": pick_list["id"],
            },
        })
