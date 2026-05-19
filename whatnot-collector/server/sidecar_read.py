"""
Read-only summaries from the Postgres/Redis sidecar.

These helpers never modify the live SQLite flow. They are meant for safe
verification and gradual rollout of sidecar-backed reads.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import (
    POSTGRES_SIDECAR_DSN,
    POSTGRES_SIDECAR_ENABLED,
    POSTGRES_SIDECAR_SCHEMA,
    REDIS_PREFIX,
    REDIS_URL,
    REDIS_EMBEDDED_STATE_PATH,
)
try:
    import psycopg2
except Exception:  # pragma: no cover
    psycopg2 = None

try:
    import redis
except Exception:  # pragma: no cover
    redis = None


def _pg_available() -> bool:
    return psycopg2 is not None


def _pg_connect():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed")
    return psycopg2.connect(POSTGRES_SIDECAR_DSN)


def _embedded_redis_url() -> str | None:
    path = Path(REDIS_EMBEDDED_STATE_PATH)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return str(payload.get("url") or "").strip() or None
    except Exception:
        return None


def _redis_client():
    if redis is None:
        return None
    for url in (_embedded_redis_url(), REDIS_URL):
        if not url:
            continue
        try:
            client = redis.Redis.from_url(url, decode_responses=True)
            client.ping()
            return client
        except Exception:
            continue
    return None


def sidecar_status() -> dict:
    redis_client = _redis_client()
    pg_ok = False
    if _pg_available():
        try:
            with _pg_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    pg_ok = bool(cur.fetchone())
        except Exception:
            pg_ok = False
    return {
        "postgres_enabled": bool(POSTGRES_SIDECAR_ENABLED),
        "postgres_connected": pg_ok,
        "postgres_schema": POSTGRES_SIDECAR_SCHEMA,
        "redis_connected": redis_client is not None,
        "redis_prefix": REDIS_PREFIX,
        "redis_url": _embedded_redis_url() or REDIS_URL,
    }


def _scalar(cur, query: str, params=None, default=0):
    cur.execute(query, params or ())
    row = cur.fetchone()
    if not row:
        return default
    return row[0] if row[0] is not None else default


def get_overview_summary() -> dict:
    if not _pg_available():
        return {"ok": False, "source": "sidecar", "error": "postgres sidecar disabled"}
    schema = POSTGRES_SIDECAR_SCHEMA
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            summary = {
                "session_count": int(_scalar(cur, f'SELECT COUNT(*) FROM {schema}."company_sessions"')),
                "live_session_count": int(_scalar(cur, f"SELECT COUNT(*) FROM {schema}.company_sessions WHERE status='live'")),
                "auction_result_count": int(_scalar(cur, f'SELECT COUNT(*) FROM {schema}."auction_results"')),
                "sale_order_count": int(_scalar(cur, f'SELECT COUNT(*) FROM {schema}."sale_orders"')),
                "customer_count": int(_scalar(cur, f'SELECT COUNT(*) FROM {schema}."customers"')),
                "product_count": int(_scalar(cur, f'SELECT COUNT(*) FROM {schema}."products"')),
                "revenue": round(float(_scalar(cur, f'SELECT COALESCE(SUM(total_amount),0) FROM {schema}."sale_orders"')), 2),
                "auction_revenue": round(float(_scalar(cur, f'SELECT COALESCE(SUM(sale_price),0) FROM {schema}."auction_results"')), 2),
                "inventory_cost_value": round(float(_scalar(cur, f'SELECT COALESCE(SUM(on_hand_qty * cost_price),0) FROM {schema}."products"')), 2),
            }
    return {"ok": True, "source": "postgres", "summary": summary}


def get_active_session_summary(account: str = "ynfdeals") -> dict:
    schema = POSTGRES_SIDECAR_SCHEMA
    redis_client = _redis_client()
    live_session = None
    redis_payload = None
    if redis_client is not None:
        raw = redis_client.get(f"{REDIS_PREFIX}:sync:sessions:{account}")
        if raw:
            try:
                redis_payload = json.loads(raw)
                rows = list(redis_payload.get("rows") or [])
                live_session = next((row for row in rows if str(row.get("status") or "").lower() == "live"), None)
            except Exception:
                redis_payload = None
    if live_session is None and _pg_available():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, name, whatnot_account, status, current_lot_number,
                           total_revenue, total_profit, total_lots_sold, started_at, ended_at
                    FROM {schema}.company_sessions
                    WHERE whatnot_account = %s AND status = 'live'
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (account,),
                )
                row = cur.fetchone()
                if row:
                    live_session = {
                        "id": row[0],
                        "name": row[1],
                        "whatnot_account": row[2],
                        "status": row[3],
                        "current_lot_number": row[4],
                        "total_revenue": float(row[5] or 0),
                        "total_profit": float(row[6] or 0),
                        "total_lots_sold": int(row[7] or 0),
                        "started_at": row[8],
                        "ended_at": row[9],
                    }
    return {
        "ok": True,
        "source": "redis" if redis_payload is not None else "postgres",
        "account": account,
        "live_session": live_session,
    }


def get_pending_winners_summary(session_id: int | None = None) -> dict:
    schema = POSTGRES_SIDECAR_SCHEMA
    redis_client = _redis_client()
    rows = None
    if session_id and redis_client is not None:
        raw = redis_client.get(f"{REDIS_PREFIX}:sync:pending_winners:{int(session_id)}")
        if raw:
            try:
                payload = json.loads(raw)
                rows = list(payload.get("rows") or [])
            except Exception:
                rows = None
    summary = {}
    if rows is not None:
        for row in rows:
            status = str(row.get("status") or "unknown").lower()
            summary[status] = summary.get(status, 0) + 1
        return {"ok": True, "source": "redis", "session_id": session_id, "summary": summary, "rows": len(rows)}
    if not _pg_available():
        return {"ok": False, "source": "sidecar", "error": "postgres sidecar disabled"}
    where = ""
    params = []
    if session_id:
        where = "WHERE session_id = %s"
        params.append(int(session_id))
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT status, COUNT(*)
                FROM {schema}.pending_winner_assignments
                {where}
                GROUP BY status
                ORDER BY COUNT(*) DESC
                """,
                tuple(params),
            )
            summary = {str(status): int(count) for status, count in cur.fetchall()}
    return {"ok": True, "source": "postgres", "session_id": session_id, "summary": summary}


