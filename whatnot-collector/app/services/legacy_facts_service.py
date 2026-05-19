from __future__ import annotations

from server.reconciler import (
    list_fact_buyers,
    list_fact_lots,
    list_fact_products,
    materialize_recent_stream_buyer_facts,
    materialize_recent_stream_facts,
    materialize_recent_stream_product_facts,
    materialize_stream_buyer_facts,
    materialize_stream_facts,
    materialize_stream_product_facts,
    materialize_streamer_buyer_facts,
    materialize_streamer_facts,
    materialize_streamer_product_facts,
)


def _with_status(payload: dict, status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def get_legacy_fact_lots(
    stream_id: str | int | None = None,
    streamer_name: str | None = None,
    confidence: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
    limit: int = 200,
    refresh: str = "auto",
):
    try:
        stream_id_value = None
        if stream_id not in (None, ""):
            try:
                stream_id_value = int(stream_id)
            except Exception:
                return _with_status({"ok": False, "error": "invalid stream_id"}, 400)

        refresh_mode = (refresh or "auto").strip().lower()
        streamer_name_value = (streamer_name or "").strip() or None
        if refresh_mode not in {"0", "false", "off", "none"}:
            if stream_id_value:
                materialize_stream_facts(stream_id_value)
            elif streamer_name_value:
                materialize_streamer_facts(streamer_name_value, limit=5)
            elif refresh_mode in {"all", "full"}:
                materialize_recent_stream_facts(limit=25)
            elif refresh_mode in {"recent"}:
                materialize_recent_stream_facts(limit=5)

        rows = list_fact_lots(
            stream_id=stream_id_value,
            streamer_name=streamer_name_value,
            confidence=(confidence or "").strip() or None,
            from_ts=(from_ts or "").strip() or None,
            to_ts=(to_ts or "").strip() or None,
            limit=limit,
        )
        totals = {
            "rows": len(rows),
            "revenue": round(sum(float(row.get("sale_price") or 0) for row in rows), 2),
            "high_confidence": sum(1 for row in rows if (row.get("confidence_label") or "") == "high"),
            "medium_confidence": sum(1 for row in rows if (row.get("confidence_label") or "") == "medium"),
            "low_confidence": sum(1 for row in rows if (row.get("confidence_label") or "") == "low"),
        }
        return {"ok": True, "rows": rows, "totals": totals}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_fact_buyers(
    stream_id: str | int | None = None,
    streamer_name: str | None = None,
    tier: str | None = None,
    q: str | None = None,
    min_spend: float = 0,
    limit: int = 200,
    refresh: str = "auto",
):
    try:
        stream_id_value = None
        if stream_id not in (None, ""):
            try:
                stream_id_value = int(stream_id)
            except Exception:
                return _with_status({"ok": False, "error": "invalid stream_id"}, 400)

        refresh_mode = (refresh or "auto").strip().lower()
        streamer_name_value = (streamer_name or "").strip() or None
        if refresh_mode not in {"0", "false", "off", "none"}:
            if stream_id_value:
                materialize_stream_buyer_facts(stream_id_value)
            elif streamer_name_value:
                materialize_streamer_buyer_facts(streamer_name_value, limit=5)
            elif refresh_mode in {"all", "full"}:
                materialize_recent_stream_buyer_facts(limit=25)
            elif refresh_mode in {"recent"}:
                materialize_recent_stream_buyer_facts(limit=5)

        rows = list_fact_buyers(
            stream_id=stream_id_value,
            streamer_name=streamer_name_value,
            tier=(tier or "").strip() or None,
            q=(q or "").strip() or None,
            min_spend=float(min_spend or 0),
            limit=limit,
        )
        totals = {
            "rows": len(rows),
            "buyers": sum(1 for row in rows if float(row.get("total_spend") or 0) > 0),
            "whales": sum(1 for row in rows if (row.get("buyer_tier") or "") == "whale"),
            "total_spend": round(sum(float(row.get("total_spend") or 0) for row in rows), 2),
            "total_wins": sum(int(row.get("lots_won") or 0) for row in rows),
            "total_messages": sum(int(row.get("chat_messages") or 0) for row in rows),
            "cross_stream_buyers": sum(1 for row in rows if int(row.get("streams_seen") or 0) >= 2),
        }
        return {"ok": True, "rows": rows, "totals": totals}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_fact_products(
    stream_id: str | int | None = None,
    streamer_name: str | None = None,
    q: str | None = None,
    min_sold: int = 0,
    limit: int = 200,
    refresh: str = "auto",
):
    try:
        stream_id_value = None
        if stream_id not in (None, ""):
            try:
                stream_id_value = int(stream_id)
            except Exception:
                return _with_status({"ok": False, "error": "invalid stream_id"}, 400)

        refresh_mode = (refresh or "auto").strip().lower()
        streamer_name_value = (streamer_name or "").strip() or None
        if refresh_mode not in {"0", "false", "off", "none"}:
            if stream_id_value:
                materialize_stream_product_facts(stream_id_value)
            elif streamer_name_value:
                materialize_streamer_product_facts(streamer_name_value, limit=5)
            elif refresh_mode in {"all", "full"}:
                materialize_recent_stream_product_facts(limit=25)
            elif refresh_mode in {"recent"}:
                materialize_recent_stream_product_facts(limit=5)

        rows = list_fact_products(
            stream_id=stream_id_value,
            streamer_name=streamer_name_value,
            q=(q or "").strip() or None,
            min_sold=int(min_sold or 0),
            limit=limit,
        )
        totals = {
            "rows": len(rows),
            "times_sold": sum(int(row.get("times_sold") or 0) for row in rows),
            "revenue": round(sum(float(row.get("total_revenue") or 0) for row in rows), 2),
            "high_demand": sum(1 for row in rows if float(row.get("demand_score") or 0) >= 0.75),
        }
        return {"ok": True, "rows": rows, "totals": totals}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)
