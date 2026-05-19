from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.config import DB_PATH, POSTGRES_SIDECAR_SCHEMA
from server.postgres_cutover import _pg_connect, postgres_available


FALLBACK_LOG_PATH = Path(DB_PATH).resolve().parent / "frontend_errors.jsonl"
MAX_TEXT = 12000
MAX_METADATA_TEXT = 20000


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(value: Any, max_len: int = MAX_TEXT) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= max_len:
        return text
    return f"{text[:max_len]}...[truncated {len(text) - max_len} chars]"


def _int_or_none(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except Exception:
        return None


def _payload_to_row(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "event_id": _truncate(payload.get("event_id"), 120) or None,
        "level": _truncate(payload.get("level"), 32) or "error",
        "source": _truncate(payload.get("source"), 64) or "frontend",
        "message": _truncate(payload.get("message"), 4000) or "Unknown frontend error",
        "stack": _truncate(payload.get("stack"), MAX_TEXT),
        "component_stack": _truncate(payload.get("component_stack"), MAX_TEXT),
        "url": _truncate(payload.get("url"), 2048),
        "route": _truncate(payload.get("route"), 512),
        "user_agent": _truncate(payload.get("user_agent"), 1024),
        "api_method": _truncate(payload.get("api_method"), 16),
        "api_url": _truncate(payload.get("api_url"), 2048),
        "api_status": _int_or_none(payload.get("api_status")),
        "api_status_text": _truncate(payload.get("api_status_text"), 128),
        "metadata_json": _truncate(json.dumps(metadata, default=str, sort_keys=True), MAX_METADATA_TEXT),
        "client_ts": _truncate(payload.get("timestamp"), 128),
    }


def ensure_frontend_error_schema() -> bool:
    if not postgres_available():
        return False
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.frontend_errors (
                    id BIGSERIAL PRIMARY KEY,
                    event_id TEXT UNIQUE,
                    level TEXT NOT NULL DEFAULT 'error',
                    source TEXT NOT NULL DEFAULT 'frontend',
                    message TEXT NOT NULL,
                    stack TEXT,
                    component_stack TEXT,
                    url TEXT,
                    route TEXT,
                    user_agent TEXT,
                    api_method TEXT,
                    api_url TEXT,
                    api_status INTEGER,
                    api_status_text TEXT,
                    metadata_json TEXT,
                    client_ts TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_frontend_errors_created_at
                ON {POSTGRES_SIDECAR_SCHEMA}.frontend_errors(created_at DESC)
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_frontend_errors_source
                ON {POSTGRES_SIDECAR_SCHEMA}.frontend_errors(source)
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_frontend_errors_api_status
                ON {POSTGRES_SIDECAR_SCHEMA}.frontend_errors(api_status)
                """
            )
        conn.commit()
    return True


def _write_fallback(row: dict[str, Any]) -> int:
    FALLBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"id": None, "created_at": _utcnow(), **row}
    with FALLBACK_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str, sort_keys=True) + "\n")
    return 0


def record_frontend_error(payload: dict[str, Any]) -> dict[str, Any]:
    row = _payload_to_row(payload if isinstance(payload, dict) else {})
    if not row["message"]:
        row["message"] = "Unknown frontend error"
    try:
        if ensure_frontend_error_schema():
            with _pg_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.frontend_errors (
                            event_id, level, source, message, stack, component_stack, url, route,
                            user_agent, api_method, api_url, api_status, api_status_text,
                            metadata_json, client_ts
                        ) VALUES (
                            %(event_id)s, %(level)s, %(source)s, %(message)s, %(stack)s,
                            %(component_stack)s, %(url)s, %(route)s, %(user_agent)s,
                            %(api_method)s, %(api_url)s, %(api_status)s, %(api_status_text)s,
                            %(metadata_json)s, %(client_ts)s
                        )
                        ON CONFLICT (event_id) DO UPDATE SET
                            level = EXCLUDED.level,
                            source = EXCLUDED.source,
                            message = EXCLUDED.message,
                            stack = EXCLUDED.stack,
                            component_stack = EXCLUDED.component_stack,
                            url = EXCLUDED.url,
                            route = EXCLUDED.route,
                            user_agent = EXCLUDED.user_agent,
                            api_method = EXCLUDED.api_method,
                            api_url = EXCLUDED.api_url,
                            api_status = EXCLUDED.api_status,
                            api_status_text = EXCLUDED.api_status_text,
                            metadata_json = EXCLUDED.metadata_json,
                            client_ts = EXCLUDED.client_ts
                        RETURNING id
                        """,
                        row,
                    )
                    inserted_id = cur.fetchone()[0]
                conn.commit()
            return {"ok": True, "id": inserted_id, "storage": "postgres"}
    except Exception as exc:
        row["metadata_json"] = _truncate(
            json.dumps({"storage_error": str(exc), "metadata_json": row.get("metadata_json")}, default=str),
            MAX_METADATA_TEXT,
        )
    fallback_id = _write_fallback(row)
    return {"ok": True, "id": fallback_id, "storage": "file", "path": str(FALLBACK_LOG_PATH)}


def _parse_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception:
        return {"raw": raw}


def list_frontend_errors(limit: int = 100) -> dict[str, Any]:
    limit = max(1, min(int(limit or 100), 500))
    rows: list[dict[str, Any]] = []
    if postgres_available():
        try:
            ensure_frontend_error_schema()
            with _pg_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT id, event_id, level, source, message, stack, component_stack, url, route,
                               user_agent, api_method, api_url, api_status, api_status_text,
                               metadata_json, client_ts, created_at
                        FROM {POSTGRES_SIDECAR_SCHEMA}.frontend_errors
                        ORDER BY created_at DESC, id DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    cols = [desc[0] for desc in cur.description or []]
                    for raw_row in cur.fetchall():
                        item = dict(zip(cols, raw_row))
                        item["created_at"] = item["created_at"].isoformat() if item.get("created_at") else None
                        item["metadata"] = _parse_metadata(item.pop("metadata_json", None))
                        rows.append(item)
            return {"ok": True, "storage": "postgres", "rows": rows, "count": len(rows)}
        except Exception as exc:
            rows.append({
                "id": None,
                "level": "error",
                "source": "frontend_error_storage",
                "message": f"Unable to read Postgres frontend errors: {exc}",
                "created_at": _utcnow(),
                "metadata": {},
            })

    if FALLBACK_LOG_PATH.exists():
        try:
            lines = FALLBACK_LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
            for line in reversed(lines):
                item = json.loads(line)
                item["metadata"] = _parse_metadata(item.pop("metadata_json", None))
                rows.append(item)
        except Exception as exc:
            rows.append({
                "id": None,
                "level": "error",
                "source": "frontend_error_storage",
                "message": f"Unable to read fallback frontend error log: {exc}",
                "created_at": _utcnow(),
                "metadata": {},
            })
    return {"ok": True, "storage": "file", "rows": rows[:limit], "count": len(rows[:limit])}
