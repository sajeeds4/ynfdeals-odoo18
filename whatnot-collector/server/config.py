"""
Configuration module — loads .env and exports all settings.
All paths are resolved relative to the project root, never hardcoded.
"""

import ipaddress
import os
import socket
from urllib.parse import urlparse

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env(path):
    """Minimal .env loader (no external dependency for the server)."""
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        return


ENV_PATH = os.getenv("DASHBOARD_ENV", os.path.join(_PROJECT_ROOT, ".env"))
_load_env(ENV_PATH)

# --- Database ---
DB_PATH = os.getenv("DB_PATH", os.path.join(_PROJECT_ROOT, "data", "whatnot.db"))

# --- Server ---
HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
PORT = int(os.getenv("DASHBOARD_PORT", "8088"))

# --- Session ---
WHATNOT_SESSION_ID = os.getenv("WHATNOT_SESSION_ID")

# --- Shared State Paths ---
SHARED_SCAN_STATE_PATH = os.getenv(
    "SHARED_SCAN_STATE_PATH",
    os.path.join(os.path.dirname(DB_PATH), "shared_scan_state.json"),
)
LIVE_COLLECTOR_STATE_PATH = os.getenv(
    "LIVE_COLLECTOR_STATE_PATH",
    os.path.join(os.path.dirname(DB_PATH), "collector_state.json"),
)
COLLECTOR_STATE_PATH = LIVE_COLLECTOR_STATE_PATH
SPECTATOR_STATE_PATH = os.getenv(
    "SPECTATOR_STATE_PATH",
    os.path.join(os.path.dirname(DB_PATH), "spectator_state.json"),
)
PRIORITY_SPECTATOR_STATE_PATH = os.getenv(
    "PRIORITY_SPECTATOR_STATE_PATH",
    os.path.join(os.path.dirname(DB_PATH), "priority_spectator_state.json"),
)
MAX_SPECTATOR_STREAMS = min(int(os.getenv("MAX_SPECTATOR_STREAMS", "10")), 20)
SPECTATOR_TABS_PER_WORKER = max(1, min(int(os.getenv("SPECTATOR_TABS_PER_WORKER", "4")), 8))
PRIORITY_SPECTATOR_MAX_STREAMS = max(1, min(int(os.getenv("PRIORITY_SPECTATOR_MAX_STREAMS", "3")), 5))
SPECTATOR_STARTS_ENABLED = os.getenv("SPECTATOR_STARTS_ENABLED", "0") == "1"
LIVE_COLLECTOR_LOG_PATH = os.getenv(
    "LIVE_COLLECTOR_LOG_PATH",
    os.getenv("COLLECTOR_LOG_PATH", os.path.join(os.path.dirname(DB_PATH), "collector.log")),
)
COLLECTOR_LOG_PATH = LIVE_COLLECTOR_LOG_PATH
LIVE_COLLECTOR_STANDBY_LOG_PATH = os.getenv(
    "LIVE_COLLECTOR_STANDBY_LOG_PATH",
    os.path.join(os.path.dirname(DB_PATH), "collector_standby.log"),
)
LIVE_COLLECTOR_LEASE_PATH = os.getenv(
    "LIVE_COLLECTOR_LEASE_PATH",
    os.path.join(os.path.dirname(DB_PATH), "collector_lease.json"),
)
LIVE_COLLECTOR_LEASE_TTL_SEC = int(os.getenv("LIVE_COLLECTOR_LEASE_TTL_SEC", "6"))
LIVE_COLLECTOR_HA_ENABLED = os.getenv("LIVE_COLLECTOR_HA_ENABLED", "1") == "1"

# --- Collector ---
COLLECTOR_ROOT = _PROJECT_ROOT
_venv_python = os.path.join(_PROJECT_ROOT, ".venv", "bin", "python3")
_fallback_python = "python3"
COLLECTOR_PYTHON = os.getenv(
    "COLLECTOR_PYTHON",
    _venv_python if os.path.exists(_venv_python) else _fallback_python,
)
COLLECTOR_SRC_PATH = os.getenv(
    "COLLECTOR_SRC_PATH",
    os.path.join(_PROJECT_ROOT, "src"),
)
COLLECTOR_HEADLESS = os.getenv("COLLECTOR_HEADLESS", "1")
COLLECTOR_POLL_INTERVAL_MS = os.getenv("COLLECTOR_POLL_INTERVAL_MS", "1500")
# CSS selector for the live viewer count element.
# Default targets the <strong> with neutral/muted colour + tabular digits
# that Whatnot uses to display the viewer count (e.g. "496").
VIEWER_COUNT_SELECTOR = os.getenv(
    "VIEWER_COUNT_SELECTOR",
    "strong.text-neutrals-opaque-50.tabular-nums",
)
COLLECTOR_COOKIES_PATH = os.getenv(
    "COOKIES_PATH",
    os.path.join(_PROJECT_ROOT, "www.whatnot.com_cookies.json"),
)

