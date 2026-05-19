"""
Collector process manager.

Maintains the live collector for our own stream only.
Legacy spectator/competitor monitoring entrypoints are kept as disabled stubs
so old callers fail closed instead of spawning removed Playwright workers.
"""

import os
import re
import signal
import subprocess
from datetime import datetime, timezone

from .config import (
    COLLECTOR_ROOT, COLLECTOR_PYTHON, COLLECTOR_SRC_PATH,
    COLLECTOR_HEADLESS, COLLECTOR_POLL_INTERVAL_MS,
    COLLECTOR_COOKIES_PATH, LIVE_COLLECTOR_LOG_PATH,
    LIVE_COLLECTOR_STANDBY_LOG_PATH, LIVE_COLLECTOR_LEASE_PATH,
    LIVE_COLLECTOR_LEASE_TTL_SEC, LIVE_COLLECTOR_HA_ENABLED,
    MAX_SPECTATOR_STREAMS, SPECTATOR_TABS_PER_WORKER, VIEWER_COUNT_SELECTOR,
    PRIORITY_SPECTATOR_MAX_STREAMS,
)
from .state import (
    load_collector_state, save_collector_state,
    load_spectator_state, save_spectator_state,
    load_priority_spectator_state, save_priority_spectator_state,
)
from .company_db import create_company_session, list_company_sessions, end_company_session


def _is_pid_running(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def _launch_live_collector(stream_url, mode="our_stream", session_id=None, role="active"):
    env = os.environ.copy()
    env["WHATNOT_STREAM_URL"] = stream_url
    env["WHATNOT_SESSION_ID"] = str(session_id) if session_id else ""
    env.pop("DB_PATH", None)
    env["PYTHONPATH"] = COLLECTOR_SRC_PATH
    env["HEADLESS"] = COLLECTOR_HEADLESS
    env["POLL_INTERVAL_MS"] = COLLECTOR_POLL_INTERVAL_MS
    env["COOKIES_PATH"] = COLLECTOR_COOKIES_PATH
    env["VIEWER_COUNT_SELECTOR"] = VIEWER_COUNT_SELECTOR
    env["COLLECTOR_KIND"] = "live"
    env["COLLECTOR_ROLE"] = role
    env["COLLECTOR_LEASE_PATH"] = LIVE_COLLECTOR_LEASE_PATH
    env["COLLECTOR_LEASE_TTL_SEC"] = str(LIVE_COLLECTOR_LEASE_TTL_SEC)
    log_path = LIVE_COLLECTOR_LOG_PATH if role == "active" else LIVE_COLLECTOR_STANDBY_LOG_PATH
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "ab") as log_file:
        proc = subprocess.Popen(
            [COLLECTOR_PYTHON, "-m", "collector.main"],
            cwd=COLLECTOR_ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
        )
    return proc, log_path


def live_collector_status():
    """Return the current live collector process status."""
    state = load_collector_state()
    pid = state.get("pid")
    standby_pid = state.get("standby_pid")
    active_running = bool(pid and _is_pid_running(pid))
    standby_running = bool(standby_pid and _is_pid_running(standby_pid))
    running = active_running or standby_running
    expected_running = bool(state.get("running") and state.get("stream_url") and not state.get("stopped_at"))
    if expected_running and not running:
        state["running"] = False
        state["pid"] = None
        state["standby_pid"] = None
        save_collector_state(state)
        active_running = False
        standby_running = False
        running = False
    if expected_running:
        changed = False
        if not active_running:
            try:
                proc, log_path = _launch_live_collector(
                    state.get("stream_url"),
                    mode=state.get("stream_mode", "our_stream"),
                    session_id=state.get("session_id"),
                    role="active",
                )
                state["pid"] = proc.pid
                state["log_path"] = log_path
                state["running"] = True
                state["restarted_at"] = datetime.now(timezone.utc).isoformat()
                state["restart_count"] = int(state.get("restart_count") or 0) + 1
                active_running = True
                changed = True
            except Exception:
                state["pid"] = None
                active_running = False
        if state.get("ha_enabled", LIVE_COLLECTOR_HA_ENABLED) and not standby_running:
            try:
                proc, standby_log_path = _launch_live_collector(
                    state.get("stream_url"),
                    mode=state.get("stream_mode", "our_stream"),
                    session_id=state.get("session_id"),
                    role="standby",
                )
                state["standby_pid"] = proc.pid
                state["standby_log_path"] = standby_log_path
                standby_running = True
                changed = True
            except Exception:
                state["standby_pid"] = None
                standby_running = False
        running = active_running or standby_running
        state["running"] = running
        if changed:
            save_collector_state(state)
    elif state and state.get("running") != running:
        state["running"] = running
        if not active_running:
            state["pid"] = None
        if not standby_running:
            state["standby_pid"] = None
        save_collector_state(state)
    return {
        "running": running,
        "pid": state.get("pid"),
        "active_running": active_running,
        "standby_pid": state.get("standby_pid"),
        "standby_running": standby_running,
        "stream_url": state.get("stream_url"),
        "stream_mode": state.get("stream_mode", "our_stream"),
        "session_id": state.get("session_id"),
        "started_at": state.get("started_at"),
        "restarted_at": state.get("restarted_at"),
        "restart_count": int(state.get("restart_count") or 0),
        "stopped_at": state.get("stopped_at"),
        "log_path": LIVE_COLLECTOR_LOG_PATH,
        "standby_log_path": LIVE_COLLECTOR_STANDBY_LOG_PATH,
        "ha_enabled": bool(state.get("ha_enabled", LIVE_COLLECTOR_HA_ENABLED)),
        "status": "running" if running else "stopped",
        "collector_type": "live",
    }


