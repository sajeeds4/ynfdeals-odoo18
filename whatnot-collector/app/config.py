from __future__ import annotations

import os
from dataclasses import dataclass

from server import config as legacy


@dataclass(frozen=True)
class AppSettings:
    app_name: str = os.getenv("APP_NAME", "Whatnot Runtime API")
    app_env: str = os.getenv("APP_ENV", "development")
    api_host: str = os.getenv("FASTAPI_HOST", legacy.HOST)
    api_port: int = int(os.getenv("FASTAPI_PORT", "8090"))
    api_reload: bool = os.getenv("FASTAPI_RELOAD", "0") == "1"
    api_prefix: str = os.getenv("FASTAPI_PREFIX", "/api/v2")
    redis_url: str = legacy.REDIS_URL
    redis_enabled: bool = legacy.REDIS_ENABLED
    postgres_dsn: str = legacy.POSTGRES_SIDECAR_DSN
    postgres_schema: str = legacy.POSTGRES_SIDECAR_SCHEMA
    celery_broker_url: str = os.getenv("CELERY_BROKER_URL", legacy.REDIS_URL)
    celery_result_backend: str = os.getenv("CELERY_RESULT_BACKEND", legacy.REDIS_URL)
    celery_default_queue: str = os.getenv("CELERY_DEFAULT_QUEUE", "default")
    celery_analytics_queue: str = os.getenv("CELERY_ANALYTICS_QUEUE", "analytics")
    celery_ingest_queue: str = os.getenv("CELERY_INGEST_QUEUE", "ingest_support")
    celery_business_queue: str = os.getenv("CELERY_BUSINESS_QUEUE", "business")
    legacy_bridge_enabled: bool = os.getenv("FASTAPI_LEGACY_BRIDGE_ENABLED", "0") == "1"
    legacy_bridge_host: str = os.getenv("FASTAPI_LEGACY_BRIDGE_HOST", "127.0.0.1")
    legacy_bridge_port: int = int(os.getenv("FASTAPI_LEGACY_BRIDGE_PORT", str(legacy.PORT + 1)))
    redis_key_prefix: str = os.getenv("REDIS_KEY_PREFIX", "whatnot:runtime")
    medusa_integration_enabled: bool = os.getenv("MEDUSA_INTEGRATION_ENABLED", "0") == "1"
    medusa_base_url: str = os.getenv("MEDUSA_BASE_URL", "http://127.0.0.1:9000").rstrip("/")
    medusa_admin_api_token: str = os.getenv("MEDUSA_ADMIN_API_TOKEN", "")
    medusa_integration_secret: str = os.getenv("MEDUSA_INTEGRATION_SECRET", "")
    medusa_store_currency_code: str = os.getenv("MEDUSA_STORE_CURRENCY_CODE", "usd").lower()
    medusa_sync_page_size: int = int(os.getenv("MEDUSA_SYNC_PAGE_SIZE", "100"))
    medusa_stock_location_name: str = os.getenv("MEDUSA_STOCK_LOCATION_NAME", "YNF Operations Inventory")


settings = AppSettings()