# --- Vite Build Output ---
VITE_DIST_PATH = os.getenv(
    "VITE_DIST_PATH",
    os.path.join(_PROJECT_ROOT, "dashboard-vite", "dist"),
)

# --- Shop Autoscrape ---
SHOP_AUTOSCRAPE_ENABLED = os.getenv("SHOP_AUTOSCRAPE_ENABLED", "1") == "1"
SHOP_AUTOSCRAPE_INTERVAL_SEC = int(os.getenv("SHOP_AUTOSCRAPE_INTERVAL_SEC", "3600"))
SHOP_AUTOSCRAPE_MIN_HOURS = float(os.getenv("SHOP_AUTOSCRAPE_MIN_HOURS", "56"))
SHOP_AUTOSCRAPE_WARMUP_SEC = int(os.getenv("SHOP_AUTOSCRAPE_WARMUP_SEC", "120"))
SHOP_AUTOSCRAPE_MAX_PER_CYCLE = int(os.getenv("SHOP_AUTOSCRAPE_MAX_PER_CYCLE", "0"))

# --- Whatnot Review Autoscrape ---
REVIEW_AUTOSCRAPE_ENABLED = os.getenv("REVIEW_AUTOSCRAPE_ENABLED", "1") == "1"
REVIEW_AUTOSCRAPE_INTERVAL_SEC = int(os.getenv("REVIEW_AUTOSCRAPE_INTERVAL_SEC", "302400"))
REVIEW_AUTOSCRAPE_WARMUP_SEC = int(os.getenv("REVIEW_AUTOSCRAPE_WARMUP_SEC", "180"))
REVIEW_AUTOSCRAPE_TARGET = os.getenv("REVIEW_AUTOSCRAPE_TARGET", "ynfdeals")

# --- Odoo ---
ODOO_URL     = os.getenv("ODOO_URL", "http://localhost:8070")
ODOO_DB      = os.getenv("ODOO_DB", "")
ODOO_USER    = os.getenv("ODOO_USER", "admin")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "")

# --- Security ---
# If set, all POST /api/* requests must include: Authorization: Bearer <token>
# Leave empty to disable authentication (default for local use).
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "")
DASHBOARD_API_BEARER_BYPASS_ENABLED = os.getenv("DASHBOARD_API_BEARER_BYPASS_ENABLED", "0") == "1"
DASHBOARD_API_BEARER_BYPASS_IP_ALLOWLIST = [
    item.strip()
    for item in os.getenv("DASHBOARD_API_BEARER_BYPASS_IP_ALLOWLIST", "").split(",")
    if item.strip()
]

