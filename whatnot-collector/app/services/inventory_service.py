from server.company_db import (
    get_product_detail,
    inventory_summary,
    list_categories,
    list_inventory_audit_logs,
    list_inventory_movements,
    list_products,
    list_vendors,
)


def get_inventory_overview():
    return {"ok": True, **inventory_summary()}


def list_inventory_products(active_only: bool = True):
    return list_products(active_only=active_only)


def list_inventory_categories():
    return {"ok": True, "rows": list_categories()}


def list_inventory_vendors():
    return {"ok": True, "rows": list_vendors()}


def list_product_movements(product_id=None, limit: int = 50):
    rows = list_inventory_movements(product_id=product_id or None, limit=limit)
    for row in rows:
        row["name"] = row.get("reason") or row.get("movement_type") or "Stock move"
        row["product_uom_qty"] = abs(float(row.get("qty_delta") or 0))
        row["date"] = row.get("created_at")
        row["location_id_name"] = row.get("reference_type") or "Inventory"
        row["location_dest_id_name"] = "Customer" if float(row.get("qty_delta") or 0) < 0 else "On Hand"
    return {"ok": True, "rows": rows}


def list_product_audit(product_id=None, limit: int = 50):
    return {"ok": True, "rows": list_inventory_audit_logs(product_id=product_id or None, limit=limit)}


def get_inventory_product_detail(product_id: int):
    detail = get_product_detail(int(product_id))
    if not detail:
        return {"ok": False, "error": "product_not_found"}
    product = detail["product"]
    product["default_code"] = product.get("sku")
    product["standard_price"] = product.get("cost_price")
    product["list_price"] = product.get("retail_price")
    product["qty_available"] = product.get("on_hand_qty")
    product["virtual_available"] = product.get("on_hand_qty")
    product["type"] = product.get("product_type")
    product["categ_name"] = product.get("category_name")
    for row in detail.get("movements", []):
        row["name"] = row.get("reason") or row.get("movement_type") or "Stock move"
        row["product_uom_qty"] = abs(float(row.get("qty_delta") or 0))
        row["date"] = row.get("created_at")
        row["location_id_name"] = row.get("reference_type") or "Inventory"
        row["location_dest_id_name"] = "Customer" if float(row.get("qty_delta") or 0) < 0 else "On Hand"
    return {"ok": True, **detail, "product": product}