def get_auction_results_summary(session_id: int | None = None) -> dict:
    schema = POSTGRES_SIDECAR_SCHEMA
    redis_client = _redis_client()
    if session_id and redis_client is not None:
        raw = redis_client.get(f"{REDIS_PREFIX}:sync:auction_results:{int(session_id)}")
        if raw:
            try:
                payload = json.loads(raw)
                rows = list(payload.get("rows") or [])
                revenue = round(sum(float(row.get("sale_price") or 0) for row in rows), 2)
                profit = round(sum(float(row.get("profit") or 0) for row in rows), 2)
                return {
                    "ok": True,
                    "source": "redis",
                    "session_id": session_id,
                    "summary": {
                        "count": len(rows),
                        "revenue": revenue,
                        "profit": profit,
                    },
                }
            except Exception:
                pass
    if not _pg_available():
        return {"ok": False, "source": "sidecar", "error": "postgres sidecar disabled"}
    where = ""
    params = []
    if session_id:
        where = "WHERE session_id = %s"
        params.append(int(session_id))
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*), COALESCE(SUM(sale_price),0), COALESCE(SUM(profit),0), COALESCE(SUM(fees),0)
                FROM {schema}.auction_results
                {where}
                """,
                tuple(params),
            )
            count, revenue, profit, fees = cur.fetchone()
    return {
        "ok": True,
        "source": "postgres",
        "session_id": session_id,
        "summary": {
            "count": int(count or 0),
            "revenue": round(float(revenue or 0), 2),
            "profit": round(float(profit or 0), 2),
            "fees": round(float(fees or 0), 2),
        },
    }


def get_inventory_summary() -> dict:
    if not _pg_available():
        return {"ok": False, "source": "sidecar", "error": "postgres sidecar disabled"}
    schema = POSTGRES_SIDECAR_SCHEMA
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS total_products,
                    COALESCE(SUM(on_hand_qty * cost_price), 0) AS total_stock_value,
                    SUM(CASE WHEN on_hand_qty <= 0 THEN 1 ELSE 0 END) AS out_of_stock_count,
                    SUM(CASE WHEN on_hand_qty > 0 AND on_hand_qty <= low_stock_threshold THEN 1 ELSE 0 END) AS low_stock_count,
                    SUM(CASE WHEN barcode IS NULL OR barcode = '' THEN 1 ELSE 0 END) AS missing_barcode_count,
                    SUM(CASE WHEN media_url IS NULL OR media_url = '' THEN 1 ELSE 0 END) AS missing_image_count,
                    SUM(CASE WHEN COALESCE(notes_verified, 0) = 0 THEN 1 ELSE 0 END) AS unverified_notes_count
                FROM {schema}.products
                """
            )
            row = cur.fetchone()
    return {
        "ok": True,
        "source": "postgres",
        "summary": {
            "total_products": int(row[0] or 0),
            "total_stock_value": round(float(row[1] or 0), 2),
            "out_of_stock_count": int(row[2] or 0),
            "low_stock_count": int(row[3] or 0),
            "missing_barcode_count": int(row[4] or 0),
            "missing_image_count": int(row[5] or 0),
            "unverified_notes_count": int(row[6] or 0),
        },
    }


def get_parity_report(table_names: list[str] | None = None) -> dict:
    return {
        "ok": False,
        "error": "parity_report_removed",
        "table_names": list(table_names or []),
    }