# --- Dashboard Authentication ---
DASHBOARD_AUTH_REQUIRED = os.getenv("DASHBOARD_AUTH_REQUIRED", "0") == "1"
DASHBOARD_HTTPS_ONLY = os.getenv("DASHBOARD_HTTPS_ONLY", "0") == "1"
DASHBOARD_HSTS_ENABLED = os.getenv("DASHBOARD_HSTS_ENABLED", "0") == "1"
DASHBOARD_SESSION_COOKIE = os.getenv("DASHBOARD_SESSION_COOKIE", "wn_session")
DASHBOARD_CSRF_COOKIE = os.getenv("DASHBOARD_CSRF_COOKIE", "wn_csrf")
DASHBOARD_JWT_SECRET = os.getenv("DASHBOARD_JWT_SECRET", "")
DASHBOARD_POS_TOKEN_PEPPER = os.getenv("DASHBOARD_POS_TOKEN_PEPPER", "")
DASHBOARD_POS_TOKEN_TTL_DAYS = int(os.getenv("DASHBOARD_POS_TOKEN_TTL_DAYS", "30"))
DASHBOARD_SESSION_TTL_SEC = int(os.getenv("DASHBOARD_SESSION_TTL_SEC", "2592000"))   # 30 days hard limit
DASHBOARD_SESSION_IDLE_TTL_SEC = int(os.getenv("DASHBOARD_SESSION_IDLE_TTL_SEC", "28800"))  # 8 hours idle
DASHBOARD_CSRF_HEADER = os.getenv("DASHBOARD_CSRF_HEADER", "X-CSRF-Token")
DASHBOARD_AUTH_USERS_PATH = os.getenv(
    "DASHBOARD_AUTH_USERS_PATH",
    os.path.join(os.path.dirname(DB_PATH), "auth_users.json"),
)
DASHBOARD_BOOTSTRAP_ADMIN_EMAIL = os.getenv("DASHBOARD_BOOTSTRAP_ADMIN_EMAIL", "")
DASHBOARD_BOOTSTRAP_ADMIN_HASH = os.getenv("DASHBOARD_BOOTSTRAP_ADMIN_HASH", "")
DASHBOARD_BOOTSTRAP_ADMIN_ROLE = os.getenv("DASHBOARD_BOOTSTRAP_ADMIN_ROLE", "admin")
DASHBOARD_TOTP_ENCRYPTION_KEY = os.getenv("DASHBOARD_TOTP_ENCRYPTION_KEY", "")
TIKTOK_SHOP_APP_KEY = os.getenv("TIKTOK_SHOP_APP_KEY", "")
TIKTOK_SHOP_APP_SECRET = os.getenv("TIKTOK_SHOP_APP_SECRET", "")
TIKTOK_SHOP_SERVICE_ID = os.getenv("TIKTOK_SHOP_SERVICE_ID", "")
TIKTOK_SHOP_REDIRECT_URI = os.getenv("TIKTOK_SHOP_REDIRECT_URI", "")
TIKTOK_SHOP_AUTH_BASE_URL = os.getenv("TIKTOK_SHOP_AUTH_BASE_URL", "https://auth.tiktok-shops.com")
TIKTOK_SHOP_AUTHORIZE_BASE_URL = os.getenv("TIKTOK_SHOP_AUTHORIZE_BASE_URL", "https://services.us.tiktokshop.com")
TIKTOK_SHOP_API_BASE_URL = os.getenv("TIKTOK_SHOP_API_BASE_URL", "https://open-api.tiktokglobalshop.com")
TIKTOK_SHOP_TOKEN_URL = os.getenv("TIKTOK_SHOP_TOKEN_URL", "https://auth.tiktok-shops.com/api/v2/token/get")
TIKTOK_SHOP_REFRESH_URL = os.getenv("TIKTOK_SHOP_REFRESH_URL", "https://auth.tiktok-shops.com/api/v2/token/refresh")
TIKTOK_SHOP_TARGET_IDC = os.getenv("TIKTOK_SHOP_TARGET_IDC", "alisg")
TIKTOK_SHOP_TOKEN_ENCRYPTION_KEY = os.getenv("TIKTOK_SHOP_TOKEN_ENCRYPTION_KEY", "")
TIKTOK_SHOP_ORDER_IMPORT_ENABLED = os.getenv("TIKTOK_SHOP_ORDER_IMPORT_ENABLED", "1") == "1"
GOOGLE_SHEETS_BACKUP_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_BACKUP_SPREADSHEET_ID", "")
GOOGLE_SHEETS_BACKUP_SPREADSHEET_URL = os.getenv("GOOGLE_SHEETS_BACKUP_SPREADSHEET_URL", "")
GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON", "")
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE", "")
_dashboard_allowed_origins = {
    item.strip()
    for item in os.getenv("DASHBOARD_ALLOWED_ORIGINS", "").split(",")
    if item.strip()
}
_dashboard_allowed_origins.update(
    {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8088",
        "http://127.0.0.1:8088",
        "https://localhost:3000",
        "https://127.0.0.1:3000",
        "https://localhost:4173",
        "https://127.0.0.1:4173",
        "https://localhost:5173",
        "https://127.0.0.1:5173",
        "https://localhost:8088",
        "https://127.0.0.1:8088",
    }
)
DASHBOARD_ALLOWED_ORIGINS = sorted(_dashboard_allowed_origins)
DASHBOARD_ALLOWED_LOCAL_ORIGIN_PORTS = {
    int(item.strip())
    for item in os.getenv("DASHBOARD_ALLOWED_LOCAL_ORIGIN_PORTS", "3000,4173,5173,8088").split(",")
    if item.strip().isdigit()
}


