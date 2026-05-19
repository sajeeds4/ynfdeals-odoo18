from __future__ import annotations

import json
import os
from typing import Any

from .company_db import utc_now
from .postgres_cutover import _pg_connect, ensure_wave1_postgres_schema, postgres_available
from .config import POSTGRES_SIDECAR_SCHEMA


TIKTOK_SHOP_SCHEMA = ""

TIKTOK_SHOP_PG_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.tiktok_category_map (
    id BIGSERIAL PRIMARY KEY,
    internal_category_id BIGINT,
    internal_category_name TEXT,
    tiktok_category_id TEXT NOT NULL,
    tiktok_category_name TEXT,
    is_leaf INTEGER NOT NULL DEFAULT 1,
    rules_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tiktok_category_map_internal_id
ON {POSTGRES_SIDECAR_SCHEMA}.tiktok_category_map(internal_category_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tiktok_category_map_internal_name
ON {POSTGRES_SIDECAR_SCHEMA}.tiktok_category_map(LOWER(internal_category_name));

CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.tiktok_product_map (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL UNIQUE,
    internal_sku TEXT,
    tiktok_product_id TEXT NOT NULL,
    tiktok_sku_id TEXT NOT NULL UNIQUE,
    tiktok_shop_id TEXT,
    tiktok_category_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    raw_response TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tiktok_product_map_product_id
ON {POSTGRES_SIDECAR_SCHEMA}.tiktok_product_map(product_id);
CREATE INDEX IF NOT EXISTS idx_tiktok_product_map_tiktok_product_id
ON {POSTGRES_SIDECAR_SCHEMA}.tiktok_product_map(tiktok_product_id);

CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.tiktok_api_logs (
    id BIGSERIAL PRIMARY KEY,
    operation TEXT NOT NULL,
    method TEXT,
    path TEXT,
    status_code INTEGER,
    ok INTEGER NOT NULL DEFAULT 0,
    request_json TEXT,
    response_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tiktok_api_logs_created_at
ON {POSTGRES_SIDECAR_SCHEMA}.tiktok_api_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tiktok_api_logs_operation
ON {POSTGRES_SIDECAR_SCHEMA}.tiktok_api_logs(operation);

CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.tiktok_webhook_events (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT,
    order_id TEXT,
    payload_json TEXT NOT NULL,
    processed INTEGER NOT NULL DEFAULT 0,
    processed_at TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tiktok_webhook_events_order_id
ON {POSTGRES_SIDECAR_SCHEMA}.tiktok_webhook_events(order_id);
CREATE INDEX IF NOT EXISTS idx_tiktok_webhook_events_created_at
ON {POSTGRES_SIDECAR_SCHEMA}.tiktok_webhook_events(created_at DESC);

CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.tiktok_returns (
    id BIGSERIAL PRIMARY KEY,
    return_id TEXT NOT NULL UNIQUE,
    order_id TEXT,
    sale_order_id BIGINT,
    return_status TEXT,
    refund_status TEXT,
    return_type TEXT,
    reason TEXT,
    buyer_note TEXT,
    total_refund_amount NUMERIC NOT NULL DEFAULT 0,
    currency TEXT,
    processed INTEGER NOT NULL DEFAULT 0,
    processed_at TEXT,
    raw_response TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tiktok_returns_order_id
ON {POSTGRES_SIDECAR_SCHEMA}.tiktok_returns(order_id);
CREATE INDEX IF NOT EXISTS idx_tiktok_returns_sale_order_id
ON {POSTGRES_SIDECAR_SCHEMA}.tiktok_returns(sale_order_id);
CREATE INDEX IF NOT EXISTS idx_tiktok_returns_updated_at
ON {POSTGRES_SIDECAR_SCHEMA}.tiktok_returns(updated_at DESC);
"""


def _pg_fetchall_dict(cur):
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in rows]


def _pg_fetchone_dict(cur):
    row = cur.fetchone()
    if row is None:
        return None
    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


def _tiktok_shop_read_prefers_postgres() -> bool:
    return postgres_available()


def _ensure_tiktok_shop_pg_schema() -> None:
    if not postgres_available():
        return
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(TIKTOK_SHOP_PG_SCHEMA)
        conn.commit()


def ensure_tiktok_shop_schema() -> None:
    if not _tiktok_shop_read_prefers_postgres():
        raise RuntimeError("postgres_runtime_required")
    _ensure_tiktok_shop_pg_schema()


def _require_tiktok_shop_postgres() -> None:
    if not _tiktok_shop_read_prefers_postgres():
        raise RuntimeError("postgres_runtime_required")


def _json(value: Any) -> str:
    text = json.dumps(value or {}, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    max_chars = int(os.getenv("TIKTOK_API_LOG_MAX_CHARS", "5000") or 5000)
    if max_chars > 0 and len(text) > max_chars:
        return json.dumps({
            "truncated": True,
            "original_chars": len(text),
            "preview": text[:max_chars],
        }, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return text


def log_tiktok_api(operation: str, method: str, path: str, *, status_code: int | None = None, ok: bool = False, request=None, response=None, error: str | None = None) -> None:
    payload = (
        operation,
        method,
        path,
        int(status_code) if status_code is not None else None,
        1 if ok else 0,
        _json(request),
        _json(response),
        error,
        utc_now(),
    )
    if not postgres_available():
        return
    try:
        _ensure_tiktok_shop_pg_schema()
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.tiktok_api_logs (
                        operation, method, path, status_code, ok,
                        request_json, response_json, error, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    payload,
                )
            conn.commit()
    except Exception:
        return


def upsert_tiktok_category_map(*, internal_category_id=None, internal_category_name=None, tiktok_category_id: str, tiktok_category_name=None, is_leaf=True, rules=None) -> dict[str, Any]:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    now = utc_now()
    clean_internal_id = int(internal_category_id) if internal_category_id not in (None, "") else None
    clean_internal_name = internal_category_name or None
    rules_json = _json(rules or {})
    _ensure_tiktok_shop_pg_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.tiktok_category_map (
                    internal_category_id, internal_category_name, tiktok_category_id,
                    tiktok_category_name, is_leaf, rules_json, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (internal_category_id) DO UPDATE SET
                    internal_category_name = EXCLUDED.internal_category_name,
                    tiktok_category_id = EXCLUDED.tiktok_category_id,
                    tiktok_category_name = EXCLUDED.tiktok_category_name,
                    is_leaf = EXCLUDED.is_leaf,
                    rules_json = EXCLUDED.rules_json,
                    updated_at = EXCLUDED.updated_at
                RETURNING *
                """,
                (
                    clean_internal_id,
                    clean_internal_name,
                    str(tiktok_category_id),
                    tiktok_category_name,
                    1 if is_leaf else 0,
                    rules_json,
                    now,
                    now,
                ),
            )
            row = _pg_fetchone_dict(cur)
        conn.commit()
    if row:
        try:
            row["rules"] = json.loads(row.get("rules_json") or "{}")
        except Exception:
            row["rules"] = {}
    return row


def get_tiktok_category_map(*, internal_category_id=None, internal_category_name=None) -> dict[str, Any] | None:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    row = None
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            if internal_category_id not in (None, ""):
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.tiktok_category_map WHERE internal_category_id = %s",
                    (int(internal_category_id),),
                )
                row = _pg_fetchone_dict(cur)
            if not row and internal_category_name:
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.tiktok_category_map WHERE LOWER(internal_category_name) = LOWER(%s)",
                    (str(internal_category_name),),
                )
                row = _pg_fetchone_dict(cur)
    if row and row.get("rules_json"):
        try:
            row["rules"] = json.loads(row["rules_json"])
        except Exception:
            row["rules"] = {}
    return row


def list_tiktok_category_maps() -> list[dict[str, Any]]:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.tiktok_category_map ORDER BY internal_category_name, id")
            rows = _pg_fetchall_dict(cur)
    for row in rows:
        try:
            row["rules"] = json.loads(row.get("rules_json") or "{}")
        except Exception:
            row["rules"] = {}
    return rows


def upsert_tiktok_product_map(*, product_id: int, internal_sku=None, tiktok_product_id: str, tiktok_sku_id: str, tiktok_shop_id=None, tiktok_category_id=None, status="active", raw_response=None) -> dict[str, Any]:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    now = utc_now()
    raw_json = _json(raw_response or {})
    _ensure_tiktok_shop_pg_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.tiktok_product_map (
                    product_id, internal_sku, tiktok_product_id, tiktok_sku_id,
                    tiktok_shop_id, tiktok_category_id, status, raw_response,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (product_id) DO UPDATE SET
                    internal_sku = EXCLUDED.internal_sku,
                    tiktok_product_id = EXCLUDED.tiktok_product_id,
                    tiktok_sku_id = EXCLUDED.tiktok_sku_id,
                    tiktok_shop_id = EXCLUDED.tiktok_shop_id,
                    tiktok_category_id = EXCLUDED.tiktok_category_id,
                    status = EXCLUDED.status,
                    raw_response = EXCLUDED.raw_response,
                    updated_at = EXCLUDED.updated_at
                RETURNING *
                """,
                (
                    int(product_id),
                    internal_sku,
                    str(tiktok_product_id),
                    str(tiktok_sku_id),
                    tiktok_shop_id,
                    tiktok_category_id,
                    status or "active",
                    raw_json,
                    now,
                    now,
                ),
            )
            row = _pg_fetchone_dict(cur)
        conn.commit()
    return row


def get_tiktok_product_map_by_product(product_id: int) -> dict[str, Any] | None:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.tiktok_product_map WHERE product_id = %s", (int(product_id),))
            return _pg_fetchone_dict(cur)


def get_tiktok_product_map_by_sku(tiktok_sku_id: str) -> dict[str, Any] | None:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.tiktok_product_map WHERE tiktok_sku_id = %s", (str(tiktok_sku_id),))
            return _pg_fetchone_dict(cur)


def list_tiktok_product_maps() -> list[dict[str, Any]]:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT tpm.*, p.name, p.sku, p.barcode, p.on_hand_qty, p.retail_price
                FROM {POSTGRES_SIDECAR_SCHEMA}.tiktok_product_map tpm
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = tpm.product_id
                ORDER BY tpm.updated_at DESC, tpm.id DESC
                """
            )
            return _pg_fetchall_dict(cur)


def delete_tiktok_product_maps(tiktok_product_ids: list[str]) -> int:
    if not tiktok_product_ids:
        return 0
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    ids = [str(i) for i in tiktok_product_ids]
    pg_placeholders = ",".join(f"%s" for _ in ids)
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.tiktok_product_map WHERE tiktok_product_id IN ({pg_placeholders})", ids)
            deleted = cur.rowcount
        conn.commit()
    return deleted


def record_tiktok_webhook_event(event_id: str, event_type: str | None, order_id: str | None, payload: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    now = utc_now()
    payload_json = _json(payload)
    _ensure_tiktok_shop_pg_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.tiktok_webhook_events WHERE event_id = %s", (event_id,))
            existing_pg = _pg_fetchone_dict(cur)
            if existing_pg:
                return False, existing_pg
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.tiktok_webhook_events (
                    event_id, event_type, order_id, payload_json, processed, created_at
                ) VALUES (%s, %s, %s, %s, 0, %s)
                RETURNING *
                """,
                (event_id, event_type, order_id, payload_json, now),
            )
            row = _pg_fetchone_dict(cur)
        conn.commit()
    return True, row


def mark_tiktok_webhook_event(event_id: str, *, processed: bool, error: str | None = None) -> None:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    _ensure_tiktok_shop_pg_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.tiktok_webhook_events
                SET processed = %s, processed_at = %s, error = %s
                WHERE event_id = %s
                """,
                (1 if processed else 0, utc_now() if processed else None, error, event_id),
            )
        conn.commit()


def list_tiktok_webhook_events(limit: int = 100, event_type: str | None = None, processed: bool | None = None) -> list[dict[str, Any]]:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    safe_limit = max(1, min(int(limit or 100), 500))
    where = []
    params: list[Any] = []
    if event_type:
        where.append("event_type = ?")
        params.append(str(event_type))
    if processed is not None:
        where.append("processed = ?")
        params.append(1 if processed else 0)
    sql = "SELECT * FROM tiktok_webhook_events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(safe_limit)
    pg_sql = sql.replace("?", "%s").replace("tiktok_webhook_events", f"{POSTGRES_SIDECAR_SCHEMA}.tiktok_webhook_events")
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(pg_sql, tuple(params))
            rows = _pg_fetchall_dict(cur)
    for row in rows:
        try:
            row["payload"] = json.loads(row.get("payload_json") or "{}")
        except Exception:
            row["payload"] = {}
    return rows


def tiktok_webhook_event_summary() -> dict[str, Any]:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS total_events,
                    SUM(CASE WHEN processed = 1 THEN 1 ELSE 0 END) AS processed_events,
                    SUM(CASE WHEN processed = 0 THEN 1 ELSE 0 END) AS pending_events,
                    SUM(CASE WHEN error IS NOT NULL AND error != '' THEN 1 ELSE 0 END) AS errored_events,
                    MAX(created_at) AS latest_event_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.tiktok_webhook_events
                """
            )
            totals = _pg_fetchone_dict(cur) or {}
            cur.execute(
                f"""
                SELECT event_type, COUNT(*) AS count
                FROM {POSTGRES_SIDECAR_SCHEMA}.tiktok_webhook_events
                GROUP BY event_type
                ORDER BY count DESC, event_type ASC
                """
            )
            by_type = _pg_fetchall_dict(cur)
    return {
        "total_events": int(totals.get("total_events") or 0),
        "processed_events": int(totals.get("processed_events") or 0),
        "pending_events": int(totals.get("pending_events") or 0),
        "errored_events": int(totals.get("errored_events") or 0),
        "latest_event_at": totals.get("latest_event_at"),
        "event_types": by_type,
    }


def upsert_tiktok_return(*, return_id: str, order_id: str | None = None, sale_order_id=None, return_status=None, refund_status=None, return_type=None, reason=None, buyer_note=None, total_refund_amount=0, currency=None, processed=False, processed_at=None, raw_response=None) -> dict[str, Any]:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    now = utc_now()
    clean_return_id = str(return_id or "").strip()
    if not clean_return_id:
        raise ValueError("return_id required")
    clean_sale_order_id = int(sale_order_id) if sale_order_id not in (None, "") else None
    raw_json = _json(raw_response or {})
    amount = float(total_refund_amount or 0)
    payload = (
        clean_return_id,
        str(order_id or "").strip() or None,
        clean_sale_order_id,
        return_status,
        refund_status,
        return_type,
        reason,
        buyer_note,
        amount,
        currency,
        1 if processed else 0,
        processed_at,
        raw_json,
        now,
        now,
    )
    _ensure_tiktok_shop_pg_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.tiktok_returns (
                    return_id, order_id, sale_order_id, return_status, refund_status,
                    return_type, reason, buyer_note, total_refund_amount, currency,
                    processed, processed_at, raw_response, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(return_id) DO UPDATE SET
                    order_id = COALESCE(EXCLUDED.order_id, tiktok_returns.order_id),
                    sale_order_id = COALESCE(EXCLUDED.sale_order_id, tiktok_returns.sale_order_id),
                    return_status = EXCLUDED.return_status,
                    refund_status = EXCLUDED.refund_status,
                    return_type = EXCLUDED.return_type,
                    reason = EXCLUDED.reason,
                    buyer_note = EXCLUDED.buyer_note,
                    total_refund_amount = EXCLUDED.total_refund_amount,
                    currency = EXCLUDED.currency,
                    processed = CASE WHEN tiktok_returns.processed = 1 THEN 1 ELSE EXCLUDED.processed END,
                    processed_at = COALESCE(tiktok_returns.processed_at, EXCLUDED.processed_at),
                    raw_response = EXCLUDED.raw_response,
                    updated_at = EXCLUDED.updated_at
                RETURNING *
                """,
                payload,
            )
            pg_row = _pg_fetchone_dict(cur)
        conn.commit()
    return pg_row


def mark_tiktok_return_processed(return_id: str, sale_order_id=None) -> dict[str, Any] | None:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    now = utc_now()
    clean_return_id = str(return_id or "").strip()
    clean_sale_order_id = int(sale_order_id) if sale_order_id not in (None, "") else None
    _ensure_tiktok_shop_pg_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.tiktok_returns
                SET processed = 1,
                    processed_at = COALESCE(processed_at, %s),
                    sale_order_id = COALESCE(%s, sale_order_id),
                    updated_at = %s
                WHERE return_id = %s
                RETURNING *
                """,
                (now, clean_sale_order_id, now, clean_return_id),
            )
            pg_row = _pg_fetchone_dict(cur)
        conn.commit()
    return pg_row


def mark_tiktok_return_manual(return_id: str, *, sale_order_id=None, note: str | None = None) -> dict[str, Any] | None:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    now = utc_now()
    clean_return_id = str(return_id or "").strip()
    clean_sale_order_id = int(sale_order_id) if sale_order_id not in (None, "") else None
    clean_note = str(note or "").strip() or None
    _ensure_tiktok_shop_pg_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.tiktok_returns
                SET processed = 0,
                    processed_at = NULL,
                    sale_order_id = COALESCE(%s, sale_order_id),
                    buyer_note = COALESCE(%s, buyer_note),
                    updated_at = %s
                WHERE return_id = %s
                RETURNING *
                """,
                (clean_sale_order_id, clean_note, now, clean_return_id),
            )
            pg_row = _pg_fetchone_dict(cur)
        conn.commit()
    return pg_row


def list_tiktok_returns(limit: int = 200, processed: bool | None = None, q: str | None = None) -> list[dict[str, Any]]:
    ensure_tiktok_shop_schema()
    _require_tiktok_shop_postgres()
    safe_limit = max(1, min(int(limit or 200), 1000))
    clauses = []
    params: list[Any] = []
    if processed is not None:
        clauses.append("tr.processed = ?")
        params.append(1 if processed else 0)
    if q:
        ql = f"%{str(q).strip().lower()}%"
        clauses.append("(LOWER(COALESCE(tr.return_id, '')) LIKE ? OR LOWER(COALESCE(tr.order_id, '')) LIKE ? OR LOWER(COALESCE(so.order_number, '')) LIKE ? OR LOWER(COALESCE(so.whatnot_buyer_username, '')) LIKE ?)")
        params.extend([ql, ql, ql, ql])
    sql = """
        SELECT
            tr.*,
            so.order_number,
            so.order_source,
            so.external_order_ref,
            so.whatnot_buyer_username,
            so.ordered_at AS sale_order_ordered_at,
            so.created_at AS sale_order_created_at,
            so.state AS sale_order_state,
            so.fulfillment_status AS sale_order_fulfillment_status,
            so.payment_status AS sale_order_payment_status,
            so.total_amount AS sale_order_total
        FROM tiktok_returns tr
        LEFT JOIN sale_orders so ON so.id = tr.sale_order_id
    """
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY tr.updated_at DESC, tr.id DESC LIMIT ?"
    params.append(safe_limit)
    pg_sql = sql.replace("?", "%s")
    pg_sql = pg_sql.replace(" tiktok_returns tr", f" {POSTGRES_SIDECAR_SCHEMA}.tiktok_returns tr")
    pg_sql = pg_sql.replace(" sale_orders so", f" {POSTGRES_SIDECAR_SCHEMA}.sale_orders so")
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(pg_sql, tuple(params))
            rows = _pg_fetchall_dict(cur)
    for row in rows:
        try:
            row["raw"] = json.loads(row.get("raw_response") or "{}")
        except Exception:
            row["raw"] = {}
    return rows


def list_inventory_movements_for_reference(reference_type: str, reference_id: int) -> list[dict[str, Any]]:
    _require_tiktok_shop_postgres()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_movements
                WHERE reference_type = %s AND reference_id = %s
                ORDER BY id ASC
                """,
                (reference_type, int(reference_id)),
            )
            return _pg_fetchall_dict(cur)
