from __future__ import annotations

from fastapi import APIRouter, Response

from app.services.legacy_runtime_service import (
    get_legacy_company_history_detail,
    get_legacy_company_history_sessions,
    get_legacy_customer_detail,
    get_legacy_customer_orders,
    get_legacy_customer_profile_lookup,
    get_legacy_customer_review_status,
    get_legacy_customer_reviews,
    get_legacy_product_profit_report,
    get_legacy_products,
    get_legacy_products_full,
)


router = APIRouter()


@router.get("/api/products")
def legacy_products():
    return get_legacy_products()


@router.get("/api/products_full")
def legacy_products_full():
    return get_legacy_products_full()


@router.get("/api/customers/detail")
def legacy_customer_detail(customer_id: int, response: Response):
    payload = get_legacy_customer_detail(customer_id)
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.get("/api/customers/profile_lookup")
def legacy_customer_profile_lookup(
    response: Response,
    customer_id: int | None = None,
    username: str | None = None,
):
    payload = get_legacy_customer_profile_lookup(customer_id=customer_id, username=username)
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.get("/api/customers/orders")
def legacy_customer_orders(partner_id: int, response: Response):
    payload = get_legacy_customer_orders(partner_id)
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.get("/api/customers/reviews")
def legacy_customer_reviews(response: Response, q: str = "", matched_only: int = 0):
    response.status_code = 410
    return {"ok": False, "error": "reviews_feature_removed"}


@router.get("/api/customers/reviews/status")
def legacy_customer_reviews_status(response: Response, seller_username: str = ""):
    response.status_code = 410
    return {"ok": False, "error": "reviews_feature_removed"}


@router.get("/api/history/company_sessions")
def legacy_company_history_sessions(limit: int = 15):
    return get_legacy_company_history_sessions(limit=limit)


@router.get("/api/history/company_detail")
def legacy_company_history_detail(stream_id: int, response: Response):
    payload = get_legacy_company_history_detail(stream_id)
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.get("/api/reports/product_profit")
def legacy_product_profit_report(session_id: int | None = None, q: str = ""):
    return get_legacy_product_profit_report(session_id=session_id, q=q)
