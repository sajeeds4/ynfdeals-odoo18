from __future__ import annotations

from fastapi import APIRouter, Body, Request, Response

from app.services.legacy_sidecar_ops_service import (
    get_legacy_company_prep,
    get_legacy_employee_pos_tokens,
    get_legacy_internal_pos_buyers,
    get_legacy_internal_pos_me,
    get_legacy_internal_pos_order_detail,
    get_legacy_internal_pos_orders_history,
    get_legacy_internal_pos_orders_mine,
    get_legacy_internal_pos_products,
    get_legacy_qr_code,
    mutate_legacy_create_pos_token,
    mutate_legacy_ensure_sale_order,
    mutate_legacy_in_house_order_approve,
    mutate_legacy_in_house_order_cancel,
    mutate_legacy_in_house_order_reject,
    mutate_legacy_in_house_sale,
    mutate_legacy_internal_pos_orders_merge,
    mutate_legacy_internal_pos_orders_split,
    mutate_legacy_internal_pos_orders_update,
    mutate_legacy_internal_pos_orders,
    mutate_legacy_picklist_upload,
    render_legacy_picklist_enriched_pdf,
    mutate_legacy_revoke_pos_token,
    mutate_legacy_rotate_pos_token,
    mutate_legacy_users_follow,
)


router = APIRouter()


def _respond(payload: dict, response: Response):
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.get("/api/company/prep")
def legacy_company_prep(response: Response):
    return _respond(get_legacy_company_prep(), response)


@router.post("/api/users/follow")
def legacy_users_follow(response: Response, payload: dict | None = Body(default=None)):
    response.status_code = 410
    return {"ok": False, "error": "competitor_monitoring_retired"}


@router.post("/api/picklist/upload")
async def legacy_picklist_upload(request: Request, response: Response, session_id: int | None = None, filename: str | None = None):
    raw = await request.body()
    return _respond(mutate_legacy_picklist_upload(raw, session_id=session_id, filename=filename), response)


@router.post("/api/whatnot_labels/enrich_pdf")
async def legacy_picklist_enrich_pdf(request: Request, session_id: int | None = None, filename: str | None = None):
    raw = await request.body()
    payload = render_legacy_picklist_enriched_pdf(raw, session_id=session_id, filename=filename)
    status = payload.pop("_status", None)
    if status or not payload.get("ok"):
        return Response(
            content=(payload.get("error") or "error"),
            status_code=status or 400,
            media_type="text/plain; charset=utf-8",
        )
    return Response(
        content=payload["content"],
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{payload["filename"]}"',
            "X-YNF-Annotated-Pages": str(payload.get("annotated_pages") or 0),
            "X-YNF-Total-Pages": str(payload.get("total_pages") or 0),
        },
    )


@router.post("/api/in_house_sales")
def legacy_in_house_sales(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_in_house_sale(payload or {}), response)


@router.post("/api/employees/pos_token/create")
def legacy_create_pos_token(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_create_pos_token(payload or {}), response)


@router.get("/api/employees/pos_tokens")
def legacy_employee_pos_tokens(response: Response, employee_id: int | None = None, employee_name: str | None = None):
    return _respond(get_legacy_employee_pos_tokens(employee_id=employee_id, employee_name=employee_name), response)


@router.post("/api/employees/pos_token/revoke")
def legacy_revoke_pos_token(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_revoke_pos_token(payload or {}), response)


@router.post("/api/employees/pos_token/rotate")
def legacy_rotate_pos_token(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_rotate_pos_token(payload or {}), response)


@router.get("/api/internal_pos/me")
def legacy_internal_pos_me(response: Response, token: str | None = None):
    return _respond(get_legacy_internal_pos_me(token), response)


@router.get("/api/internal_pos/products")
def legacy_internal_pos_products(response: Response, token: str | None = None, q: str | None = None, code: str | None = None):
    return _respond(get_legacy_internal_pos_products(token, q=q, code=code), response)


@router.get("/api/qr_code")
def legacy_qr_code(response: Response, value: str | None = None):
    return _respond(get_legacy_qr_code(value=value), response)


@router.get("/api/internal_pos/buyers")
def legacy_internal_pos_buyers(response: Response, q: str | None = None):
    return _respond(get_legacy_internal_pos_buyers(q=q), response)


@router.get("/api/internal_pos/orders/mine")
def legacy_internal_pos_orders_mine(response: Response, token: str | None = None):
    return _respond(get_legacy_internal_pos_orders_mine(token), response)


@router.get("/api/internal_pos/orders/history")
def legacy_internal_pos_orders_history(response: Response, employee_id: int | None = None, buyer_name: str | None = None, buyer_phone: str | None = None, buyer_email: str | None = None):
    return _respond(get_legacy_internal_pos_orders_history(employee_id=employee_id, buyer_name=buyer_name, buyer_phone=buyer_phone, buyer_email=buyer_email), response)


@router.get("/api/internal_pos/orders/detail")
def legacy_internal_pos_order_detail(response: Response, id: int | None = None, buyer_name: str | None = None, buyer_phone: str | None = None, buyer_email: str | None = None):
    return _respond(get_legacy_internal_pos_order_detail(id, buyer_name=buyer_name, buyer_phone=buyer_phone, buyer_email=buyer_email), response)


@router.post("/api/internal_pos/orders")
def legacy_internal_pos_orders(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_internal_pos_orders(payload or {}), response)


@router.post("/api/internal_pos/orders/update")
def legacy_internal_pos_orders_update(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_internal_pos_orders_update(payload or {}), response)


@router.post("/api/internal_pos/orders/split")
def legacy_internal_pos_orders_split(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_internal_pos_orders_split(payload or {}), response)


@router.post("/api/internal_pos/orders/merge")
def legacy_internal_pos_orders_merge(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_internal_pos_orders_merge(payload or {}), response)


@router.post("/api/in_house_orders/approve")
def legacy_in_house_order_approve(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_in_house_order_approve(payload or {}), response)


@router.post("/api/in_house_orders/reject")
def legacy_in_house_order_reject(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_in_house_order_reject(payload or {}), response)


@router.post("/api/in_house_orders/cancel")
def legacy_in_house_order_cancel(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_in_house_order_cancel(payload or {}), response)


@router.post("/api/orders/ensure_sale_order")
def legacy_orders_ensure_sale_order(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_ensure_sale_order(payload or {}), response)
