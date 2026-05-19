from server.api import _current_company_session, _ingest_tiktok_operator_winners, _process_event_side_effects
from server.collector_manager import collector_status
from server.company_db import (
    get_company_session,
    get_current_company_lot,
    list_auction_results,
    list_company_sessions,
    update_company_session,
)
from server.events_db import get_recent_events, get_stream_id, latest_db_event
from server.state import shared_scan_for_session

TIKTOK_PLATFORM_FEE_RATE = 0.06


def _with_platform_fee(session):
    if not session:
        return session
    enriched = dict(session)
    revenue = float(enriched.get("total_revenue") or 0.0)
    enriched["platform_fee_rate"] = TIKTOK_PLATFORM_FEE_RATE
    enriched["platform_fee"] = round(revenue * TIKTOK_PLATFORM_FEE_RATE, 2)
    return enriched


def get_current_session():
    session = _current_company_session()
    return {"ok": True, "session": _with_platform_fee(session)}


def list_recent_sessions(limit: int = 15):
    return [_with_platform_fee(row) for row in list_company_sessions("ynfdeals", limit=limit)]


def get_session_by_id(session_id: int):
    return {"ok": True, "session": _with_platform_fee(get_company_session(int(session_id)))}


def get_current_session_stats():
    local_company_session = _current_company_session()
    if not local_company_session:
        return {
            "ok": True,
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
        }

    current_status = collector_status()
    current_stream_url = current_status.get("stream_url")
    current_stream_id = get_stream_id(current_stream_url) if current_stream_url else None
    if current_stream_id is not None:
        try:
            recent_events = get_recent_events(100, stream_id=current_stream_id)
            if recent_events:
                _process_event_side_effects(recent_events, stream_id=current_stream_id)
            update_company_session(int(local_company_session["id"]), stream_id=int(current_stream_id))
            local_company_session = get_company_session(int(local_company_session["id"])) or local_company_session
        except Exception:
            pass

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
    session = _with_platform_fee(session)
    total_products = session.get("total_products_sold") or 0
    total_revenue = session.get("total_revenue") or 0.0
    avg_price = (total_revenue / total_products) if total_products else 0.0
    latest_db_winner = latest_db_event("auction_winner", stream_id=current_stream_id) if current_stream_id else {}
    latest_db_lot = latest_db_event("lot_update", stream_id=current_stream_id) if current_stream_id else {}
    latest_auction_state = latest_db_event("auction_state", stream_id=current_stream_id) if current_stream_id else {}
    current_lot = get_current_company_lot(local_company_session["id"]) or {}
    latest_auction = {}
    if local_company_session.get("total_lots_sold"):
        rows = list_auction_results(local_company_session["id"], limit=1)
        if rows:
            latest_auction = rows[0]
    active_item = shared_scan_for_session(local_company_session["id"]) or {}
    return {
        "ok": True,
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
    }
