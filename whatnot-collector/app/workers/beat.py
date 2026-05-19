from app.workers.celery_app import celery_app
from app.config import settings

celery_app.conf.beat_schedule = {
    "capture-runtime-diagnostics": {
        "task": "app.tasks.default.capture_runtime_diagnostics",
        "schedule": 300.0,
    },
    "capture-current-session-stats": {
        "task": "app.tasks.default.capture_current_session_stats",
        "schedule": 30.0,
    },
    "refresh-inventory-snapshot": {
        "task": "app.tasks.business.refresh_inventory_snapshot",
        "schedule": 120.0,
        "options": {"queue": settings.celery_business_queue},
    },
    "refresh-sales-orders-snapshot": {
        "task": "app.tasks.business.refresh_sales_orders_snapshot",
        "schedule": 300.0,
        "options": {"queue": settings.celery_business_queue},
    },
    "refresh-auction-results-snapshot": {
        "task": "app.tasks.business.refresh_auction_results_snapshot",
        "schedule": 300.0,
        "options": {"queue": settings.celery_business_queue},
    },
}
