from __future__ import annotations

from contextlib import asynccontextmanager
from collections import defaultdict, deque
import hashlib
import hmac
import json
from pathlib import Path
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.legacy_analytics_compat import router as legacy_analytics_compat_router
from app.api.legacy_analytics_intelligence import router as legacy_analytics_intelligence_router
from app.api.legacy_admin_mutations import router as legacy_admin_mutations_router
from app.api.legacy_auth_admin import router as legacy_auth_admin_router
from app.api.legacy_competitor_detection import router as legacy_competitor_detection_router
from app.api.legacy_core_analytics import router as legacy_core_analytics_router
from app.api.legacy_exports import router as legacy_exports_router
from app.api.legacy_facts import router as legacy_facts_router
from app.api.legacy_feed import router as legacy_feed_router
from app.api.legacy_inventory_admin_mutations import router as legacy_inventory_admin_mutations_router
from app.api.legacy_mutations import router as legacy_mutations_router
from app.api.legacy_order_mutations import router as legacy_order_mutations_router
from app.api.legacy_product_profit import router as legacy_product_profit_router
from app.api.legacy_sidecar_ops import router as legacy_sidecar_ops_router
from app.api.legacy_shop_analytics import router as legacy_shop_analytics_router
from app.api.legacy_shop_scrape import router as legacy_shop_scrape_router
from app.api.legacy_tiktok import router as legacy_tiktok_router
from app.api.legacy_user_cluster import router as legacy_user_cluster_router
from app.api.legacy_detail_reads import router as legacy_detail_reads_router
from app.api.legacy_inventory_detail import router as legacy_inventory_detail_router
from app.api.legacy_ops import router as legacy_ops_router
from app.api.legacy_reads import router as legacy_reads_router
from app.api.legacy_runtime import router as legacy_runtime_router
from app.api.legacy_sale_orders import router as legacy_sale_orders_router
from app.api.legacy_proxy import router as legacy_proxy_router
from app.core.legacy_bridge import LegacyBridgeManager
from app.core.redis import ping, set_runtime_state
from app.core.runtime_observability import record_request_metric
from app.services.tiktok_shop_integration_service import handle_tiktok_webhook
from server.auth import audit_auth_event, auth_enabled, csrf_cookie_name, csrf_header_name, get_session, session_cookie_name
from server.config import (
    API_SECRET_KEY,
    DASHBOARD_API_BEARER_BYPASS_ENABLED,
    DASHBOARD_API_BEARER_BYPASS_IP_ALLOWLIST,
    DASHBOARD_CSP,
    DASHBOARD_HSTS_ENABLED,
    DASHBOARD_RATE_LIMIT_API,
    DASHBOARD_RATE_LIMIT_DIAGNOSTICS,
    DASHBOARD_RATE_LIMIT_LOGIN,
    DASHBOARD_RATE_LIMIT_PUBLIC_TOKEN,
    dashboard_origin_allowed,
)
from server.rbac import ADMIN_POLICY, MUTATING_METHODS, role_allows, route_policy
from .api.routers import api_router
from .config import settings


REPO_ROOT = Path(__file__).resolve().parents[1]
API_PERF_LOG_PATH = REPO_ROOT / "data" / "api_perf_requests.jsonl"
API_PERF_SLOW_MS = 400.0
API_PERF_LARGE_BYTES = 300_000
VITE_DIST_PATH = REPO_ROOT / "dashboard-vite" / "dist"
VITE_INDEX_PATH = VITE_DIST_PATH / "index.html"
PRODUCT_MEDIA_PATH = REPO_ROOT / "data" / "marketplace_images"
PRODUCT_UPLOADS_PATH = REPO_ROOT / "product_uploads"
PUBLIC_AUTH_PATHS = {
    "/api/auth/config",
    "/api/auth/login",
    "/api/auth/me",
    "/api/v2/auth/status",
}
PUBLIC_INGEST_PATHS = {
    "/api/v2/diagnostics/frontend-error",
    "/api/v2/integrations/tiktok-shop/webhook",
    "/api/v2/store-sync/products",
    "/api/v2/store-sync/products/sync",
    "/api/v2/medusa/orders",
}
PUBLIC_TOKEN_PATH_PREFIXES = (
    "/api/internal_pos/",
    "/api/v2/purchases/bargain/",
)
PUBLIC_TOKEN_PATHS = {
    "/api/internal_pos/orders",
}
PUBLIC_HEALTH_PATHS = {
    "/healthz",
    "/api/v2/health",
    "/api/v2/ready",
}
FEED_API_PATHS = {"/latest_id", "/events", "/recent"}
PUBLIC_OBS_PATHS = {
    "/api/stream_status",
    "/api/obs/current",
    "/api/obs/demo/scan",
    "/api/current_lot/products",
}
RATE_BUCKETS = defaultdict(deque)