def collector_status():
    """Backward-compatible alias for the live collector status."""
    return live_collector_status()


def _extract_show_id(stream_url):
    match = re.search(r"/live/([^/?#]+)", stream_url or "")
    return match.group(1) if match else None


def _ensure_stream_session(stream_url):
    """Always create a fresh local company session for a new our-stream start."""
    show_id = _extract_show_id(stream_url)
    if show_id:
        for session in list_company_sessions("ynfdeals", limit=200):
            if session.get("show_id") == show_id and session.get("status") in ("draft", "live"):
                try:
                    end_company_session(int(session["id"]))
                except Exception:
                    pass
    created = create_company_session(
        show_id=show_id,
        whatnot_account="ynfdeals",
        status="live",
    )
    return int(created["id"]) if created else None


def start_live_collector(stream_url, mode="our_stream"):
    """Start the live collector subprocess for our stream URL.

    mode: 'our_stream' — company collector flow (default)
    """
    if mode != "our_stream":
        raise RuntimeError("spectator_mode_removed")
    status = live_collector_status()
    if status["running"]:
        if status.get("stream_url") == stream_url:
            return status
        stop_live_collector()

    session_id = None
    if mode == "our_stream":
        session_id = _ensure_stream_session(stream_url)
        if not session_id:
            raise RuntimeError("unable_to_create_session")

    proc, log_path = _launch_live_collector(stream_url, mode=mode, session_id=session_id, role="active")
    standby_pid = None
    standby_log_path = LIVE_COLLECTOR_STANDBY_LOG_PATH if LIVE_COLLECTOR_HA_ENABLED else None
    if LIVE_COLLECTOR_HA_ENABLED:
        standby_proc, standby_log_path = _launch_live_collector(stream_url, mode=mode, session_id=session_id, role="standby")
        standby_pid = standby_proc.pid
    state = {
        "pid": proc.pid,
        "standby_pid": standby_pid,
        "stream_url": stream_url,
        "stream_mode": mode,
        "session_id": session_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "restarted_at": None,
        "restart_count": 0,
        "stopped_at": None,
        "running": True,
        "ha_enabled": LIVE_COLLECTOR_HA_ENABLED,
        "log_path": log_path,
        "standby_log_path": standby_log_path,
    }
    save_collector_state(state)
    return live_collector_status()


def start_collector(stream_url, mode="our_stream"):
    """Backward-compatible alias for the live collector start."""
    return start_live_collector(stream_url, mode=mode)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-tab spectator manager — ONE Chromium process, many tabs.
# Completely independent of the our_stream collector above.
# ─────────────────────────────────────────────────────────────────────────────

