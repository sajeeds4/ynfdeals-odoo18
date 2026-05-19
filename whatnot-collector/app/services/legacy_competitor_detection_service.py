from __future__ import annotations

from server.events_db import get_stream_detection_feed, get_stream_title_quality


def _with_status(payload: dict, status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def get_legacy_competitor_title_quality(stream_id: int | None = None):
    stream_id_value = int(stream_id or 0)
    if stream_id_value <= 0:
        return _with_status({"ok": False, "error": "stream_id required"}, 400)

    try:
        return {"ok": True, **get_stream_title_quality(stream_id_value)}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_competitor_detection_feed(stream_id: int | None = None):
    stream_id_value = int(stream_id or 0)
    if stream_id_value <= 0:
        return _with_status({"ok": False, "error": "stream_id required"}, 400)

    try:
        return {"ok": True, **get_stream_detection_feed(stream_id_value)}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)