from fastapi import APIRouter

from app.services.inventory_service import (
    get_inventory_overview,
    get_inventory_product_detail,
    list_inventory_categories,
    list_inventory_products,
    list_inventory_vendors,
    list_product_audit,
    list_product_movements,
)

router = APIRouter()


@router.get("/summary")
def inventory_summary():
    return get_inventory_overview()


@router.get("/products")
def inventory_products(active_only: bool = True):
    return {"ok": True, "rows": list_inventory_products(active_only=active_only)}


@router.get("/categories")
def inventory_categories():
    return list_inventory_categories()


@router.get("/vendors")
def inventory_vendors():
    return list_inventory_vendors()


@router.get("/movements")
def inventory_movements(product_id: int | None = None, limit: int = 50):
    return list_product_movements(product_id=product_id, limit=limit)


@router.get("/audit")
def inventory_audit(product_id: int | None = None, limit: int = 50):
    return list_product_audit(product_id=product_id, limit=limit)


@router.get("/products/{product_id}")
def inventory_product_detail(product_id: int):
    return get_inventory_product_detail(product_id)
