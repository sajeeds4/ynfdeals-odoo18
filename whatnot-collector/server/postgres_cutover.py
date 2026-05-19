"""
Helpers for gradual PostgreSQL cutover.

Wave 1 and Wave 2 domains can be promoted independently:
- Wave 1: settings, reviews, employees, in-house
- Wave 2: inventory products, inventory audit, inventory movements
"""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.pool import PoolError
    from psycopg2.pool import ThreadedConnectionPool
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None
    sql = None
    PoolError = Exception
    ThreadedConnectionPool = None

from .config import (
    DB_DUAL_WRITE_COMPANY_LOTS,
    DB_DUAL_WRITE_COMPANY_PENDING,
    DB_DUAL_WRITE_COMPANY_RESULTS,
    DB_DUAL_WRITE_COMPANY_ORDERS,
    DB_DUAL_WRITE_COMPANY_CUSTOMERS,
    DB_DUAL_WRITE_COMPANY_SESSIONS,
    DB_DUAL_WRITE_EMPLOYEES,
    DB_DUAL_WRITE_INGEST_EVENTS,
    DB_DUAL_WRITE_INGEST_FAILED,
    DB_DUAL_WRITE_INGEST_LOTS,
    DB_DUAL_WRITE_INGEST_STREAM_MERGE,
    DB_DUAL_WRITE_INGEST_STREAMS,
    DB_DUAL_WRITE_INGEST_USERS,
    DB_DUAL_WRITE_IN_HOUSE,
    DB_DUAL_WRITE_INVENTORY_AUDIT,
    DB_DUAL_WRITE_INVENTORY_MOVEMENTS,
    DB_DUAL_WRITE_INVENTORY_PRODUCTS,
    DB_DUAL_WRITE_ANALYTICS,
    DB_DUAL_WRITE_COMPANY,
    DB_DUAL_WRITE_EVENTS,
    DB_DUAL_WRITE_INVENTORY,
    DB_DUAL_WRITE_REVIEWS,
    DB_DUAL_WRITE_SETTINGS,
    DB_PRIMARY_DOMAIN_ANALYTICS,
    DB_PRIMARY_DOMAIN_COMPANY,
    DB_PRIMARY_DOMAIN_EVENTS,
    DB_PRIMARY_COMPANY_LOTS,
    DB_PRIMARY_COMPANY_PENDING,
    DB_PRIMARY_COMPANY_RESULTS,
    DB_PRIMARY_COMPANY_ORDERS,
    DB_PRIMARY_COMPANY_CUSTOMERS,
    DB_PRIMARY_COMPANY_SESSIONS,
    DB_PRIMARY_DOMAIN_EMPLOYEES,
    DB_PRIMARY_DOMAIN_INVENTORY,
    DB_PRIMARY_INGEST_EVENTS,
    DB_PRIMARY_INGEST_FAILED,
    DB_PRIMARY_INGEST_LOTS,
    DB_PRIMARY_INGEST_STREAM_MERGE,
    DB_PRIMARY_INGEST_STREAMS,
    DB_PRIMARY_INGEST_USERS,
    DB_PRIMARY_DOMAIN_IN_HOUSE,
    DB_PRIMARY_INVENTORY_AUDIT,
    DB_PRIMARY_INVENTORY_MOVEMENTS,
    DB_PRIMARY_INVENTORY_PRODUCTS,
    DB_PRIMARY_DOMAIN_REVIEWS,
    DB_PRIMARY_DOMAIN_SETTINGS,
    DB_VALIDATE_WRITE_COMPANY_LOTS,
    DB_VALIDATE_WRITE_COMPANY_PENDING,
    DB_VALIDATE_WRITE_COMPANY_RESULTS,
    DB_VALIDATE_WRITE_COMPANY_ORDERS,
    DB_VALIDATE_WRITE_COMPANY_CUSTOMERS,
    DB_VALIDATE_WRITE_COMPANY_SESSIONS,
    DB_VALIDATE_WRITE_EMPLOYEES,
    DB_VALIDATE_WRITE_INGEST_EVENTS,
    DB_VALIDATE_WRITE_INGEST_FAILED,
    DB_VALIDATE_WRITE_INGEST_LOTS,
    DB_VALIDATE_WRITE_INGEST_STREAM_MERGE,
    DB_VALIDATE_WRITE_INGEST_STREAMS,
    DB_VALIDATE_WRITE_INGEST_USERS,
    DB_VALIDATE_WRITE_IN_HOUSE,
    DB_VALIDATE_WRITE_INVENTORY_AUDIT,
    DB_VALIDATE_WRITE_INVENTORY_MOVEMENTS,
    DB_VALIDATE_WRITE_INVENTORY_PRODUCTS,
    DB_VALIDATE_WRITE_ANALYTICS,
    DB_VALIDATE_WRITE_COMPANY,
    DB_VALIDATE_WRITE_EVENTS,
    DB_VALIDATE_WRITE_INVENTORY,
    DB_VALIDATE_WRITE_REVIEWS,
    DB_VALIDATE_WRITE_SETTINGS,
    POSTGRES_CUTOVER_MISMATCH_LOG_PATH,
    POSTGRES_SIDECAR_ENABLED,
    POSTGRES_SIDECAR_DSN,
    POSTGRES_SIDECAR_SCHEMA,
)

