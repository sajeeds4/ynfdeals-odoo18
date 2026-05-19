from __future__ import annotations

from fastapi import APIRouter

from app.services.legacy_product_profit_service import get_legacy_product_profit


router = APIRouter()


@router.get("/api/product_profit")
def legacy_product_profit(session_id: str | None = None):
    return get_legacy_product_profit(session_id=session_id)
