"""
Shared state management — scan state and collector state persistence.
"""

import json
import os
import threading

from .config import (
    SHARED_SCAN_STATE_PATH, COLLECTOR_STATE_PATH,
    SPECTATOR_STATE_PATH, PRIORITY_SPECTATOR_STATE_PATH,
)

# In-process lock: prevents concurrent request threads from clobbering
# each other's reads/writes to shared_scan_state.json.
_scan_state_lock = threading.Lock()


# --- Shared Scan State ---

def load_shared_scan_state():
    if not os.path.exists(SHARED_SCAN_STATE_PATH):
        return {}
    try:
        with open(SHARED_SCAN_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_shared_scan_state(state):
    try:
        # Write to a temp file then atomically rename to prevent partial reads.
        tmp = SHARED_SCAN_STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, SHARED_SCAN_STATE_PATH)
    except Exception:
        pass


def shared_scan_for_session(session_id):
    if not session_id:
        return {}
    state = load_shared_scan_state()
    scan = state.get(str(session_id)) or {}
    return scan if isinstance(scan, dict) else {}


def set_shared_scan_for_session(session_id, scan):
    if not session_id or not scan:
        return
    with _scan_state_lock:
        state = load_shared_scan_state()
        state[str(session_id)] = scan
        save_shared_scan_state(state)


def clear_shared_scan_for_session(session_id):
    if not session_id:
        return
    with _scan_state_lock:
        state = load_shared_scan_state()
        if str(session_id) in state:
            state.pop(str(session_id), None)
            save_shared_scan_state(state)


# --- Collector State ---

def load_collector_state():
    if not os.path.exists(COLLECTOR_STATE_PATH):
        return {}
    try:
        with open(COLLECTOR_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_collector_state(state):
    try:
        with open(COLLECTOR_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


# --- Spectator Multi-Stream State ---
# Dict keyed by stream_url: {pid, started_at, stopped_at, running, log_path}

def load_spectator_state():
    """Load spectator streams state dict (keyed by stream_url)."""
    if not os.path.exists(SPECTATOR_STATE_PATH):
        return {}
    try:
        with open(SPECTATOR_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_spectator_state(state):
    try:
        with open(SPECTATOR_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def load_priority_spectator_state():
    if not os.path.exists(PRIORITY_SPECTATOR_STATE_PATH):
        return {}
    try:
        with open(PRIORITY_SPECTATOR_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_priority_spectator_state(state):
    try:
        with open(PRIORITY_SPECTATOR_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass
