from __future__ import annotations

from fastapi import APIRouter

from server.api import _process_event_side_effects
from server.collector_manager import collector_status
from server.company_db import update_company_session
from server.events_db import get_events_since, get_latest_id, get_recent_events, get_stream_id
from server.state import load_collector_state


router = APIRouter()


def _active_or_saved_stream_id() -> int | None:
    status = collector_status()
    if status.get("running") and status.get("stream_url"):
        return get_stream_id(status.get("stream_url"))
    saved = load_collector_state()
    saved_url = saved.get("stream_url")
    return get_stream_id(saved_url) if saved_url else None


@router.get("/latest_id")
def latest_id():
    return {"latest_id": get_latest_id()}


@router.get("/events")
def events(
    since: int = 0,
    limit: int = 500,
    stream_id: int | None = None,
    stream_url: str | None = None,
):
    limit = max(1, min(int(limit), 5000))
    process_side_effects = False
    if stream_id is not None:
        resolved_stream_id = int(stream_id)
        status = collector_status()
        collector_stream_id = None
        if status.get("running") and status.get("stream_url") and status.get("stream_mode") == "our_stream":
            collector_stream_id = get_stream_id(status.get("stream_url"))
            company_session_id = status.get("session_id")
            if collector_stream_id is not None and company_session_id:
                try:
                    update_company_session(int(company_session_id), stream_id=int(collector_stream_id))
                except Exception:
                    pass
        process_side_effects = collector_stream_id is not None and resolved_stream_id == collector_stream_id
    elif stream_url:
        resolved_stream_id = get_stream_id(stream_url)
    else:
        status = collector_status()
        if status.get("running") and status.get("stream_url"):
            resolved_stream_id = get_stream_id(status.get("stream_url"))
            company_session_id = status.get("session_id")
            if resolved_stream_id is not None and company_session_id and status.get("stream_mode") == "our_stream":
                try:
                    update_company_session(int(company_session_id), stream_id=int(resolved_stream_id))
                except Exception:
                    pass
        else:
            resolved_stream_id = _active_or_saved_stream_id()
        process_side_effects = resolved_stream_id is not None

    rows = get_events_since(int(since), stream_id=resolved_stream_id, limit=limit)
    if process_side_effects:
        _process_event_side_effects(rows, stream_id=resolved_stream_id)
    return {"events": rows, "has_more": len(rows) >= limit}


@router.get("/recent")
def recent(limit: int = 200, stream_id: int | None = None, stream_url: str | None = None):
    if stream_id is not None:
        resolved_stream_id = int(stream_id)
    elif stream_url:
        resolved_stream_id = get_stream_id(stream_url)
    else:
        resolved_stream_id = _active_or_saved_stream_id()
    return {"events": get_recent_events(int(limit), stream_id=resolved_stream_id)}