def _is_private_dashboard_host(hostname):
    host = str(hostname or "").strip().lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
        return ip.is_loopback or ip.is_private
    except ValueError:
        pass
    # Hostname (e.g. machine name like cybertechna-MS-7C94) — resolve and check
    try:
        results = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        for _family, _type, _proto, _canonname, sockaddr in results:
            addr = sockaddr[0]
            try:
                ip = ipaddress.ip_address(addr)
                if ip.is_loopback or ip.is_private:
                    return True
            except ValueError:
                continue
    except OSError:
        pass
    return False


def dashboard_origin_allowed(origin="", referer="", host=""):
    """Allow same-host and local/LAN dashboard origins without allowing public sites."""
    allowed = set(DASHBOARD_ALLOWED_ORIGINS)
    if host:
        allowed.add(f"http://{host}")
        allowed.add(f"https://{host}")

    candidate = str(origin or "").strip()
    if candidate:
        # Some browser/file-picker flows can send Origin: null. Keep this tight:
        # only allow it when the request is still targeting a local/private
        # dashboard host, or when the referer independently passes below.
        if candidate.lower() == "null":
            parsed_host = urlparse(f"//{host}") if host else None
            host_name = str(parsed_host.hostname or "").strip("[]") if parsed_host else ""
            host_port = parsed_host.port if parsed_host else None
            is_single_label_lan_name = bool(host_name and "." not in host_name and host_name.lower() not in {"com", "net", "org"})
            if (
                _is_private_dashboard_host(host_name)
                or (is_single_label_lan_name and host_port in DASHBOARD_ALLOWED_LOCAL_ORIGIN_PORTS)
            ):
                return True
            if not referer:
                return False
            candidate = ""
        else:
            parsed = urlparse(candidate)
            if candidate in allowed:
                return True
            if parsed.scheme in {"http", "https"} and _is_private_dashboard_host(parsed.hostname):
                return True
            if parsed.scheme in {"http", "https"} and parsed.port in DASHBOARD_ALLOWED_LOCAL_ORIGIN_PORTS:
                return _is_private_dashboard_host(parsed.hostname)
            return False

    ref = str(referer or "").strip()
    if not ref:
        return True
    if any(ref.startswith(prefix) for prefix in allowed):
        return True
    parsed = urlparse(ref)
    if parsed.scheme in {"http", "https"} and _is_private_dashboard_host(parsed.hostname):
        return True
    if parsed.scheme in {"http", "https"} and parsed.port in DASHBOARD_ALLOWED_LOCAL_ORIGIN_PORTS:
        return _is_private_dashboard_host(parsed.hostname)
    return False

DASHBOARD_ADMIN_IP_ALLOWLIST = [
    item.strip()
    for item in os.getenv("DASHBOARD_ADMIN_IP_ALLOWLIST", "").split(",")
    if item.strip()
]
DASHBOARD_CSP = os.getenv(
    "DASHBOARD_CSP",
    "default-src 'self'; "
    "img-src 'self' data: blob: https:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "script-src 'self'; "
    "connect-src 'self' https: wss:; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'",
)
DASHBOARD_RATE_LIMIT_LOGIN = os.getenv("DASHBOARD_RATE_LIMIT_LOGIN", "8/minute")
DASHBOARD_RATE_LIMIT_DIAGNOSTICS = os.getenv("DASHBOARD_RATE_LIMIT_DIAGNOSTICS", "60/minute")
DASHBOARD_RATE_LIMIT_PUBLIC_TOKEN = os.getenv("DASHBOARD_RATE_LIMIT_PUBLIC_TOKEN", "120/minute")
DASHBOARD_RATE_LIMIT_API = os.getenv("DASHBOARD_RATE_LIMIT_API", "600/minute")

# --- Optional Redis Sidecar ---
# Disabled by default so it has zero runtime effect until explicitly enabled.
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "0") == "1"
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_PREFIX = os.getenv("REDIS_PREFIX", "wnlive")
REDIS_LEASE_TTL_SEC = int(os.getenv("REDIS_LEASE_TTL_SEC", "10"))
REDIS_SOCKET_CONNECT_TIMEOUT_SEC = float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT_SEC", "1.0"))
REDIS_SOCKET_TIMEOUT_SEC = float(os.getenv("REDIS_SOCKET_TIMEOUT_SEC", "1.5"))
REDIS_HEALTH_CACHE_SEC = float(os.getenv("REDIS_HEALTH_CACHE_SEC", "2.0"))

