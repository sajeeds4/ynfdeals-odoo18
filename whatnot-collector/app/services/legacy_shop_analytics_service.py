from __future__ import annotations

from server.shop_scraper import get_scrape_status, get_shop_products


def _with_status(payload: dict, status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def get_legacy_shop_products(streamer_name: str | None = None):
    if not streamer_name:
        return _with_status({"ok": False, "error": "streamer_name required"}, 400)
    try:
        result = get_shop_products(streamer_name)
        return {"ok": True, **result}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_shop_scrape_status(streamer_name: str | None = None):
    if not streamer_name:
        return _with_status({"ok": False, "error": "streamer_name required"}, 400)
    try:
        return {"ok": True, **get_scrape_status(streamer_name)}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)