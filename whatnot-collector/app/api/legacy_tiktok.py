from __future__ import annotations

from fastapi import APIRouter, Response

from app.services.legacy_tiktok_service import (
    apply_tiktok_live_session_inventory_service,
    create_tiktok_live_order,
    create_tiktok_shop_order,
    get_tiktok_live_label_artifact,
    get_tiktok_live_next_sequence,
    get_tiktok_live_google_sheet_backup_status,
    get_tiktok_live_sessions,
    get_tiktok_live_session_active,
    get_tiktok_extractor_lot_state,
    get_tiktok_live_picklist,
    import_tiktok_shop_orders,
    set_tiktok_extractor_lot_state,
    update_tiktok_operator_config,
)
from app.services.tiktok_live_analytics_service import (
    get_tiktok_live_customer_detail,
    get_tiktok_live_customers_page,
    get_tiktok_live_order_detail,
    get_tiktok_live_orders_page,
    get_tiktok_live_overview,
    get_tiktok_live_product_detail,
    get_tiktok_live_products_page,
    get_tiktok_live_returns_page,
    get_tiktok_live_session_detail,
    get_tiktok_live_sessions_page,
)
from app.services.live_commerce_intelligence_service import (
    analytics_data_catalog,
    ensure_live_commerce_analytics_schema,
    get_live_commerce_session_intelligence,
    refresh_live_commerce_analytics,
)


router = APIRouter()


def _respond(payload: dict, response: Response):
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.get("/api/tiktok_extractor/lot_state")
def legacy_tiktok_extractor_lot_state(response: Response, stream_url: str | None = None):
    return _respond(get_tiktok_extractor_lot_state(stream_url=stream_url), response)


@router.post("/api/tiktok_extractor/lot_state")
def legacy_tiktok_extractor_lot_state_update(payload: dict, response: Response):
    return _respond(
        set_tiktok_extractor_lot_state(
            stream_url=payload.get("stream_url"),
            next_lot=payload.get("next_lot"),
        ),
        response,
    )


@router.post("/api/tiktok_operator/config")
def legacy_tiktok_operator_config(payload: dict, response: Response):
    return _respond(
        update_tiktok_operator_config(
            enabled=bool(payload.get("enabled")),
            streamer=payload.get("streamer"),
        ),
        response,
    )


@router.post("/api/tiktok_shop_orders/create")
def legacy_tiktok_shop_orders_create(payload: dict, response: Response):
    return _respond(create_tiktok_shop_order(payload), response)


@router.post("/api/tiktok_live_orders/create")
def legacy_tiktok_live_orders_create(payload: dict, response: Response):
    return _respond(create_tiktok_live_order(payload), response)


@router.post("/api/tiktok_shop_orders/import_csv")
def legacy_tiktok_shop_orders_import_csv(payload: dict, response: Response):
    return _respond(
        import_tiktok_shop_orders(
            csv_text=payload.get("csv_text"),
            commit=bool(payload.get("commit")),
        ),
        response,
    )


@router.get("/api/tiktok_live_picklist")
def legacy_tiktok_live_picklist(response: Response, session_id: int | None = None):
    return _respond(get_tiktok_live_picklist(session_id), response)


@router.get("/api/tiktok_live_sessions")
def legacy_tiktok_live_sessions(response: Response, limit: int = 80, summary: int = 0):
    return _respond(get_tiktok_live_sessions(limit=limit, summary=bool(summary)), response)


@router.get("/api/tiktok_live_sessions/active")
def legacy_tiktok_live_sessions_active(response: Response):
    return _respond(get_tiktok_live_session_active(), response)


@router.get("/api/tiktok_live_sessions/next_sequence")
def legacy_tiktok_live_sessions_next_sequence(response: Response):
    return _respond(get_tiktok_live_next_sequence(), response)


@router.get("/api/tiktok_live_sessions/google_sheet_backup_status")
def legacy_tiktok_live_sessions_google_sheet_backup_status(response: Response, session_id: int | None = None):
    return _respond(get_tiktok_live_google_sheet_backup_status(session_id), response)


@router.get("/api/tiktok_live_labels/artifacts")
def legacy_tiktok_live_label_artifact(response: Response, session_key: str | None = None):
    return _respond(get_tiktok_live_label_artifact(session_key=session_key), response)


@router.post("/api/tiktok_live_sessions/apply_inventory")
def legacy_tiktok_live_apply_inventory(payload: dict, response: Response):
    return _respond(apply_tiktok_live_session_inventory_service(payload.get("session_id")), response)


@router.get("/api/tiktok_live_analytics/overview")
def tiktok_live_analytics_overview(
    response: Response,
    date_from: str | None = None,
    date_to: str | None = None,
    session_id: int | None = None,
    customer: str | None = None,
    product: str | None = None,
    brand: str | None = None,
    status: str | None = None,
    profitability: str | None = None,
    q: str | None = None,
    return_status: str | None = None,
):
    return _respond(
        get_tiktok_live_overview(
            date_from=date_from,
            date_to=date_to,
            session_id=session_id,
            customer=customer,
            product=product,
            brand=brand,
            status=status,
            profitability=profitability,
            q=q,
            return_status=return_status,
        ),
        response,
    )