# --- Postgres Primary Sidecar ---
# Default runtime is Postgres-first. Set POSTGRES_SIDECAR_ENABLED=0 only for
# explicit offline/manual compatibility work.
POSTGRES_SIDECAR_ENABLED = os.getenv("POSTGRES_SIDECAR_ENABLED", "1") == "1"
POSTGRES_SIDECAR_DBNAME = os.getenv("POSTGRES_SIDECAR_DBNAME", "whatnot_sidecar")
POSTGRES_SIDECAR_DSN = os.getenv(
    "POSTGRES_SIDECAR_DSN",
    f"dbname={POSTGRES_SIDECAR_DBNAME}",
)
POSTGRES_SIDECAR_SCHEMA = os.getenv("POSTGRES_SIDECAR_SCHEMA", "sqlite_mirror")
POSTGRES_SIDECAR_BATCH_SIZE = int(os.getenv("POSTGRES_SIDECAR_BATCH_SIZE", "5000"))
POSTGRES_SIDECAR_HOT_SYNC_INTERVAL_SEC = int(os.getenv("POSTGRES_SIDECAR_HOT_SYNC_INTERVAL_SEC", "60"))
POSTGRES_SIDECAR_FULL_SYNC_INTERVAL_SEC = int(os.getenv("POSTGRES_SIDECAR_FULL_SYNC_INTERVAL_SEC", "21600"))
POSTGRES_SIDECAR_STATE_PATH = os.getenv(
    "POSTGRES_SIDECAR_STATE_PATH",
    os.path.join(os.path.dirname(DB_PATH), "sidecar_status.json"),
)

# --- Embedded Redis Mirror Sidecar ---
# We keep this separate from the live runtime so Redis can be brought up locally
# without requiring a system redis-server package.
REDIS_EMBEDDED_DB_PATH = os.getenv(
    "REDIS_EMBEDDED_DB_PATH",
    os.path.join(os.path.dirname(DB_PATH), "redislite", "sidecar.redis"),
)
REDIS_EMBEDDED_STATE_PATH = os.getenv(
    "REDIS_EMBEDDED_STATE_PATH",
    os.path.join(os.path.dirname(DB_PATH), "redislite", "sidecar_runtime.json"),
)
REDIS_SIDECAR_SYNC_INTERVAL_SEC = int(os.getenv("REDIS_SIDECAR_SYNC_INTERVAL_SEC", "15"))

