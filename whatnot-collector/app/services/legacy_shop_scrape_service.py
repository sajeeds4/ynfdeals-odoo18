from __future__ import annotations

from server.shop_scraper import get_scrape_status, start_shop_scrape


def _with_status(payload: dict, status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def trigger_legacy_shop_scrape(streamer_name: str | None = None):
    streamer_name_value = (streamer_name or "").strip()
    if not streamer_name_value:
        return _with_status({"ok": False, "error": "streamer_name required"}, 400)
    try:
        started = start_shop_scrape(streamer_name_value)
        status = get_scrape_status(streamer_name_value)
        return {"ok": True, "started": started, **status}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)
