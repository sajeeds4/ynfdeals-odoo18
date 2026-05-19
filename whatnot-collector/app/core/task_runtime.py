from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.redis import get_runtime_state, held_lock, set_runtime_state


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_task_metric(name: str, outcome: str) -> None:
    try:
        key = "tasks:metrics"
        state = get_runtime_state(key, default={}) or {}
        metric_key = f"{name}:{outcome}"
        current = dict(state.get(metric_key) or {})
        state[metric_key] = {
            "task": name,
            "outcome": outcome,
            "count": int(current.get("count") or 0) + 1,
            "last_seen_at": _utc_now(),
        }
        set_runtime_state(key, state, ttl_seconds=7 * 24 * 3600)
    except Exception:
        pass


def _compact_result(value: Any, *, depth: int = 0) -> Any:
    if depth >= 2:
        if isinstance(value, dict):
            return {"type": "dict", "keys": len(value)}
        if isinstance(value, list):
            return {"type": "list", "count": len(value)}
        return value if isinstance(value, (str, int, float, bool)) or value is None else str(type(value).__name__)

    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, list):
                compact[key] = {"count": len(item)}
            elif isinstance(item, dict):
                if "rows" in item and isinstance(item.get("rows"), list):
                    nested = {k: v for k, v in item.items() if k != "rows"}
                    compact[key] = {
                        **_compact_result(nested, depth=depth + 1),
                        "rows": {"count": len(item.get("rows") or [])},
                    }
                else:
                    compact[key] = _compact_result(item, depth=depth + 1)
            else:
                compact[key] = item
        return compact

    if isinstance(value, list):
        return {"count": len(value)}

    return value if isinstance(value, (str, int, float, bool)) or value is None else str(type(value).__name__)


def run_tracked_task(name: str, fn, *args, lock_ttl_seconds: int = 300, state_ttl_seconds: int = 86400, **kwargs):
    owner = f"{name}:{_utc_now()}"
    state_key = f"tasks:{name}"
    try:
        with held_lock(state_key, owner=owner, ttl_seconds=lock_ttl_seconds) as acquired:
            if not acquired:
                payload = {"ok": False, "skipped": True, "reason": "lock_not_acquired", "task": name, "at": _utc_now()}
                _record_task_metric(name, "skipped")
                try:
                    set_runtime_state(state_key, payload, ttl_seconds=state_ttl_seconds)
                except Exception:
                    pass
                return payload
            try:
                set_runtime_state(state_key, {"ok": True, "status": "running", "task": name, "at": _utc_now()}, ttl_seconds=state_ttl_seconds)
            except Exception:
                pass
            try:
                result = fn(*args, **kwargs)
                _record_task_metric(name, "completed")
                try:
                    set_runtime_state(
                        state_key,
                        {
                            "ok": True,
                            "status": "completed",
                            "task": name,
                            "at": _utc_now(),
                            "result": _compact_result(result),
                        },
                        ttl_seconds=state_ttl_seconds,
                    )
                except Exception:
                    pass
                return result
            except Exception as exc:
                _record_task_metric(name, "failed")
                try:
                    set_runtime_state(
                        state_key,
                        {"ok": False, "status": "failed", "task": name, "at": _utc_now(), "error": str(exc)},
                        ttl_seconds=state_ttl_seconds,
                    )
                except Exception:
                    pass
                raise
    except Exception:
        _record_task_metric(name, "fallback")
        return fn(*args, **kwargs)
