from __future__ import annotations

from app.core.redis import get_cached_json, set_cached_json
from server.analytics import (
    get_company_livestream_intelligence,
)
from server.api import (
    _current_company_session,
)
from server.company_db import get_setting_map, list_auction_results, list_products
from server.events_db import (
    get_analytics_chat_signals,
    get_analytics_timing,
)


def _with_status(payload: dict, status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def _cached(name: str, ttl_seconds: int, builder):
    cached = get_cached_json(name)
    if cached is not None:
        return cached
    result = builder()
    try:
        set_cached_json(name, result, ttl_seconds=ttl_seconds)
    except Exception:
        pass
    return result


def get_legacy_analytics_overview(stream_id: int | None = None):
    return _with_status({"ok": False, "error": "competitor_monitoring_retired"}, 410)


def get_legacy_company_intelligence():
    try:
        return _cached("company_intelligence", 45, lambda: {"ok": True, **get_company_livestream_intelligence()})
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_market_pulse(running_only: bool = False):
    return _with_status({"ok": False, "error": "competitor_monitoring_retired"}, 410)


def get_legacy_alerts():
    try:
        settings = get_setting_map()
        margin_threshold = float(settings.get("alert_margin_threshold") or 0)
        buyer_lots_threshold = int(settings.get("alert_buyer_lots_threshold") or 0)
        alerts = []
        local_session = _current_company_session()
        if local_session and margin_threshold > 0:
            rev = local_session.get("total_revenue") or 0
            prof = local_session.get("total_profit") or 0
            margin = (prof / rev * 100) if rev else 0
            if margin < margin_threshold and rev > 0:
                alerts.append({
                    "type": "margin",
                    "severity": "warning",
                    "message": f"Session margin {margin:.1f}% is below threshold {margin_threshold:.0f}%",
                    "value": round(margin, 1),
                    "threshold": margin_threshold,
                })
        if local_session and buyer_lots_threshold > 0:
            results = list_auction_results(session_id=local_session["id"], limit=2000)
            buyer_map = {}
            for row in results:
                username = row.get("winner_username") or "?"
                buyer_map[username] = buyer_map.get(username, 0) + 1
            for username, count in buyer_map.items():
                if count >= buyer_lots_threshold:
                    alerts.append({
                        "type": "buyer_concentration",
                        "severity": "info",
                        "message": f"@{username} has won {count} lots this session",
                        "username": username,
                        "lots": count,
                        "threshold": buyer_lots_threshold,
                    })
        low_stock_prods = list_products(low_stock_only=True, include_sales_metrics=False)
        if low_stock_prods:
            names = [p.get("name", "") for p in low_stock_prods[:5]]
            alerts.append({
                "type": "low_stock",
                "severity": "warning",
                "message": f"{len(low_stock_prods)} product(s) at or below low-stock threshold: {', '.join(names[:3])}{'…' if len(names) > 3 else ''}",
                "count": len(low_stock_prods),
            })
        return {"ok": True, "alerts": alerts, "count": len(alerts)}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_alert_settings():
    try:
        settings = get_setting_map()
        return {
            "ok": True,
            "margin_threshold": float(settings.get("alert_margin_threshold") or 0),
            "buyer_lots_threshold": int(settings.get("alert_buyer_lots_threshold") or 0),
        }
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_spectator_listings(stream_id: int | None = None):
    return _with_status({"ok": False, "error": "competitor_monitoring_retired"}, 410)


def get_legacy_competitor_prices(q: str = "", limit: int = 200):
    return _with_status({"ok": False, "error": "competitor_monitoring_retired"}, 410)


def get_legacy_chat_signals(stream_id: int | None = None):
    try:
        stream_id_value = int(stream_id) if stream_id not in (None, "", 0, "0") else None
        return {"ok": True, **get_analytics_chat_signals(stream_id=stream_id_value)}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_timing(streamer_name: str | None = None):
    try:
        return {"ok": True, **get_analytics_timing(streamer_name=streamer_name if streamer_name else None)}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)