_MISMATCH_LOG_ENABLED = os.getenv("POSTGRES_CUTOVER_MISMATCH_LOG_ENABLED", "0") == "1"
_MISMATCH_LOG_MAX_BYTES = int(os.getenv("POSTGRES_CUTOVER_MISMATCH_LOG_MAX_BYTES", str(25 * 1024 * 1024)))


_DOMAIN_FLAGS = {
    "settings": {
        "primary": lambda: DB_PRIMARY_DOMAIN_SETTINGS,
        "dual_write": lambda: DB_DUAL_WRITE_SETTINGS,
        "validate": lambda: DB_VALIDATE_WRITE_SETTINGS,
    },
    "reviews": {
        "primary": lambda: DB_PRIMARY_DOMAIN_REVIEWS,
        "dual_write": lambda: DB_DUAL_WRITE_REVIEWS,
        "validate": lambda: DB_VALIDATE_WRITE_REVIEWS,
    },
    "employees": {
        "primary": lambda: DB_PRIMARY_DOMAIN_EMPLOYEES,
        "dual_write": lambda: DB_DUAL_WRITE_EMPLOYEES,
        "validate": lambda: DB_VALIDATE_WRITE_EMPLOYEES,
    },
    "in_house": {
        "primary": lambda: DB_PRIMARY_DOMAIN_IN_HOUSE,
        "dual_write": lambda: DB_DUAL_WRITE_IN_HOUSE,
        "validate": lambda: DB_VALIDATE_WRITE_IN_HOUSE,
    },
    "company": {
        "primary": lambda: DB_PRIMARY_DOMAIN_COMPANY,
        "dual_write": lambda: DB_DUAL_WRITE_COMPANY,
        "validate": lambda: DB_VALIDATE_WRITE_COMPANY,
    },
    "company_customers": {
        "primary": lambda: DB_PRIMARY_COMPANY_CUSTOMERS,
        "dual_write": lambda: DB_DUAL_WRITE_COMPANY_CUSTOMERS,
        "validate": lambda: DB_VALIDATE_WRITE_COMPANY_CUSTOMERS,
    },
    "company_sessions": {
        "primary": lambda: DB_PRIMARY_COMPANY_SESSIONS,
        "dual_write": lambda: DB_DUAL_WRITE_COMPANY_SESSIONS,
        "validate": lambda: DB_VALIDATE_WRITE_COMPANY_SESSIONS,
    },
    "company_lots": {
        "primary": lambda: DB_PRIMARY_COMPANY_LOTS,
        "dual_write": lambda: DB_DUAL_WRITE_COMPANY_LOTS,
        "validate": lambda: DB_VALIDATE_WRITE_COMPANY_LOTS,
    },
    "company_pending": {
        "primary": lambda: DB_PRIMARY_COMPANY_PENDING,
        "dual_write": lambda: DB_DUAL_WRITE_COMPANY_PENDING,
        "validate": lambda: DB_VALIDATE_WRITE_COMPANY_PENDING,
    },
    "company_results": {
        "primary": lambda: DB_PRIMARY_COMPANY_RESULTS,
        "dual_write": lambda: DB_DUAL_WRITE_COMPANY_RESULTS,
        "validate": lambda: DB_VALIDATE_WRITE_COMPANY_RESULTS,
    },
    "company_orders": {
        "primary": lambda: DB_PRIMARY_COMPANY_ORDERS,
        "dual_write": lambda: DB_DUAL_WRITE_COMPANY_ORDERS,
        "validate": lambda: DB_VALIDATE_WRITE_COMPANY_ORDERS,
    },
    "ingest_streams": {
        "primary": lambda: DB_PRIMARY_INGEST_STREAMS,
        "dual_write": lambda: DB_DUAL_WRITE_INGEST_STREAMS,
        "validate": lambda: DB_VALIDATE_WRITE_INGEST_STREAMS,
    },
    "ingest_stream_merge": {
        "primary": lambda: DB_PRIMARY_INGEST_STREAM_MERGE,
        "dual_write": lambda: DB_DUAL_WRITE_INGEST_STREAM_MERGE,
        "validate": lambda: DB_VALIDATE_WRITE_INGEST_STREAM_MERGE,
    },
    "ingest_events": {
        "primary": lambda: DB_PRIMARY_INGEST_EVENTS,
        "dual_write": lambda: DB_DUAL_WRITE_INGEST_EVENTS,
        "validate": lambda: DB_VALIDATE_WRITE_INGEST_EVENTS,
    },
    "ingest_failed": {
        "primary": lambda: DB_PRIMARY_INGEST_FAILED,
        "dual_write": lambda: DB_DUAL_WRITE_INGEST_FAILED,
        "validate": lambda: DB_VALIDATE_WRITE_INGEST_FAILED,
    },
    "ingest_lots": {
        "primary": lambda: DB_PRIMARY_INGEST_LOTS,
        "dual_write": lambda: DB_DUAL_WRITE_INGEST_LOTS,
        "validate": lambda: DB_VALIDATE_WRITE_INGEST_LOTS,
    },
    "ingest_users": {
        "primary": lambda: DB_PRIMARY_INGEST_USERS,
        "dual_write": lambda: DB_DUAL_WRITE_INGEST_USERS,
        "validate": lambda: DB_VALIDATE_WRITE_INGEST_USERS,
    },
    "events": {
        "primary": lambda: DB_PRIMARY_DOMAIN_EVENTS,
        "dual_write": lambda: DB_DUAL_WRITE_EVENTS,
        "validate": lambda: DB_VALIDATE_WRITE_EVENTS,
    },
    "inventory": {
        "primary": lambda: DB_PRIMARY_DOMAIN_INVENTORY,
        "dual_write": lambda: DB_DUAL_WRITE_INVENTORY,
        "validate": lambda: DB_VALIDATE_WRITE_INVENTORY,
    },
    "inventory_products": {
        "primary": lambda: DB_PRIMARY_INVENTORY_PRODUCTS,
        "dual_write": lambda: DB_DUAL_WRITE_INVENTORY_PRODUCTS,
        "validate": lambda: DB_VALIDATE_WRITE_INVENTORY_PRODUCTS,
    },
    "inventory_audit": {
        "primary": lambda: DB_PRIMARY_INVENTORY_AUDIT,
        "dual_write": lambda: DB_DUAL_WRITE_INVENTORY_AUDIT,
        "validate": lambda: DB_VALIDATE_WRITE_INVENTORY_AUDIT,
    },
    "inventory_movements": {
        "primary": lambda: DB_PRIMARY_INVENTORY_MOVEMENTS,
        "dual_write": lambda: DB_DUAL_WRITE_INVENTORY_MOVEMENTS,
        "validate": lambda: DB_VALIDATE_WRITE_INVENTORY_MOVEMENTS,
    },
    "analytics": {
        "primary": lambda: DB_PRIMARY_DOMAIN_ANALYTICS,
        "dual_write": lambda: DB_DUAL_WRITE_ANALYTICS,
        "validate": lambda: DB_VALIDATE_WRITE_ANALYTICS,
    },
    "shop_scraper": {
        "primary": lambda: "postgres",
        "dual_write": lambda: False,
        "validate": lambda: True,
    },
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def domain_primary_backend(domain: str) -> str:
    if not POSTGRES_SIDECAR_ENABLED:
        return "sqlite"
    cfg = _DOMAIN_FLAGS.get(str(domain or "").strip().lower())
    if not cfg:
        return "sqlite"
    value = str(cfg["primary"]() or "sqlite").strip().lower()
    return value if value in {"sqlite", "postgres"} else "sqlite"


def domain_dual_write_enabled(domain: str) -> bool:
    return False


def domain_validate_enabled(domain: str) -> bool:
    cfg = _DOMAIN_FLAGS.get(str(domain or "").strip().lower())
    return bool(cfg and cfg["validate"]())


def postgres_available() -> bool:
    return POSTGRES_SIDECAR_ENABLED and psycopg2 is not None


_PG_POOL = None
_PG_POOL_LOCK = threading.Lock()
_PG_POOL_MIN = max(1, int(os.getenv("POSTGRES_POOL_MIN", "1") or "1"))
_PG_POOL_MAX = max(_PG_POOL_MIN, int(os.getenv("POSTGRES_POOL_MAX", "24") or "24"))


class _PooledPgConnection:
    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn
        self._closed = False

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._conn.rollback()
        except Exception:
            pass
        try:
            self._pool.putconn(self._conn)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass


def _pg_pool():
    global _PG_POOL
    if ThreadedConnectionPool is None:
        raise RuntimeError("psycopg2 pool is not available")
    if _PG_POOL is None:
        with _PG_POOL_LOCK:
            if _PG_POOL is None:
                _PG_POOL = ThreadedConnectionPool(_PG_POOL_MIN, _PG_POOL_MAX, POSTGRES_SIDECAR_DSN)
    return _PG_POOL


def _reset_pg_pool():
    global _PG_POOL
    with _PG_POOL_LOCK:
        pool = _PG_POOL
        _PG_POOL = None
        if pool is not None:
            try:
                pool.closeall()
            except Exception:
                pass


def _pg_connect():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed")
    last_error = None
    for attempt in range(3):
        pool = _pg_pool()
        try:
            return _PooledPgConnection(pool, pool.getconn())
        except PoolError as exc:
            last_error = exc
            if "connection pool exhausted" not in str(exc).lower():
                raise
            _reset_pg_pool()
            time.sleep(0.05 * (attempt + 1))
    raise RuntimeError(f"postgres connection pool exhausted after recovery attempts: {last_error}")


_WAVE1_SEQUENCE_TABLES = (
    "customer_reviews",
    "customers",
    "company_sessions",
    "company_lots",
    "pending_winner_assignments",
    "pending_winner_assignment_items",
    "auction_results",
    "buyer_groups",
    "sale_orders",
    "sale_order_lines",
    "employee_accounts",
    "employee_pos_tokens",
    "in_house_sales",
    "in_house_orders",
    "in_house_order_lines",
)

_WAVE2_SEQUENCE_TABLES = (
    "products",
    "inventory_audit_log",
    "inventory_movements",
    "streams",
    "events",
    "failed_ingests",
    "lots",
    "users",
)

_WAVE1_UNIQUE_INDEXES = {
    "customer_reviews": (("review_key",),),
    "customers": (("whatnot_username",),),
    "company_lots": (("session_id", "lot_number"),),
    "pending_winner_assignments": (("source_event_id",),),
    "auction_results": (("source_event_id",),),
    "buyer_groups": (("session_id", "buyer_username"),),
    "sale_orders": (("order_number",),),
    "employee_accounts": (("name_key",),),
    "employee_pos_tokens": (("token",),),
    "failed_ingests": (("source_event_id",),),
    "users": (("username",),),
}


def _fetchone_dict_pg(cur):
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip((desc[0] for desc in cur.description), row))