# --- Postgres Primary Cutover Controls ---
# These flags let us move business domains to Postgres gradually while keeping
# SQLite as a shadow writer until confidence is high enough to retire it.
# Default runtime now prefers Postgres across domains unless an environment
# override explicitly pushes a domain back to SQLite.
DB_PRIMARY_DOMAIN_SETTINGS = os.getenv("DB_PRIMARY_DOMAIN_SETTINGS", "postgres").strip().lower()
DB_PRIMARY_DOMAIN_REVIEWS = os.getenv("DB_PRIMARY_DOMAIN_REVIEWS", "postgres").strip().lower()
DB_PRIMARY_DOMAIN_EMPLOYEES = os.getenv("DB_PRIMARY_DOMAIN_EMPLOYEES", "postgres").strip().lower()
DB_PRIMARY_DOMAIN_IN_HOUSE = os.getenv("DB_PRIMARY_DOMAIN_IN_HOUSE", "postgres").strip().lower()
DB_PRIMARY_DOMAIN_INVENTORY = os.getenv("DB_PRIMARY_DOMAIN_INVENTORY", "postgres").strip().lower()
DB_PRIMARY_INVENTORY_PRODUCTS = os.getenv(
    "DB_PRIMARY_INVENTORY_PRODUCTS",
    DB_PRIMARY_DOMAIN_INVENTORY,
).strip().lower()
DB_PRIMARY_INVENTORY_AUDIT = os.getenv(
    "DB_PRIMARY_INVENTORY_AUDIT",
    DB_PRIMARY_DOMAIN_INVENTORY,
).strip().lower()
DB_PRIMARY_INVENTORY_MOVEMENTS = os.getenv(
    "DB_PRIMARY_INVENTORY_MOVEMENTS",
    DB_PRIMARY_DOMAIN_INVENTORY,
).strip().lower()
DB_PRIMARY_DOMAIN_COMPANY = os.getenv("DB_PRIMARY_DOMAIN_COMPANY", "postgres").strip().lower()
DB_PRIMARY_COMPANY_CUSTOMERS = os.getenv(
    "DB_PRIMARY_COMPANY_CUSTOMERS",
    DB_PRIMARY_DOMAIN_COMPANY,
).strip().lower()
DB_PRIMARY_COMPANY_SESSIONS = os.getenv(
    "DB_PRIMARY_COMPANY_SESSIONS",
    DB_PRIMARY_DOMAIN_COMPANY,
).strip().lower()
DB_PRIMARY_COMPANY_LOTS = os.getenv(
    "DB_PRIMARY_COMPANY_LOTS",
    DB_PRIMARY_DOMAIN_COMPANY,
).strip().lower()
DB_PRIMARY_COMPANY_PENDING = os.getenv(
    "DB_PRIMARY_COMPANY_PENDING",
    DB_PRIMARY_DOMAIN_COMPANY,
).strip().lower()
DB_PRIMARY_COMPANY_RESULTS = os.getenv(
    "DB_PRIMARY_COMPANY_RESULTS",
    DB_PRIMARY_DOMAIN_COMPANY,
).strip().lower()
DB_PRIMARY_COMPANY_ORDERS = os.getenv(
    "DB_PRIMARY_COMPANY_ORDERS",
    DB_PRIMARY_DOMAIN_COMPANY,
).strip().lower()
DB_PRIMARY_DOMAIN_EVENTS = os.getenv("DB_PRIMARY_DOMAIN_EVENTS", "postgres").strip().lower()
DB_PRIMARY_INGEST_STREAMS = os.getenv(
    "DB_PRIMARY_INGEST_STREAMS",
    DB_PRIMARY_DOMAIN_EVENTS,
).strip().lower()
DB_PRIMARY_INGEST_STREAM_MERGE = os.getenv(
    "DB_PRIMARY_INGEST_STREAM_MERGE",
    DB_PRIMARY_INGEST_STREAMS,
).strip().lower()
DB_PRIMARY_INGEST_EVENTS = os.getenv(
    "DB_PRIMARY_INGEST_EVENTS",
    DB_PRIMARY_DOMAIN_EVENTS,
).strip().lower()
DB_PRIMARY_INGEST_FAILED = os.getenv(
    "DB_PRIMARY_INGEST_FAILED",
    DB_PRIMARY_DOMAIN_EVENTS,
).strip().lower()
DB_PRIMARY_INGEST_USERS = os.getenv(
    "DB_PRIMARY_INGEST_USERS",
    DB_PRIMARY_DOMAIN_EVENTS,
).strip().lower()
DB_PRIMARY_INGEST_LOTS = os.getenv(
    "DB_PRIMARY_INGEST_LOTS",
    DB_PRIMARY_DOMAIN_EVENTS,
).strip().lower()
DB_PRIMARY_DOMAIN_ANALYTICS = os.getenv("DB_PRIMARY_DOMAIN_ANALYTICS", "postgres").strip().lower()

