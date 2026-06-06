"""Stub for live commerce intelligence service — not yet implemented."""

_NOT_IMPL = {"ok": False, "error": "live_commerce_intelligence_not_configured"}


def analytics_data_catalog(**kwargs):
    return {"ok": True, "catalog": []}


def ensure_live_commerce_analytics_schema(**kwargs):
    return {"ok": True}


def get_live_commerce_session_intelligence(session_id, **kwargs):
    return dict(_NOT_IMPL)


def refresh_live_commerce_analytics(**kwargs):
    return dict(_NOT_IMPL)
