from __future__ import annotations

from server.events_db import get_analytics_products_intel
from server.reconciler import list_intelligence_signals, materialize_stream_intelligence


def _with_status(payload: dict, status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def get_legacy_products_intel(streamer_name: str | None = None):
    try:
        data = get_analytics_products_intel(streamer_name=streamer_name if streamer_name else None)
        return {"ok": True, **data}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_intelligence_live(
    stream_id: str | int | None = None,
    signal_type: str | None = None,
    limit: int = 40,
    refresh: str | None = "auto",
):
    if stream_id in (None, ""):
        return _with_status({"ok": False, "error": "stream_id required"}, 400)
    try:
        stream_id_value = int(stream_id)
    except Exception:
        return _with_status({"ok": False, "error": "invalid stream_id"}, 400)
    try:
        refresh_mode = (refresh or "auto").strip().lower()
        if refresh_mode not in {"0", "false", "off", "none"}:
            materialize_stream_intelligence(stream_id_value)
        rows = list_intelligence_signals(
            stream_id_value,
            signal_type=(signal_type or "").strip().lower() or None,
            limit=limit,
        )
        grouped = {}
        for row in rows:
            grouped.setdefault(row["signal_type"], []).append(row)
        return {"ok": True, "rows": rows, "grouped": grouped}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)