DB_DUAL_WRITE_SETTINGS = os.getenv("DB_DUAL_WRITE_SETTINGS", "0") == "1"
DB_DUAL_WRITE_REVIEWS = os.getenv("DB_DUAL_WRITE_REVIEWS", "0") == "1"
DB_DUAL_WRITE_EMPLOYEES = os.getenv("DB_DUAL_WRITE_EMPLOYEES", "0") == "1"
DB_DUAL_WRITE_IN_HOUSE = os.getenv("DB_DUAL_WRITE_IN_HOUSE", "0") == "1"
DB_DUAL_WRITE_INVENTORY = os.getenv("DB_DUAL_WRITE_INVENTORY", "0") == "1"
DB_DUAL_WRITE_INVENTORY_PRODUCTS = os.getenv(
    "DB_DUAL_WRITE_INVENTORY_PRODUCTS",
    "1" if DB_DUAL_WRITE_INVENTORY else "0",
) == "1"
DB_DUAL_WRITE_INVENTORY_AUDIT = os.getenv(
    "DB_DUAL_WRITE_INVENTORY_AUDIT",
    "1" if DB_DUAL_WRITE_INVENTORY else "0",
) == "1"
DB_DUAL_WRITE_INVENTORY_MOVEMENTS = os.getenv(
    "DB_DUAL_WRITE_INVENTORY_MOVEMENTS",
    "1" if DB_DUAL_WRITE_INVENTORY else "0",
) == "1"
DB_DUAL_WRITE_COMPANY = os.getenv("DB_DUAL_WRITE_COMPANY", "0") == "1"
DB_DUAL_WRITE_COMPANY_CUSTOMERS = os.getenv(
    "DB_DUAL_WRITE_COMPANY_CUSTOMERS",
    "1" if DB_DUAL_WRITE_COMPANY else "0",
) == "1"
DB_DUAL_WRITE_COMPANY_SESSIONS = os.getenv(
    "DB_DUAL_WRITE_COMPANY_SESSIONS",
    "1" if DB_DUAL_WRITE_COMPANY else "0",
) == "1"
DB_DUAL_WRITE_COMPANY_LOTS = os.getenv(
    "DB_DUAL_WRITE_COMPANY_LOTS",
    "1" if DB_DUAL_WRITE_COMPANY else "0",
) == "1"
DB_DUAL_WRITE_COMPANY_PENDING = os.getenv(
    "DB_DUAL_WRITE_COMPANY_PENDING",
    "1" if DB_DUAL_WRITE_COMPANY else "0",
) == "1"
DB_DUAL_WRITE_COMPANY_RESULTS = os.getenv(
    "DB_DUAL_WRITE_COMPANY_RESULTS",
    "1" if DB_DUAL_WRITE_COMPANY else "0",
) == "1"
DB_DUAL_WRITE_COMPANY_ORDERS = os.getenv(
    "DB_DUAL_WRITE_COMPANY_ORDERS",
    "1" if DB_DUAL_WRITE_COMPANY else "0",
) == "1"
DB_DUAL_WRITE_EVENTS = os.getenv("DB_DUAL_WRITE_EVENTS", "0") == "1"
DB_DUAL_WRITE_INGEST_STREAMS = os.getenv(
    "DB_DUAL_WRITE_INGEST_STREAMS",
    "1" if DB_DUAL_WRITE_EVENTS else "0",
) == "1"
DB_DUAL_WRITE_INGEST_STREAM_MERGE = os.getenv(
    "DB_DUAL_WRITE_INGEST_STREAM_MERGE",
    "1" if DB_DUAL_WRITE_INGEST_STREAMS else "0",
) == "1"
DB_DUAL_WRITE_INGEST_EVENTS = os.getenv(
    "DB_DUAL_WRITE_INGEST_EVENTS",
    "1" if DB_DUAL_WRITE_EVENTS else "0",
) == "1"
DB_DUAL_WRITE_INGEST_FAILED = os.getenv(
    "DB_DUAL_WRITE_INGEST_FAILED",
    "1" if DB_DUAL_WRITE_EVENTS else "0",
) == "1"
DB_DUAL_WRITE_INGEST_USERS = os.getenv(
    "DB_DUAL_WRITE_INGEST_USERS",
    "1" if DB_DUAL_WRITE_EVENTS else "0",
) == "1"
DB_DUAL_WRITE_INGEST_LOTS = os.getenv(
    "DB_DUAL_WRITE_INGEST_LOTS",
    "1" if DB_DUAL_WRITE_EVENTS else "0",
) == "1"
DB_DUAL_WRITE_ANALYTICS = os.getenv("DB_DUAL_WRITE_ANALYTICS", "0") == "1"