@lru_cache(maxsize=1)
def ensure_wave1_postgres_schema() -> bool:
    if not postgres_available():
        return False
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {}.customer_identities (
                        id BIGSERIAL PRIMARY KEY,
                        customer_id BIGINT NOT NULL,
                        platform TEXT NOT NULL,
                        platform_user_id TEXT,
                        username TEXT,
                        display_name TEXT,
                        email TEXT,
                        phone TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                ).format(sql.Identifier(POSTGRES_SIDECAR_SCHEMA))
            )
            cur.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS customer_identities_customer_id_idx ON {}.customer_identities (customer_id)").format(
                    sql.Identifier(POSTGRES_SIDECAR_SCHEMA)
                )
            )
            cur.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS customer_identities_platform_idx ON {}.customer_identities (platform)").format(
                    sql.Identifier(POSTGRES_SIDECAR_SCHEMA)
                )
            )
            cur.execute(
                sql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS customer_identities_platform_user_id_uniq ON {}.customer_identities (platform, platform_user_id)").format(
                    sql.Identifier(POSTGRES_SIDECAR_SCHEMA)
                )
            )
            cur.execute(
                sql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS customer_identities_platform_username_uniq ON {}.customer_identities (platform, username)").format(
                    sql.Identifier(POSTGRES_SIDECAR_SCHEMA)
                )
            )
            for table_name in (_WAVE1_SEQUENCE_TABLES + _WAVE2_SEQUENCE_TABLES):
                seq_name = f"{table_name}_id_seq"
                cur.execute(
                    sql.SQL("CREATE SEQUENCE IF NOT EXISTS {}.{}").format(
                        sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                        sql.Identifier(seq_name),
                    )
                )
                cur.execute(
                    sql.SQL("ALTER TABLE {}.{} ALTER COLUMN id SET DEFAULT nextval(%s)").format(
                        sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                        sql.Identifier(table_name),
                    ),
                    (f"{POSTGRES_SIDECAR_SCHEMA}.{seq_name}",),
                )
                cur.execute(
                    sql.SQL(
                        "SELECT setval(%s, COALESCE((SELECT MAX(id) FROM {}.{}), 0) + 1, false)"
                    ).format(
                        sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                        sql.Identifier(table_name),
                    ),
                    (f"{POSTGRES_SIDECAR_SCHEMA}.{seq_name}",),
                )
            for table_name, indexes in _WAVE1_UNIQUE_INDEXES.items():
                for columns in indexes:
                    index_name = f"{table_name}_{'_'.join(columns)}_uniq"
                    cur.execute(
                        sql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS {} ON {}.{} ({})").format(
                            sql.Identifier(index_name),
                            sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                            sql.Identifier(table_name),
                            sql.SQL(", ").join(sql.Identifier(col) for col in columns),
                        )
                    )
            for column_name in ("raw_cost", "cost_plus_12", "cost_plus_20"):
                cur.execute(
                    sql.SQL("ALTER TABLE {}.products ADD COLUMN IF NOT EXISTS {} DOUBLE PRECISION NOT NULL DEFAULT 0").format(
                        sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                        sql.Identifier(column_name),
                    )
                )
            for column_name in ("size_oz", "size_ml", "volume_oz", "volume_ml"):
                cur.execute(
                    sql.SQL("ALTER TABLE {}.products ADD COLUMN IF NOT EXISTS {} DOUBLE PRECISION").format(
                        sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                        sql.Identifier(column_name),
                    )
                )
            text_columns = (
                "similar_to", "image_gallery_urls", "source_fragrantica_url", "source_jomashop_url",
                "source_parfumo_url", "source_official_url",
                "tiktok_title", "tiktok_category_id", "tiktok_category_name", "tiktok_brand",
                "tiktok_search_keywords", "tiktok_image_urls", "tiktok_pack_type", "tiktok_scent",
                "tiktok_region_of_origin", "tiktok_product_form", "tiktok_edition",
                "tiktok_contains_alcohol_or_aerosol", "tiktok_manufacturer", "tiktok_shelf_life",
                "tiktok_inactive_ingredients", "tiktok_age_group", "tiktok_item_name",
                "tiktok_feature", "tiktok_fragrance_concentration", "tiktok_material_type_free",
                "tiktok_ingredients", "tiktok_container_type", "tiktok_allergen_information",
                "tiktok_ingredient_feature", "tiktok_volume", "tiktok_description",
                "tiktok_highlights", "tiktok_seller_sku", "tiktok_ean",
                "tiktok_product_identifier_code_type", "tiktok_ca_prop_65_repro_chems",
                "tiktok_ca_prop_65_carcinogens", "tiktok_flammable_liquid", "tiktok_aerosols",
                "tiktok_dangerous_goods_or_hazardous_materials", "tiktok_environmental_feature",
                "tiktok_sds_file_path",
            )
            for column_name in text_columns:
                cur.execute(
                    sql.SQL("ALTER TABLE {}.products ADD COLUMN IF NOT EXISTS {} TEXT").format(
                        sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                        sql.Identifier(column_name),
                    )
                )
            for column_name in (
                "tiktok_quantity", "tiktok_retail_price", "tiktok_package_weight_oz",
                "tiktok_package_length_in", "tiktok_package_width_in", "tiktok_package_height_in",
            ):
                cur.execute(
                    sql.SQL("ALTER TABLE {}.products ADD COLUMN IF NOT EXISTS {} DOUBLE PRECISION").format(
                        sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                        sql.Identifier(column_name),
                    )
                )
        conn.commit()
    return True


