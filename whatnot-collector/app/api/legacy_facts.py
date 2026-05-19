from __future__ import annotations

from fastapi import APIRouter, Query, Response

from app.services.legacy_facts_service import get_legacy_fact_buyers, get_legacy_fact_lots, get_legacy_fact_products


router = APIRouter()


def _respond(payload: dict, response: Response):
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.get("/api/facts/lots")
def legacy_fact_lots(
    response: Response,
    stream_id: str | None = None,
    streamer_name: str | None = None,
    confidence: str | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    limit: int = 200,
    refresh: str = "auto",
):
    return _respond(
        get_legacy_fact_lots(
            stream_id=stream_id,
            streamer_name=streamer_name,
            confidence=confidence,
            from_ts=from_,
            to_ts=to,
            limit=limit,
            refresh=refresh,
        ),
        response,
    )


@router.get("/api/facts/buyers")
def legacy_fact_buyers(
    response: Response,
    stream_id: str | None = None,
    streamer_name: str | None = None,
    tier: str | None = None,
    q: str | None = None,
    min_spend: float = 0,
    limit: int = 200,
    refresh: str = "auto",
):
    return _respond(
        get_legacy_fact_buyers(
            stream_id=stream_id,
            streamer_name=streamer_name,
            tier=tier,
            q=q,
            min_spend=min_spend,
            limit=limit,
            refresh=refresh,
        ),
        response,
    )


@router.get("/api/facts/products")
def legacy_fact_products(
    response: Response,
    stream_id: str | None = None,
    streamer_name: str | None = None,
    q: str | None = None,
    min_sold: int = 0,
    limit: int = 200,
    refresh: str = "auto",
):
    return _respond(
        get_legacy_fact_products(
            stream_id=stream_id,
            streamer_name=streamer_name,
            q=q,
            min_sold=min_sold,
            limit=limit,
            refresh=refresh,
        ),
        response,
    )
