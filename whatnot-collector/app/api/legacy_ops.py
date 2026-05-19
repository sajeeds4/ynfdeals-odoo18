from __future__ import annotations

from fastapi import APIRouter

from app.services.legacy_runtime_service import (
    get_legacy_auction_results,
    get_legacy_customers,
    get_legacy_orders,
    get_legacy_winner_assignment_state,
)


router = APIRouter()


@router.get("/api/winner_assignment/state")
def legacy_winner_assignment_state(session_id: int | None = None, limit: int = 200):
    return get_legacy_winner_assignment_state(session_id=session_id, limit=limit)


@router.get("/api/orders")
def legacy_orders(session_id: int | None = None, q: str = "", limit: int | None = None, offset: int = 0):
    return get_legacy_orders(session_id=session_id, q=q, limit=limit, offset=offset)


@router.get("/api/customers")
def legacy_customers(q: str = "", has_orders: int = 0, limit: int | None = None, offset: int = 0):
    return get_legacy_customers(q=q, has_orders=has_orders in (1, True), limit=limit, offset=offset)


@router.get("/api/auction_results")
def legacy_auction_results(session_id: int | None = None, scope: str = "", q: str = "", limit: int = 500):
    return get_legacy_auction_results(session_id=session_id, scope=scope, q=q, limit=limit)
