from __future__ import annotations

from server.collector_manager import collector_status
from server.events_db import get_all_streams, get_analytics_trends, get_competitor_businesses, get_stream_id
from server.state import load_collector_state


def _with_status(payload: dict, status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def _resolve_our_stream_context() -> tuple[set[str], set[str]]:
    our_urls = set()
    status = collector_status()
    if status.get("stream_url"):
        our_urls.add(status["stream_url"])

    saved = load_collector_state()
    if saved.get("stream_url"):
        our_urls.add(saved["stream_url"])

    all_urls = our_urls | {url.split("?")[0] for url in our_urls}
    our_streamer_names = set()
    streams_by_id = {int(row.get("id") or 0): row for row in get_all_streams()}
    for url in all_urls:
        sid = get_stream_id(url)
        if not sid:
            continue
        row = streams_by_id.get(int(sid))
        if row and row.get("streamer_name"):
            our_streamer_names.add(row["streamer_name"])
    return all_urls, our_streamer_names


def get_legacy_analytics_businesses():
    try:
        our_stream_urls, our_streamer_names = _resolve_our_stream_context()
        businesses = get_competitor_businesses(
            our_stream_urls=our_stream_urls,
            our_streamer_names=our_streamer_names,
        )
        return {"ok": True, "businesses": businesses}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_analytics_trends(streamer_name: str | None = None):
    if not streamer_name:
        return _with_status({"ok": False, "error": "streamer_name required"}, 400)

    try:
        our_stream_urls, our_streamer_names = _resolve_our_stream_context()
        data = get_analytics_trends(
            streamer_name,
            our_stream_urls=our_stream_urls,
            our_streamer_names=our_streamer_names,
        )
        return {"ok": True, **data}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)
