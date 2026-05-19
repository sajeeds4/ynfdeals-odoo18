from __future__ import annotations

from datetime import datetime, timezone

from app.core.redis import get_runtime_state, set_runtime_state

_REQUEST_STATE_KEY = "http:request_stats"
_BRIDGE_STATE_KEY = "http:bridge_stats"
_MAX_REQUEST_ENTRIES = 200
_MAX_BRIDGE_ENTRIES = 100


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim_stats(entries: dict[str, dict], limit: int) -> dict[str, dict]:
    ranked = sorted(
        entries.items(),
        key=lambda item: (
            int(item[1].get("count") or 0),
            str(item[1].get("last_seen_at") or ""),
        ),
        reverse=True,
    )
    return dict(ranked[:limit])


def record_request_metric(path: str, method: str, status_code: int, duration_ms: float) -> None:
    stats = get_runtime_state(_REQUEST_STATE_KEY, default={}) or {}
    key = f"{method.upper()} {path}"
    current = dict(stats.get(key) or {})
    count = int(current.get("count") or 0) + 1
    total_ms = float(current.get("total_duration_ms") or 0.0) + float(duration_ms)
    stats[key] = {
        "path": path,
        "method": method.upper(),
        "count": count,
        "status_code": int(status_code),
        "last_duration_ms": round(float(duration_ms), 2),
        "avg_duration_ms": round(total_ms / count, 2),
        "total_duration_ms": round(total_ms, 2),
        "last_seen_at": _utc_now(),
    }
    set_runtime_state(_REQUEST_STATE_KEY, _trim_stats(stats, _MAX_REQUEST_ENTRIES), ttl_seconds=7 * 24 * 3600)


def record_bridge_hit(path: str, method: str, status_code: int) -> None:
    stats = get_runtime_state(_BRIDGE_STATE_KEY, default={}) or {}
    key = f"{method.upper()} {path}"
    current = dict(stats.get(key) or {})
    stats[key] = {
        "path": path,
        "method": method.upper(),
        "count": int(current.get("count") or 0) + 1,
        "status_code": int(status_code),
        "last_seen_at": _utc_now(),
    }
    set_runtime_state(_BRIDGE_STATE_KEY, _trim_stats(stats, _MAX_BRIDGE_ENTRIES), ttl_seconds=7 * 24 * 3600)


def get_request_metrics():
    return get_runtime_state(_REQUEST_STATE_KEY, default={}) or {}


def get_bridge_metrics():
    return get_runtime_state(_BRIDGE_STATE_KEY, default={}) or {}


def summarize_request_metrics(limit: int = 5) -> dict:
    metrics = list(get_request_metrics().values())
    by_count = sorted(
        metrics,
        key=lambda item: (
            int(item.get("count") or 0),
            float(item.get("avg_duration_ms") or 0.0),
        ),
        reverse=True,
    )
    by_latency = sorted(
        metrics,
        key=lambda item: (
            float(item.get("avg_duration_ms") or 0.0),
            int(item.get("count") or 0),
        ),
        reverse=True,
    )
    total_requests = sum(int(item.get("count") or 0) for item in metrics)
    error_requests = sum(
        int(item.get("count") or 0) for item in metrics if int(item.get("status_code") or 0) >= 400
    )
    return {
        "tracked_routes": len(metrics),
        "total_requests": total_requests,
        "error_requests": error_requests,
        "error_rate_pct": round((error_requests / total_requests) * 100.0, 2) if total_requests else 0.0,
        "top_routes_by_count": by_count[:limit],
        "slowest_routes_by_avg_ms": by_latency[:limit],
    }


def summarize_bridge_metrics(limit: int = 5) -> dict:
    metrics = list(get_bridge_metrics().values())
    by_count = sorted(
        metrics,
        key=lambda item: (
            int(item.get("count") or 0),
            str(item.get("last_seen_at") or ""),
        ),
        reverse=True,
    )
    total_hits = sum(int(item.get("count") or 0) for item in metrics)
    return {
        "tracked_routes": len(metrics),
        "total_bridge_hits": total_hits,
        "top_bridge_routes": by_count[:limit],
    }
