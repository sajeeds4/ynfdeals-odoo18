from __future__ import annotations

from datetime import datetime, timezone

from app.core.redis import acquire_lock


def _claim_enqueue(name: str, ttl_seconds: int = 20) -> bool:
    try:
        owner = datetime.now(timezone.utc).isoformat()
        return acquire_lock(f"enqueue:{name}", owner=owner, ttl_seconds=ttl_seconds)
    except Exception:
        return True


def enqueue_inventory_refresh(product_id: int | None = None) -> None:
    try:
        from app.tasks.business_tasks import (
            refresh_inventory_activity,
            refresh_inventory_product,
            refresh_inventory_snapshot,
        )

        if _claim_enqueue("inventory_snapshot"):
            refresh_inventory_snapshot.delay()
        activity_key = "inventory_activity:all" if product_id is None else f"inventory_activity:{int(product_id)}"
        if _claim_enqueue(activity_key):
            refresh_inventory_activity.delay(product_id=product_id)
        if product_id and _claim_enqueue(f"inventory_product:{int(product_id)}"):
            refresh_inventory_product.delay(int(product_id))
    except Exception:
        pass


def enqueue_sales_order_refresh(session_id: int | None = None, customer_id: int | None = None) -> None:
    try:
        from app.tasks.business_tasks import refresh_customer_orders_snapshot, refresh_sales_orders_snapshot

        sales_key = "sales_orders:current" if session_id is None else f"sales_orders:{int(session_id)}"
        if _claim_enqueue(sales_key, ttl_seconds=30):
            refresh_sales_orders_snapshot.delay(session_id=session_id)
        if customer_id and _claim_enqueue(f"customer_orders:{int(customer_id)}", ttl_seconds=30):
            refresh_customer_orders_snapshot.delay(int(customer_id))
    except Exception:
        pass


def enqueue_auction_results_refresh(session_id: int | None = None) -> None:
    try:
        from app.tasks.business_tasks import refresh_auction_results_snapshot

        auction_key = "auction_results:current" if session_id is None else f"auction_results:{int(session_id)}"
        if _claim_enqueue(auction_key, ttl_seconds=30):
            refresh_auction_results_snapshot.delay(session_id=session_id)
    except Exception:
        pass