def _append_api_perf_event(event: dict) -> None:
    try:
        API_PERF_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with API_PERF_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _vite_index_response():
    return FileResponse(
        VITE_INDEX_PATH,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


def _vite_static_response(path: Path):
    if path.name in {"index.html", "ops-next.html"}:
        return FileResponse(
            path,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return FileResponse(path)


def _client_ip(request) -> str:
    forwarded = (request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _is_api_path(path: str) -> bool:
    return path.startswith("/api/") or path in FEED_API_PATHS


def _bearer_authorized(request) -> bool:
    if not API_SECRET_KEY or not DASHBOARD_API_BEARER_BYPASS_ENABLED:
        return False
    if DASHBOARD_API_BEARER_BYPASS_IP_ALLOWLIST and _client_ip(request) not in DASHBOARD_API_BEARER_BYPASS_IP_ALLOWLIST:
        return False
    return request.headers.get("Authorization", "") == f"Bearer {API_SECRET_KEY}"


def _public_api_path(path: str) -> bool:
    if (
        path in PUBLIC_AUTH_PATHS
        or path in PUBLIC_INGEST_PATHS
        or path in PUBLIC_HEALTH_PATHS
        or path in FEED_API_PATHS
        or path in PUBLIC_OBS_PATHS
    ):
        return True
    if path in PUBLIC_TOKEN_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_TOKEN_PATH_PREFIXES):
        return True
    return False


def _origin_allowed(request) -> bool:
    origin = (request.headers.get("Origin") or "").strip()
    referer = (request.headers.get("Referer") or "").strip()
    host = (request.headers.get("Host") or "").strip()
    return dashboard_origin_allowed(origin=origin, referer=referer, host=host)


def _is_trustworthy_origin(request) -> bool:
    proto = (request.headers.get("X-Forwarded-Proto") or request.url.scheme or "").split(",", 1)[0].strip().lower()
    host = (request.headers.get("Host") or request.url.hostname or "").split(":", 1)[0].strip().lower()
    return proto == "https" or host in {"localhost", "127.0.0.1", "::1"}


def _parse_rate_limit(value: str, default_limit: int, default_window: int) -> tuple[int, int]:
    raw = str(value or "").strip().lower()
    if not raw:
        return default_limit, default_window
    try:
        count_raw, window_raw = raw.split("/", 1)
        limit = max(1, int(count_raw.strip()))
        window = {
            "second": 1,
            "sec": 1,
            "s": 1,
            "minute": 60,
            "min": 60,
            "m": 60,
            "hour": 3600,
            "h": 3600,
        }.get(window_raw.strip(), default_window)
        return limit, window
    except Exception:
        return default_limit, default_window


def _rate_limit_key(request, bucket: str) -> str:
    session = getattr(request.state, "dashboard_session", None) or {}
    subject = session.get("email") or _client_ip(request)
    return f"{bucket}:{subject}:{request.url.path}"


def _check_rate_limit(request, bucket: str, setting: str, default_limit: int, default_window: int):
    limit, window = _parse_rate_limit(setting, default_limit, default_window)
    now = time.monotonic()
    key = _rate_limit_key(request, bucket)
    rows = RATE_BUCKETS[key]
    while rows and now - rows[0] > window:
        rows.popleft()
    if len(rows) >= limit:
        retry_after = max(1, int(window - (now - rows[0])))
        audit_auth_event("rate_limited", path=request.url.path, method=request.method, bucket=bucket, client_ip=_client_ip(request))
        return JSONResponse(
            {"ok": False, "error": "rate_limited", "retry_after_sec": retry_after},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )
    rows.append(now)
    return None


def _route_policy(path: str, method: str) -> str:
    return route_policy(
        path,
        method,
        public_token_paths=PUBLIC_TOKEN_PATHS,
        public_token_prefixes=PUBLIC_TOKEN_PATH_PREFIXES,
    )


def _role_allows(session: dict, policy: str) -> bool:
    return role_allows(session.get("role"), policy)


def create_app(*, with_runtime: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bridge = None
        if with_runtime:
            if settings.legacy_bridge_enabled:
                bridge = LegacyBridgeManager(settings.legacy_bridge_host, settings.legacy_bridge_port)
                app.state.legacy_bridge_url = bridge.start()
            else:
                app.state.legacy_bridge_url = None
            app.state.redis_connected = ping() if settings.redis_enabled else False
            if app.state.redis_connected:
                try:
                    set_runtime_state(
                        "fastapi:boot",
                        {
                            "ok": True,
                            "app": settings.app_name,
                            "redis_connected": app.state.redis_connected,
                            "legacy_bridge_url": app.state.legacy_bridge_url,
                        },
                        ttl_seconds=3600,
                    )
                except Exception:
                    app.state.redis_connected = False
        else:
            app.state.legacy_bridge_url = getattr(app.state, "legacy_bridge_url", None)
            app.state.redis_connected = getattr(app.state, "redis_connected", False)
        try:
            yield
        finally:
            if bridge is not None:
                bridge.stop()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_metrics_middleware(request, call_next):
        started_at = time.perf_counter()
        response = await call_next(request)
        try:
            duration_ms = (time.perf_counter() - started_at) * 1000.0
            record_request_metric(
                request.url.path,
                request.method,
                response.status_code,
                duration_ms,
            )
            response.headers["Server-Timing"] = f"app;dur={duration_ms:.1f}"

            path = request.url.path or "/"
            if path.startswith("/api/") or path in FEED_API_PATHS:
                content_length = response.headers.get("content-length")
                try:
                    response_bytes = int(content_length) if content_length else 0
                except Exception:
                    response_bytes = 0
                event = {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime()),
                    "method": request.method,
                    "path": path,
                    "query": request.url.query,
                    "status": int(response.status_code),
                    "duration_ms": round(duration_ms, 1),
                    "response_bytes": response_bytes,
                    "client_ip": _client_ip(request),
                }
                _append_api_perf_event(event)
                if duration_ms >= API_PERF_SLOW_MS or response_bytes >= API_PERF_LARGE_BYTES:
                    print(
                        f"[api-perf] {request.method} {path} status={response.status_code} ms={duration_ms:.1f} bytes={response_bytes}",
                        flush=True,
                    )
        except Exception:
            pass
        return response

    @app.middleware("http")
    async def dashboard_auth_middleware(request, call_next):
        path = request.url.path
        if path in PUBLIC_INGEST_PATHS:
            limited = _check_rate_limit(request, "diagnostics", DASHBOARD_RATE_LIMIT_DIAGNOSTICS, 60, 60)
            if limited:
                return limited
        elif path in PUBLIC_TOKEN_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_TOKEN_PATH_PREFIXES):
            limited = _check_rate_limit(request, "public_token", DASHBOARD_RATE_LIMIT_PUBLIC_TOKEN, 120, 60)
            if limited:
                return limited

        if request.method == "OPTIONS" or not auth_enabled() or not _is_api_path(path) or _public_api_path(path):
            return await call_next(request)
        if _bearer_authorized(request):
            audit_auth_event("api_bearer_bypass", path=path, method=request.method, client_ip=_client_ip(request))
            return await call_next(request)

        session = get_session(
            request.cookies.get(session_cookie_name()) or "",
            client_ip=_client_ip(request),
            user_agent=request.headers.get("User-Agent", ""),
        )
        if not session:
            audit_auth_event("api_auth_required", path=path, method=request.method, client_ip=_client_ip(request))
            return JSONResponse({"ok": False, "error": "auth_required"}, status_code=401)

        request.state.dashboard_session = session
        limited = _check_rate_limit(request, "api", DASHBOARD_RATE_LIMIT_API, 600, 60)
        if limited:
            return limited

        policy = _route_policy(path, request.method)
        if not _role_allows(session, policy):
            audit_auth_event(
                "api_forbidden",
                path=path,
                method=request.method,
                policy=policy,
                email=session.get("email"),
                role=session.get("role"),
                client_ip=_client_ip(request),
            )
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

        if request.method.upper() in MUTATING_METHODS:
            if not _origin_allowed(request):
                audit_auth_event("csrf_origin_forbidden", path=path, method=request.method, email=session.get("email"), client_ip=_client_ip(request))
                return JSONResponse({"ok": False, "error": "origin_forbidden"}, status_code=403)
            expected = str(session.get("csrf_token") or "")
            header_token = str(request.headers.get(csrf_header_name()) or "").strip()
            cookie_token = str(request.cookies.get(csrf_cookie_name()) or "").strip()
            if not expected or not header_token or not cookie_token:
                audit_auth_event("csrf_failed", path=path, method=request.method, email=session.get("email"), client_ip=_client_ip(request))
                return JSONResponse({"ok": False, "error": "csrf_failed"}, status_code=403)
            if not hmac.compare_digest(header_token, expected) or not hmac.compare_digest(cookie_token, expected):
                audit_auth_event("csrf_failed", path=path, method=request.method, email=session.get("email"), client_ip=_client_ip(request))
                return JSONResponse({"ok": False, "error": "csrf_failed"}, status_code=403)
            audit_auth_event("api_mutation_allowed", path=path, method=request.method, policy=policy, email=session.get("email"), role=session.get("role"), client_ip=_client_ip(request))
            if policy == ADMIN_POLICY:
                audit_auth_event("admin_mutation", path=path, method=request.method, actor_email=session.get("email"), client_ip=_client_ip(request))

        return await call_next(request)

    # ETag/304 for hot poll endpoints. Buffers the response body, hashes it,
    # and returns 304 Not Modified when the client's If-None-Match matches.
    # Scoped to a small allowlist of high-frequency reads to keep risk low.
    ETAG_PATHS = {
        "/api/stream_status",
        "/api/obs/current",
        "/api/current_lot/products",
        "/api/collector/health",
        "/api/v2/sessions/current/stats",
        "/api/session_stats",
        "/api/alerts",
        "/api/alerts/settings",
        "/api/fee_settings",
        "/api/inventory",
        "/api/sale_orders",
        "/api/tiktok_live_sessions/detail",
    }

    @app.middleware("http")
    async def etag_middleware(request, call_next):
        if request.method != "GET" or request.url.path not in ETAG_PATHS:
            return await call_next(request)
        response = await call_next(request)
        if response.status_code != 200:
            return response
        body_chunks = []
        async for chunk in response.body_iterator:
            body_chunks.append(chunk)
        body = b"".join(body_chunks)
        etag = 'W/"' + hashlib.sha1(body).hexdigest() + '"'
        if request.headers.get("if-none-match") == etag:
            headers = dict(response.headers)
            headers.pop("content-length", None)
            headers["etag"] = etag
            return Response(status_code=304, headers=headers)
        new_response = Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
        new_response.headers["ETag"] = etag
        new_response.headers.setdefault("Cache-Control", "private, max-age=0, must-revalidate")
        return new_response

    @app.middleware("http")
    async def security_headers_middleware(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if _is_trustworthy_origin(request):
            response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
            response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), interest-cohort=()")
        response.headers.setdefault("Content-Security-Policy", DASHBOARD_CSP)
        if DASHBOARD_HSTS_ENABLED and _is_trustworthy_origin(request) and (
            request.headers.get("X-Forwarded-Proto", request.url.scheme).split(",", 1)[0].strip().lower() == "https"
        ):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    app.include_router(api_router, prefix=settings.api_prefix)
    app.include_router(legacy_analytics_compat_router)
    app.include_router(legacy_analytics_intelligence_router)
    app.include_router(legacy_core_analytics_router)
    app.include_router(legacy_competitor_detection_router)
    app.include_router(legacy_feed_router)
    app.include_router(legacy_admin_mutations_router)
    app.include_router(legacy_auth_admin_router)
    app.include_router(legacy_inventory_admin_mutations_router)
    app.include_router(legacy_mutations_router)
    app.include_router(legacy_order_mutations_router)
    app.include_router(legacy_detail_reads_router)
    app.include_router(legacy_inventory_detail_router)
    app.include_router(legacy_ops_router)
    app.include_router(legacy_reads_router)
    app.include_router(legacy_runtime_router)
    app.include_router(legacy_sale_orders_router)
    app.include_router(legacy_exports_router)
    app.include_router(legacy_facts_router)
    app.include_router(legacy_product_profit_router)
    app.include_router(legacy_sidecar_ops_router)
    app.include_router(legacy_shop_analytics_router)
    app.include_router(legacy_shop_scrape_router)
    app.include_router(legacy_tiktok_router)
    app.include_router(legacy_user_cluster_router)
    app.include_router(legacy_proxy_router)

    @app.get("/healthz", tags=["health"])
    def healthz():
        return {
            "ok": True,
            "service": settings.app_name,
            "redis_connected": getattr(app.state, "redis_connected", False),
            "legacy_bridge_url": getattr(app.state, "legacy_bridge_url", None),
        }

    @app.post("/webhooks/tiktok", tags=["integrations"])
    async def tiktok_shop_webhook_alias(request: Request):
        payload = await request.json()
        return await handle_tiktok_webhook(payload, headers=dict(request.headers))

    @app.get("/product-uploads/{file_path:path}", include_in_schema=False)
    def product_uploads_file(file_path: str):
        target = (PRODUCT_UPLOADS_PATH / file_path).resolve()
        root = PRODUCT_UPLOADS_PATH.resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(target)

    if VITE_DIST_PATH.is_dir():
        PRODUCT_MEDIA_PATH.mkdir(parents=True, exist_ok=True)
        app.mount("/product-media", StaticFiles(directory=str(PRODUCT_MEDIA_PATH)), name="product-media")
        # Compatibility alias for older stored image paths.
        app.mount("/marketplace-media", StaticFiles(directory=str(PRODUCT_MEDIA_PATH)), name="marketplace-media")
        PRODUCT_UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
        app.mount("/product-uploads", StaticFiles(directory=str(PRODUCT_UPLOADS_PATH)), name="product-uploads")
        assets_path = VITE_DIST_PATH / "assets"
        if assets_path.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")
        vite_icon = VITE_DIST_PATH / "vite.svg"

        @app.get("/vite.svg", include_in_schema=False)
        def vite_svg():
            return FileResponse(vite_icon)

        @app.get("/", include_in_schema=False)
        def dashboard_root():
            return _vite_index_response()

        @app.get("/{full_path:path}", include_in_schema=False)
        def dashboard_spa_fallback(full_path: str):
            first = (full_path or "").split("/", 1)[0]
            if first in {"api", "docs", "redoc", "openapi.json", "healthz", "assets", "marketplace-media", "product-media", "product-uploads", "vite.svg"}:
                from fastapi import HTTPException

                raise HTTPException(status_code=404, detail="Not Found")
            static_file = VITE_DIST_PATH / full_path
            if static_file.is_file():
                return _vite_static_response(static_file)
            return _vite_index_response()

    return app


app = create_app()
