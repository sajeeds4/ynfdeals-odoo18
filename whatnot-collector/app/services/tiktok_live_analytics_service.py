"""Stub for TikTok Live analytics service — not yet implemented."""

_NOT_IMPL = {"ok": False, "error": "tiktok_live_analytics_not_configured"}


def get_tiktok_live_overview(**kwargs):
    return dict(_NOT_IMPL)


def get_tiktok_live_sessions_page(**kwargs):
    return {"ok": True, "rows": [], "total": 0}


def get_tiktok_live_session_detail(session_id, **kwargs):
    return dict(_NOT_IMPL)


def get_tiktok_live_orders_page(**kwargs):
    return {"ok": True, "rows": [], "total": 0}


def get_tiktok_live_order_detail(order_id, **kwargs):
    return dict(_NOT_IMPL)


def get_tiktok_live_customers_page(**kwargs):
    return {"ok": True, "rows": [], "total": 0}


def get_tiktok_live_customer_detail(customer_id, **kwargs):
    return dict(_NOT_IMPL)


def get_tiktok_live_products_page(**kwargs):
    return {"ok": True, "rows": [], "total": 0}


def get_tiktok_live_product_detail(product_id, **kwargs):
    return dict(_NOT_IMPL)


def get_tiktok_live_returns_page(**kwargs):
    return {"ok": True, "rows": [], "total": 0}
