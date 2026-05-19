from datetime import datetime, timezone

from app.core.redis import get_client, get_runtime_state, ping
from app.core.runtime_observability import (
    get_bridge_metrics,
    get_request_metrics,
    summarize_bridge_metrics,
    summarize_request_metrics,
)
from app.workers.celery_app import celery_app


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _celery_queue_health():
    queue_names = [
        celery_app.conf.task_default_queue,
        celery_app.conf.task_routes.get("app.tasks.analytics.*", {}).get("queue"),
        celery_app.conf.task_routes.get("app.tasks.business.*", {}).get("queue"),
        celery_app.conf.task_routes.get("app.tasks.ingest.*", {}).get("queue"),
    ]
    queue_names = [name for name in queue_names if name]
    health = {"queues": [], "workers": {}, "inspect_ok": False}
    try:
        inspect = celery_app.control.inspect(timeout=1.0)
        ping_result = inspect.ping() or {}
        active_queues = inspect.active_queues() or {}
        health["workers"] = {
            "ping": ping_result,
            "active_queues": active_queues,
        }
        health["inspect_ok"] = True
    except Exception as exc:
        health["workers"] = {"error": str(exc)}
    try:
        client = get_client()
        for queue_name in queue_names:
            depth = client.llen(queue_name)
            health["queues"].append({"name": queue_name, "depth": int(depth)})
    except Exception as exc:
        health["queue_error"] = str(exc)
    return health


def _task_metrics_summary() -> dict:
    metrics = get_runtime_state("tasks:metrics", default={}) or {}
    entries = list(metrics.values())
    by_count = sorted(
        entries,
        key=lambda item: (
            int(item.get("count") or 0),
            str(item.get("last_seen_at") or ""),
        ),
        reverse=True,
    )
    outcome_totals = {}
    for entry in entries:
        outcome = str(entry.get("outcome") or "unknown")
        outcome_totals[outcome] = outcome_totals.get(outcome, 0) + int(entry.get("count") or 0)
    return {
        "tracked_outcomes": len(entries),
        "outcome_totals": outcome_totals,
        "top_task_outcomes": by_count[:10],
    }


def _fastapi_runtime_payload() -> dict:
    try:
        diagnostics_state = get_runtime_state("diagnostics:last")
        session_stats_state = get_runtime_state("session_stats:last")
    except Exception:
        diagnostics_state = None
        session_stats_state = None

    return {
        "redis_connected": ping(),
        "celery_default_queue": celery_app.conf.task_default_queue,
        "celery_result_backend": celery_app.conf.result_backend,
        "celery_queue_health": _celery_queue_health(),
        "runtime_state": {
            "diagnostics": diagnostics_state,
            "session_stats": session_stats_state,
            "request_metrics": get_request_metrics(),
            "request_summary": summarize_request_metrics(),
            "bridge_metrics": get_bridge_metrics(),
            "bridge_summary": summarize_bridge_metrics(),
            "task_metrics": get_runtime_state("tasks:metrics", default={}) or {},
            "task_summary": _task_metrics_summary(),
        },
    }


def get_runtime_diagnostics():
    return {
        "ok": True,
        "generated_at": _utcnow(),
        "diagnostics_mode": "runtime",
        "fastapi_runtime": _fastapi_runtime_payload(),
    }


def get_deep_runtime_diagnostics(log_limit: int = 200):
    from server.api import _build_system_diagnostics

    payload = _build_system_diagnostics(log_limit=log_limit)
    payload["diagnostics_mode"] = "deep"
    payload["fastapi_runtime"] = _fastapi_runtime_payload()
    return payload
