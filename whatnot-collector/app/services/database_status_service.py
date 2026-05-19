from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse, urlunparse

from server.config import DB_PATH, POSTGRES_SIDECAR_DSN, POSTGRES_SIDECAR_ENABLED, POSTGRES_SIDECAR_SCHEMA
from server.postgres_cutover import domain_dual_write_enabled, domain_primary_backend, domain_validate_enabled

try:
    import psycopg2
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None


CRITICAL_DOMAINS = (
    "settings",
    "reviews",
    "employees",
    "in_house",
    "inventory_products",
    "inventory_audit",
    "inventory_movements",
    "company_customers",
    "company_sessions",
    "company_lots",
    "company_pending",
    "company_results",
    "company_orders",
    "ingest_streams",
    "ingest_stream_merge",
    "ingest_events",
    "ingest_failed",
    "ingest_lots",
    "ingest_users",
)


def _redact_dsn(dsn: str) -> str:
    raw = str(dsn or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        netloc = parsed.netloc
        if "@" in netloc:
            userinfo, hostinfo = netloc.rsplit("@", 1)
            username = userinfo.split(":", 1)[0]
            netloc = f"{username}:***@{hostinfo}"
        return urlunparse(parsed._replace(netloc=netloc))
    parts = []
    for part in raw.split():
        if part.lower().startswith(("password=", "pass=", "pwd=")):
            key = part.split("=", 1)[0]
            parts.append(f"{key}=***")
        else:
            parts.append(part)
    return " ".join(parts)


def _sqlite_status() -> dict:
    path = Path(DB_PATH)
    return {
        "backend": "sqlite",
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "connected": False,
        "retired": True,
        "error": "sqlite_runtime_retired",
    }


def _postgres_status() -> dict:
    status = {
        "backend": "postgres",
        "enabled": bool(POSTGRES_SIDECAR_ENABLED),
        "driver_installed": psycopg2 is not None,
        "dsn": _redact_dsn(POSTGRES_SIDECAR_DSN),
        "schema": POSTGRES_SIDECAR_SCHEMA,
        "connected": False,
        "schema_ready": False,
        "error": None,
    }
    if psycopg2 is None:
        status["error"] = "psycopg2 is not installed"
        return status
    try:
        with psycopg2.connect(POSTGRES_SIDECAR_DSN, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.execute(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = %s)",
                    (POSTGRES_SIDECAR_SCHEMA,),
                )
                status["schema_ready"] = bool(cur.fetchone()[0])
        status["connected"] = True
    except Exception as exc:
        status["error"] = str(exc)
    return status


def _domain_status() -> list[dict]:
    return [
        {
            "domain": domain,
            "primary": domain_primary_backend(domain),
            "dual_write": domain_dual_write_enabled(domain),
            "validate": domain_validate_enabled(domain),
        }
        for domain in CRITICAL_DOMAINS
    ]


def get_database_status() -> dict:
    sqlite = _sqlite_status()
    postgres = _postgres_status()
    domains = _domain_status()
    postgres_primary_domains = [row["domain"] for row in domains if row["primary"] == "postgres"]
    sqlite_primary_domains = [row["domain"] for row in domains if row["primary"] != "postgres"]
    dual_write_domains = [row["domain"] for row in domains if row["dual_write"]]
    current_primary = "postgres"
    runtime_ok = bool(postgres["connected"] and postgres["schema_ready"] and not sqlite_primary_domains)
    next_safe_step = (
        "SQLite runtime is retired. Keep removing dead SQLite code paths and tooling."
        if runtime_ok
        else "Postgres primary runtime is incomplete. Restore Postgres and promote every critical domain before live operations."
    )
    return {
        "ok": runtime_ok,
        "framework": "FastAPI",
        "safe_mode": not runtime_ok,
        "current_primary": current_primary,
        "sqlite": sqlite,
        "postgres": postgres,
        "domains": domains,
        "summary": {
            "postgres_primary_domains": postgres_primary_domains,
            "sqlite_primary_domains": sqlite_primary_domains,
            "dual_write_domains": dual_write_domains,
            "postgres_available_for_cutover": bool(postgres["driver_installed"] and postgres["connected"] and postgres["schema_ready"]),
            "postgres_primary_complete": not sqlite_primary_domains,
            "fail_closed": not runtime_ok,
            "next_safe_step": next_safe_step,
        },
    }