def _spectator_workers(state=None):
    state = state or load_spectator_state()
    workers = state.get("__workers__")
    if isinstance(workers, list) and workers:
        return [w for w in workers if isinstance(w, dict)]
    pid = state.get("__pid__")
    if pid:
        return [{
            "pid": pid,
            "log_path": state.get("__log_path__"),
            "started_at": state.get("__started_at__"),
            "urls": [u for u in state.keys() if not u.startswith("__")],
            "worker_index": 0,
        }]
    return []


def _spectator_worker_pids(state=None):
    pids = []
    for worker in _spectator_workers(state):
        pid = worker.get("pid")
        if pid and _is_pid_running(pid):
            pids.append(int(pid))
    return pids


def _spectator_pid():
    """Backward-compatible helper: return the first running spectator worker PID."""
    pids = _spectator_worker_pids()
    return pids[0] if pids else None


def spectator_status():
    """Return list of status dicts for all known spectator streams."""
    state = load_spectator_state()
    worker_pids = set(_spectator_worker_pids(state))
    workers = _spectator_workers(state)
    url_to_worker = {}
    for worker in workers:
        pid = worker.get("pid")
        for url in worker.get("urls") or []:
            url_to_worker[url] = {
                "pid": pid,
                "log_path": worker.get("log_path"),
            }
    changed = False
    result = []
    for url, info in list(state.items()):
        if url.startswith("__"):
            continue
        was_running = info.get("running", False)
        worker_meta = url_to_worker.get(url, {})
        worker_pid = worker_meta.get("pid")
        now_running = bool(worker_pid in worker_pids and was_running and not info.get("stopped_at"))
        if was_running != now_running:
            info["running"] = now_running
            if not now_running:
                info["pid"] = None
            state[url] = info
            changed = True
        result.append({
            "stream_url": url,
            "pid": worker_pid if now_running else None,
            "started_at": info.get("started_at"),
            "stopped_at": info.get("stopped_at"),
            "running": now_running,
            "status": "running" if now_running else "stopped",
            "log_path": worker_meta.get("log_path") or info.get("log_path"),
        })
    if changed:
        save_spectator_state(state)
    return result


def start_spectator(stream_url):
    raise RuntimeError("spectator_removed")


def start_spectator_batch(stream_urls):
    raise RuntimeError("spectator_removed")


def stop_spectator(stream_url=None):
    """Stop the multi-tab spectator process (stops ALL streams).

    If stream_url is given, only marks that URL as stopped but keeps the
    process running for the remaining streams.
    Returns list of stopped stream URLs.
    """
    state = load_spectator_state()

    if stream_url:
        # Mark single URL stopped but keep process alive
        info = state.get(stream_url)
        if info:
            info["running"] = False
            info["stopped_at"] = datetime.now(timezone.utc).isoformat()
            state[stream_url] = info
            save_spectator_state(state)
        return [stream_url] if info else []

    # Stop every worker process.
    # First ask them to shut down gracefully so Playwright can close cleanly.
    worker_pids = _spectator_worker_pids(state)
    for pid in worker_pids:
        try:
            os.killpg(os.getpgid(int(pid)), signal.SIGINT)
        except Exception:
            try:
                os.kill(int(pid), signal.SIGINT)
            except Exception:
                pass

    time_limit = datetime.now(timezone.utc).timestamp() + 4.0
    while datetime.now(timezone.utc).timestamp() < time_limit:
        remaining = [pid for pid in worker_pids if _is_pid_running(pid)]
        if not remaining:
            break
        import time as _time
        _time.sleep(0.2)

    for pid in worker_pids:
        if not _is_pid_running(pid):
            continue
        try:
            os.killpg(os.getpgid(int(pid)), signal.SIGTERM)
        except Exception:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass

    stopped = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for url, info in list(state.items()):
        if url.startswith("__"):
            continue
        if isinstance(info, dict):
            stopped.append(url)

    # A full stop should fully clear the saved spectator set so nothing
    # appears active or silently comes back after a server restart.
    cleared_state = {
        "__pid__": None,
        "__workers__": [],
        "__started_at__": now_iso,
        "__log_path__": None,
    }
    save_spectator_state(cleared_state)
    return stopped


