from app.core.task_runtime import run_tracked_task
from app.workers.celery_app import celery_app
from app.core.redis import set_runtime_state
from app.services.diagnostics_service import get_deep_runtime_diagnostics
from app.services.session_service import get_current_session_stats
from server.state import load_collector_state


def _live_show_running() -> bool:
    try:
        state = load_collector_state() or {}
    except Exception:
        return False
    return bool(state.get("running") and state.get("stream_url") and not state.get("stopped_at"))


@celery_app.task(name="app.tasks.default.capture_runtime_diagnostics")
def capture_runtime_diagnostics():
    def _run():
        payload = get_deep_runtime_diagnostics()
        try:
            set_runtime_state("diagnostics:last", payload, ttl_seconds=3600)
        except Exception:
            pass
        return payload
    return run_tracked_task("capture_runtime_diagnostics", _run, lock_ttl_seconds=240)


@celery_app.task(name="app.tasks.default.capture_current_session_stats")
def capture_current_session_stats():
    if _live_show_running():
        return {"ok": True, "skipped": True, "reason": "live_show_running"}

    def _run():
        payload = get_current_session_stats()
        try:
            set_runtime_state("session_stats:last", payload, ttl_seconds=1800)
        except Exception:
            pass
        return payload
    return run_tracked_task("capture_current_session_stats", _run, lock_ttl_seconds=60)