@router.get("/api/tiktok_live_analytics/sessions")
def tiktok_live_analytics_sessions(
    response: Response,
    page: int = 1,
    page_size: int = 25,
    date_from: str | None = None,
    date_to: str | None = None,
    customer: str | None = None,
    product: str | None = None,
    brand: str | None = None,
    status: str | None = None,
    profitability: str | None = None,
    q: str | None = None,
    return_status: str | None = None,
):
    return _respond(
        get_tiktok_live_sessions_page(
            page=page,
            page_size=page_size,
            date_from=date_from,
            date_to=date_to,
            customer=customer,
            product=product,
            brand=brand,
            status=status,
            profitability=profitability,
            q=q,
            return_status=return_status,
        ),
        response,
    )


@router.get("/api/tiktok_live_analytics/sessions/{session_id}")
def tiktok_live_analytics_session_detail(session_id: int, response: Response):
    return _respond(get_tiktok_live_session_detail(session_id), response)


@router.get("/api/tiktok_live_analytics/products")
def tiktok_live_analytics_products(
    response: Response,
    page: int = 1,
    page_size: int = 25,
    date_from: str | None = None,
    date_to: str | None = None,
    session_id: int | None = None,
    customer: str | None = None,
    product: str | None = None,
    brand: str | None = None,
    status: str | None = None,
    profitability: str | None = None,
    q: str | None = None,
    return_status: str | None = None,
):
    return _respond(
        get_tiktok_live_products_page(
            page=page,
            page_size=page_size,
            date_from=date_from,
            date_to=date_to,
            session_id=session_id,
            customer=customer,
            product=product,
            brand=brand,
            status=status,
            profitability=profitability,
            q=q,
            return_status=return_status,
        ),
        response,
    )


@router.get("/api/tiktok_live_analytics/products/{product_id}")
def tiktok_live_analytics_product_detail(product_id: int, response: Response):
    return _respond(get_tiktok_live_product_detail(product_id), response)


@router.get("/api/tiktok_live_analytics/orders")
def tiktok_live_analytics_orders(
    response: Response,
    page: int = 1,
    page_size: int = 25,
    date_from: str | None = None,
    date_to: str | None = None,
    session_id: int | None = None,
    customer: str | None = None,
    product: str | None = None,
    brand: str | None = None,
    status: str | None = None,
    profitability: str | None = None,
    q: str | None = None,
    return_status: str | None = None,
):
    return _respond(
        get_tiktok_live_orders_page(
            page=page,
            page_size=page_size,
            date_from=date_from,
            date_to=date_to,
            session_id=session_id,
            customer=customer,
            product=product,
            brand=brand,
            status=status,
            profitability=profitability,
            q=q,
            return_status=return_status,
        ),
        response,
    )


@router.get("/api/tiktok_live_analytics/orders/{order_id}")
def tiktok_live_analytics_order_detail(order_id: int, response: Response):
    return _respond(get_tiktok_live_order_detail(order_id), response)


@router.get("/api/tiktok_live_analytics/customers")
def tiktok_live_analytics_customers(
    response: Response,
    page: int = 1,
    page_size: int = 25,
    date_from: str | None = None,
    date_to: str | None = None,
    session_id: int | None = None,
    customer: str | None = None,
    product: str | None = None,
    brand: str | None = None,
    status: str | None = None,
    profitability: str | None = None,
    q: str | None = None,
    return_status: str | None = None,
):
    return _respond(
        get_tiktok_live_customers_page(
            page=page,
            page_size=page_size,
            date_from=date_from,
            date_to=date_to,
            session_id=session_id,
            customer=customer,
            product=product,
            brand=brand,
            status=status,
            profitability=profitability,
            q=q,
            return_status=return_status,
        ),
        response,
    )


@router.get("/api/tiktok_live_analytics/customers/{customer_key}")
def tiktok_live_analytics_customer_detail(customer_key: str, response: Response):
    return _respond(get_tiktok_live_customer_detail(customer_key), response)


@router.get("/api/tiktok_live_analytics/returns")
def tiktok_live_analytics_returns(
    response: Response,
    page: int = 1,
    page_size: int = 25,
    date_from: str | None = None,
    date_to: str | None = None,
    session_id: int | None = None,
    customer: str | None = None,
    product: str | None = None,
    brand: str | None = None,
    status: str | None = None,
    profitability: str | None = None,
    q: str | None = None,
    return_status: str | None = None,
):
    return _respond(
        get_tiktok_live_returns_page(
            page=page,
            page_size=page_size,
            date_from=date_from,
            date_to=date_to,
            session_id=session_id,
            customer=customer,
            product=product,
            brand=brand,
            status=status,
            profitability=profitability,
            q=q,
            return_status=return_status,
        ),
        response,
    )


@router.get("/api/live_commerce_intelligence/catalog")
def live_commerce_intelligence_catalog(response: Response):
    return _respond(analytics_data_catalog(), response)


@router.post("/api/live_commerce_intelligence/ensure_schema")
def live_commerce_intelligence_ensure_schema(response: Response):
    return _respond(ensure_live_commerce_analytics_schema(), response)


@router.post("/api/live_commerce_intelligence/refresh")
def live_commerce_intelligence_refresh(response: Response, session_id: int | None = None):
    return _respond(refresh_live_commerce_analytics(session_id=session_id), response)


@router.get("/api/live_commerce_intelligence/sessions/{session_id}")
def live_commerce_intelligence_session(session_id: int, response: Response):
    return _respond(get_live_commerce_session_intelligence(session_id), response)