def stop_live_collector(mark_session_ended=True):
    """Stop the running live collector subprocess."""
    state = load_collector_state()
    for pid_key in ("pid", "standby_pid"):
        pid = state.get(pid_key)
        if pid and _is_pid_running(pid):
            try:
                os.killpg(os.getpgid(int(pid)), signal.SIGTERM)
            except Exception:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except Exception:
                    pass
    if mark_session_ended and state.get("session_id"):
        try:
            end_company_session(int(state["session_id"]))
        except Exception:
            pass
    state["running"] = False
    state["pid"] = None
    state["standby_pid"] = None
    state["stopped_at"] = datetime.now(timezone.utc).isoformat()
    state["restarted_at"] = None
    save_collector_state(state)
    try:
        if os.path.exists(LIVE_COLLECTOR_LEASE_PATH):
            os.remove(LIVE_COLLECTOR_LEASE_PATH)
    except Exception:
        pass
    return live_collector_status()


def stop_collector(mark_session_ended=True):
    """Backward-compatible alias for the live collector stop."""
    return stop_live_collector(mark_session_ended=mark_session_ended)


def _priority_spectator_workers(state=None):
    state = state or load_priority_spectator_state()
    workers = state.get("__workers__")
    if isinstance(workers, list) and workers:
        return [w for w in workers if isinstance(w, dict)]
    pid = state.get("__pid__")
    if pid:
        return [{
            "pid": pid,
            "log_path": state.get("__log_path__"),
            "started_at": state.get("__started_at__"),
            "urls": [u for u in state.keys() if not u.startswith("__")],
            "worker_index": 0,
        }]
    return []


def _priority_spectator_worker_pids(state=None):
    pids = []
    for worker in _priority_spectator_workers(state):
        pid = worker.get("pid")
        if pid and _is_pid_running(pid):
            pids.append(int(pid))
    return pids


def priority_spectator_status():
    state = load_priority_spectator_state()
    worker_pids = set(_priority_spectator_worker_pids(state))
    workers = _priority_spectator_workers(state)
    url_to_worker = {}
    for worker in workers:
        pid = worker.get("pid")
        for url in worker.get("urls") or []:
            url_to_worker[url] = {
                "pid": pid,
                "log_path": worker.get("log_path"),
            }
    changed = False
    result = []
    for url, info in list(state.items()):
        if url.startswith("__"):
            continue
        was_running = info.get("running", False)
        worker_meta = url_to_worker.get(url, {})
        worker_pid = worker_meta.get("pid")
        now_running = bool(worker_pid in worker_pids and was_running and not info.get("stopped_at"))
        if was_running != now_running:
            info["running"] = now_running
            if not now_running:
                info["pid"] = None
            state[url] = info
            changed = True
        result.append({
            "stream_url": url,
            "pid": worker_pid if now_running else None,
            "started_at": info.get("started_at"),
            "stopped_at": info.get("stopped_at"),
            "running": now_running,
            "status": "running" if now_running else "stopped",
            "log_path": worker_meta.get("log_path") or info.get("log_path"),
            "mode": "headed_priority",
        })
    if changed:
        save_priority_spectator_state(state)
    return result


def start_priority_spectator_batch(stream_urls):
    raise RuntimeError("spectator_removed")


def stop_priority_spectator(stream_url=None):
    state = load_priority_spectator_state()
    if stream_url:
        info = state.get(stream_url)
        if info:
            info["running"] = False
            info["stopped_at"] = datetime.now(timezone.utc).isoformat()
            state[stream_url] = info
            save_priority_spectator_state(state)
        return [stream_url] if info else []

    for pid in _priority_spectator_worker_pids(state):
        try:
            os.killpg(os.getpgid(int(pid)), signal.SIGTERM)
        except Exception:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass

    stopped = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for url, info in list(state.items()):
        if url.startswith("__"):
            continue
        if isinstance(info, dict):
            stopped.append(url)

    cleared_state = {
        "__pid__": None,
        "__workers__": [],
        "__started_at__": now_iso,
        "__log_path__": None,
    }
    save_priority_spectator_state(cleared_state)
    return stopped


def collectors_status():
    """Combined status view for both live and spectator collectors."""
    live = live_collector_status()
    spectator_streams = spectator_status()
    return {
        "live": live,
        "spectator": {
            "running_count": sum(1 for s in spectator_streams if s.get("running")),
            "streams": spectator_streams,
            "worker_pids": _spectator_worker_pids(),
            "status": "running" if any(s.get("running") for s in spectator_streams) else "stopped",
            "collector_type": "spectator",
        },
    }
