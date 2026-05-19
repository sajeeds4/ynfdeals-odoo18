from __future__ import annotations

from server.api import OUR_WHATNOT_ACCOUNT
from server.company_db import (
    create_company_session,
    delete_category,
    ensure_category,
    get_customer,
    get_setting_map,
    update_company_session,
    update_customer,
    upsert_setting,
)


def _with_status(payload: dict, status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def mutate_session_create(name=None, show_id=None, whatnot_account=None, status="live"):
    clean_name = (name or "").strip()
    if not clean_name:
        return _with_status({"ok": False, "error": "name required"}, 400)
    try:
        result = create_company_session(
            show_id=show_id,
            whatnot_account=whatnot_account or OUR_WHATNOT_ACCOUNT,
            name=clean_name,
            status=status or "live",
        )
        return {"ok": True, "id": result.get("id"), "session": result}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_session_update(payload: dict):
    session_id = payload.get("session_id") or payload.get("id")
    if not session_id:
        return _with_status({"ok": False, "error": "session_id required"}, 400)
    try:
        vals = {}
        if payload.get("name") is not None:
            vals["name"] = payload.get("name")
        if payload.get("status") is not None:
            vals["status"] = payload.get("status")
        if payload.get("whatnot_account") is not None:
            vals["whatnot_account"] = payload.get("whatnot_account")
        if payload.get("show_id") is not None:
            vals["show_id"] = payload.get("show_id")
        if payload.get("end_time") is not None:
            vals["ended_at"] = payload.get("end_time")
        result = update_company_session(int(session_id), **vals)
        return {"ok": bool(result), "session": result}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_customer_update(payload: dict):
    customer_id = payload.get("customer_id") or payload.get("id")
    if not customer_id:
        return _with_status({"ok": False, "error": "customer_id required"}, 400)
    try:
        current = get_customer(int(customer_id))
        if not current:
            return _with_status({"ok": False, "error": "customer_not_found"}, 404)
        customer = update_customer(
            int(customer_id),
            display_name=payload.get("display_name"),
            email=payload.get("email"),
            phone=payload.get("phone"),
            notes=payload.get("notes"),
        )
        if customer:
            customer["name"] = customer.get("display_name")
        return {"ok": bool(customer), "customer": customer}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_fee_settings_save(payload: dict):
    try:
        if "platform_fee_pct" in payload:
            upsert_setting("platform_fee_pct", float(payload["platform_fee_pct"]))
        if "fixed_fee" in payload:
            upsert_setting("fixed_fee", float(payload["fixed_fee"]))
        return {"ok": True}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_recalc_fees():
    try:
        settings = get_setting_map()
        fee_pct = float(settings.get("platform_fee_pct", 10.9))
        fixed_fee = float(settings.get("fixed_fee", 0.50))
        from server.company_db import recalc_all_fees

        count = recalc_all_fees(fee_pct=fee_pct, fixed_fee=fixed_fee)
        return {"ok": True, "updated": count, "fee_pct": fee_pct, "fixed_fee": fixed_fee}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_inventory_category_create(payload: dict):
    try:
        cat = ensure_category(payload.get("name", ""))
        if not cat:
            return _with_status({"ok": False, "error": "name required"}, 400)
        return {"ok": True, "category": cat}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_inventory_category_delete(payload: dict):
    cat_id = payload.get("id")
    if not cat_id:
        return _with_status({"ok": False, "error": "id required"}, 400)
    try:
        delete_category(int(cat_id))
        return {"ok": True}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)