DB_VALIDATE_WRITE_SETTINGS = os.getenv("DB_VALIDATE_WRITE_SETTINGS", "1") == "1"
DB_VALIDATE_WRITE_REVIEWS = os.getenv("DB_VALIDATE_WRITE_REVIEWS", "1") == "1"
DB_VALIDATE_WRITE_EMPLOYEES = os.getenv("DB_VALIDATE_WRITE_EMPLOYEES", "1") == "1"
DB_VALIDATE_WRITE_IN_HOUSE = os.getenv("DB_VALIDATE_WRITE_IN_HOUSE", "1") == "1"
DB_VALIDATE_WRITE_INVENTORY = os.getenv("DB_VALIDATE_WRITE_INVENTORY", "1") == "1"
DB_VALIDATE_WRITE_INVENTORY_PRODUCTS = os.getenv(
    "DB_VALIDATE_WRITE_INVENTORY_PRODUCTS",
    "1" if DB_VALIDATE_WRITE_INVENTORY else "0",
) == "1"
DB_VALIDATE_WRITE_INVENTORY_AUDIT = os.getenv(
    "DB_VALIDATE_WRITE_INVENTORY_AUDIT",
    "1" if DB_VALIDATE_WRITE_INVENTORY else "0",
) == "1"
DB_VALIDATE_WRITE_INVENTORY_MOVEMENTS = os.getenv(
    "DB_VALIDATE_WRITE_INVENTORY_MOVEMENTS",
    "1" if DB_VALIDATE_WRITE_INVENTORY else "0",
) == "1"
DB_VALIDATE_WRITE_COMPANY = os.getenv("DB_VALIDATE_WRITE_COMPANY", "1") == "1"
DB_VALIDATE_WRITE_COMPANY_CUSTOMERS = os.getenv(
    "DB_VALIDATE_WRITE_COMPANY_CUSTOMERS",
    "1" if DB_VALIDATE_WRITE_COMPANY else "0",
) == "1"
DB_VALIDATE_WRITE_COMPANY_SESSIONS = os.getenv(
    "DB_VALIDATE_WRITE_COMPANY_SESSIONS",
    "1" if DB_VALIDATE_WRITE_COMPANY else "0",
) == "1"
DB_VALIDATE_WRITE_COMPANY_LOTS = os.getenv(
    "DB_VALIDATE_WRITE_COMPANY_LOTS",
    "1" if DB_VALIDATE_WRITE_COMPANY else "0",
) == "1"
DB_VALIDATE_WRITE_COMPANY_PENDING = os.getenv(
    "DB_VALIDATE_WRITE_COMPANY_PENDING",
    "1" if DB_VALIDATE_WRITE_COMPANY else "0",
) == "1"
DB_VALIDATE_WRITE_COMPANY_RESULTS = os.getenv(
    "DB_VALIDATE_WRITE_COMPANY_RESULTS",
    "1" if DB_VALIDATE_WRITE_COMPANY else "0",
) == "1"
DB_VALIDATE_WRITE_COMPANY_ORDERS = os.getenv(
    "DB_VALIDATE_WRITE_COMPANY_ORDERS",
    "1" if DB_VALIDATE_WRITE_COMPANY else "0",
) == "1"
DB_VALIDATE_WRITE_EVENTS = os.getenv("DB_VALIDATE_WRITE_EVENTS", "1") == "1"
DB_VALIDATE_WRITE_INGEST_STREAMS = os.getenv(
    "DB_VALIDATE_WRITE_INGEST_STREAMS",
    "1" if DB_VALIDATE_WRITE_EVENTS else "0",
) == "1"
DB_VALIDATE_WRITE_INGEST_STREAM_MERGE = os.getenv(
    "DB_VALIDATE_WRITE_INGEST_STREAM_MERGE",
    "1" if DB_VALIDATE_WRITE_INGEST_STREAMS else "0",
) == "1"
DB_VALIDATE_WRITE_INGEST_EVENTS = os.getenv(
    "DB_VALIDATE_WRITE_INGEST_EVENTS",
    "1" if DB_VALIDATE_WRITE_EVENTS else "0",
) == "1"
DB_VALIDATE_WRITE_INGEST_FAILED = os.getenv(
    "DB_VALIDATE_WRITE_INGEST_FAILED",
    "1" if DB_VALIDATE_WRITE_EVENTS else "0",
) == "1"
DB_VALIDATE_WRITE_INGEST_USERS = os.getenv(
    "DB_VALIDATE_WRITE_INGEST_USERS",
    "1" if DB_VALIDATE_WRITE_EVENTS else "0",
) == "1"
DB_VALIDATE_WRITE_INGEST_LOTS = os.getenv(
    "DB_VALIDATE_WRITE_INGEST_LOTS",
    "1" if DB_VALIDATE_WRITE_EVENTS else "0",
) == "1"
DB_VALIDATE_WRITE_ANALYTICS = os.getenv("DB_VALIDATE_WRITE_ANALYTICS", "1") == "1"

POSTGRES_CUTOVER_MISMATCH_LOG_PATH = os.getenv(
    "POSTGRES_CUTOVER_MISMATCH_LOG_PATH",
    os.path.join(os.path.dirname(DB_PATH), "postgres_cutover_mismatches.jsonl"),
)

# --- Events DB Read Cutover Controls ---
EVENTS_DB_READ_BACKEND = os.getenv("EVENTS_DB_READ_BACKEND", "postgres").strip().lower()
EVENTS_DB_VALIDATE_READS = os.getenv("EVENTS_DB_VALIDATE_READS", "1") == "1"
