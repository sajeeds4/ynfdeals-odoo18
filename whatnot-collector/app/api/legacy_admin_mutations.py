from __future__ import annotations

from fastapi import APIRouter, Body, Response

from app.services.legacy_admin_mutation_service import (
    mutate_customer_update,
    mutate_fee_settings_save,
    mutate_inventory_category_create,
    mutate_inventory_category_delete,
    mutate_recalc_fees,
    mutate_session_create,
    mutate_session_update,
)


router = APIRouter()


def _respond(payload: dict, response: Response):
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.post("/api/sessions/create")
def legacy_sessions_create(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(
        mutate_session_create(
            name=payload.get("name"),
            show_id=payload.get("show_id"),
            whatnot_account=payload.get("whatnot_account"),
            status=payload.get("status", "live"),
        ),
        response,
    )


@router.post("/api/sessions/update")
def legacy_sessions_update(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(mutate_session_update(payload), response)


@router.post("/api/customers/update")
def legacy_customers_update(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(mutate_customer_update(payload), response)


@router.post("/api/fee_settings/save")
def legacy_fee_settings_save(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(mutate_fee_settings_save(payload), response)


@router.post("/api/recalc_fees")
def legacy_recalc_fees(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_recalc_fees(), response)


@router.post("/api/inventory/categories")
def legacy_inventory_categories_create(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(mutate_inventory_category_create(payload), response)


@router.post("/api/inventory/categories/delete")
def legacy_inventory_categories_delete(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(mutate_inventory_category_delete(payload), response)
