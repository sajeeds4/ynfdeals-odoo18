from __future__ import annotations

from server.api import TARGET_COMPETITOR_WATCHLIST, _attach_followed_flags
from server.events_db import get_audience_user_profile, get_audience_users, get_cross_stream_users, get_target_buyers


def _with_status(payload: dict, status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def get_legacy_users_cross_stream(min_streams: int = 2, limit: int = 500, q: str = ""):
    try:
        payload = get_cross_stream_users(min_streams=min_streams, limit=limit, q=q)
        return {"ok": True, **payload}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_users_audience(min_streams: int = 1, limit: int = 1000, q: str = ""):
    try:
        users = _attach_followed_flags(get_audience_users(min_streams=min_streams, limit=limit, q=(q or "").strip().lower()))
        totals = {
            "unique_users": len(users),
            "total_spent": round(sum(float(row.get("total_spent") or 0) for row in users), 2),
            "total_wins": sum(int(row.get("total_wins") or 0) for row in users),
            "total_bids": sum(int(row.get("bids") or 0) for row in users),
            "total_chat_messages": sum(int(row.get("chat_messages") or 0) for row in users),
            "buyers": sum(1 for row in users if int(row.get("total_wins") or 0) > 0),
            "chatters": sum(1 for row in users if int(row.get("chat_messages") or 0) > 0),
            "bidders": sum(1 for row in users if int(row.get("bids") or 0) > 0),
            "cross_stream_users": sum(1 for row in users if int(row.get("stream_count") or 0) >= 2),
        }
        return {"ok": True, "users": users, "total": len(users), "totals": totals}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_users_profile(username: str | None = None):
    clean = (username or "").strip()
    if not clean:
        return _with_status({"ok": False, "error": "username required"}, 400)
    try:
        profile = get_audience_user_profile(clean)
        if not profile:
            return _with_status({"ok": False, "error": "User not found"}, 404)
        return {"ok": True, **profile}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_target_buyers(
    sellers: str | None = None,
    min_streamers: int = 2,
    limit: int = 50,
    q: str = "",
):
    watchlist = [
        (value or "").strip().lower()
        for value in (sellers or "").split(",")
        if (value or "").strip()
    ] or TARGET_COMPETITOR_WATCHLIST
    try:
        payload = get_target_buyers(
            streamer_names=watchlist,
            min_streamers=min_streamers,
            limit=limit,
            q=(q or "").strip().lower(),
        )
        payload["buyers"] = _attach_followed_flags(payload.get("buyers") or [])
        return {"ok": True, **payload}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)