@lru_cache(maxsize=128)
def _table_columns(table_name: str) -> tuple[str, ...]:
    if not postgres_available():
        raise RuntimeError("postgres_unavailable")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position ASC
                """,
                (POSTGRES_SIDECAR_SCHEMA, str(table_name)),
            )
            columns = tuple(str(row[0]) for row in cur.fetchall())
    if not columns:
        raise RuntimeError(f"unknown_postgres_table:{table_name}")
    return columns


def _log_mismatch(domain: str, operation: str, table_name: str, identifier, details: dict) -> None:
    if not _MISMATCH_LOG_ENABLED:
        return
    try:
        path = Path(POSTGRES_CUTOVER_MISMATCH_LOG_PATH)
        if path.exists() and path.stat().st_size >= _MISMATCH_LOG_MAX_BYTES:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": _utcnow(),
            "domain": domain,
            "operation": operation,
            "table_name": table_name,
            "identifier": identifier,
            "details": details,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        return


def log_cutover_event(domain: str, operation: str, table_name: str, identifier, details: dict) -> None:
    _log_mismatch(domain, operation, table_name, identifier, details)


def _normalize_value(value):
    if isinstance(value, memoryview):
        value = bytes(value)
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except Exception:
            value = bytes(value)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, str)) or value is None:
        return value
    if isinstance(value, float):
        return round(value, 6)
    return str(value)


def _pg_only_company_validation_report(recent_limit: int = 100) -> dict:
    ensure_wave1_postgres_schema()
    with _pg_connect() as pg_conn:
        with pg_conn.cursor() as cur:
            counts = {}
            for label, table_name in (
                ("customers", "customers"),
                ("company_sessions", "company_sessions"),
                ("company_lots", "company_lots"),
                ("company_pending_assignments", "pending_winner_assignments"),
                ("company_pending_items", "pending_winner_assignment_items"),
                ("company_results", "auction_results"),
                ("company_orders", "sale_orders"),
                ("company_order_lines", "sale_order_lines"),
            ):
                cur.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                        sql.Identifier(POSTGRES_SIDECAR_SCHEMA),
                        sql.Identifier(table_name),
                    )
                )
                counts[label] = int((cur.fetchone() or [0])[0] or 0)
    return {
        "ok": True,
        "mode": "postgres_only",
        "recent_limit": int(recent_limit),
        "counts": counts,
        "manual_sqlite_compare_available": False,
        "note": "SQLite comparison has been retired; this report validates PostgreSQL only.",
    }


def inventory_validation_report(recent_limit: int = 100) -> dict:
    return {"ok": False, "retired": True, "error": "sqlite_validation_retired"}



def company_validation_report(recent_limit: int = 100, *, db_path: str | None = None, sqlite_compare: bool = False) -> dict:
    if not postgres_available():
        return {"ok": False, "error": "postgres_unavailable"}
    if sqlite_compare or db_path:
        raise RuntimeError("company_validation_sqlite_compare_retired")
    return _pg_only_company_validation_report(recent_limit=recent_limit)


@contextmanager
def pg_domain_tx(domain: str, operation: str):
    ensure_wave1_postgres_schema()
    conn = _pg_connect()
    try:
        yield conn, conn.cursor()
        conn.commit()
    except Exception as exc:
        conn.rollback()
        _log_mismatch(domain, "pg_primary_failed", operation, None, {"error": str(exc)})
        raise
    finally:
        conn.close()
