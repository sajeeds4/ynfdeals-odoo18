from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import mimetypes
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from cryptography.fernet import Fernet

from server.company_db import (
    add_sale_order_line,
    apply_sale_order_inventory,
    create_sale_order,
    find_product_by_code,
    get_product,
    get_setting_map,
    list_products,
    list_categories,
    list_sale_order_lines,
    list_sale_orders_fast,
    list_sale_orders,
    record_inventory_movement,
    reverse_sale_order_inventory,
    set_product_details,
    update_sale_order,
    upsert_customer,
    upsert_setting,
)
from server.config import (
    DASHBOARD_JWT_SECRET,
    DASHBOARD_TOTP_ENCRYPTION_KEY,
    TIKTOK_SHOP_API_BASE_URL,
    TIKTOK_SHOP_APP_KEY,
    TIKTOK_SHOP_APP_SECRET,
    TIKTOK_SHOP_AUTHORIZE_BASE_URL,
    TIKTOK_SHOP_AUTH_BASE_URL,
    TIKTOK_SHOP_REFRESH_URL,
    TIKTOK_SHOP_REDIRECT_URI,
    TIKTOK_SHOP_SERVICE_ID,
    TIKTOK_SHOP_TARGET_IDC,
    TIKTOK_SHOP_TOKEN_ENCRYPTION_KEY,
    TIKTOK_SHOP_TOKEN_URL,
    TIKTOK_SHOP_ORDER_IMPORT_ENABLED,
)
from server.tiktok_shop_db import (
    delete_tiktok_product_maps,
    ensure_tiktok_shop_schema,
    get_tiktok_category_map,
    get_tiktok_product_map_by_product,
    get_tiktok_product_map_by_sku,
    list_tiktok_category_maps,
    list_tiktok_product_maps,
    list_tiktok_returns,
    list_tiktok_webhook_events,
    list_inventory_movements_for_reference,
    log_tiktok_api,
    mark_tiktok_return_manual,
    mark_tiktok_return_processed,
    mark_tiktok_webhook_event,
    record_tiktok_webhook_event,
    tiktok_webhook_event_summary,
    upsert_tiktok_category_map,
    upsert_tiktok_product_map,
    upsert_tiktok_return,
)


SETTINGS_KEY = "integrations.tiktok_shop"
STATE_PREFIX = "integrations.tiktok_shop.state."
RETURNS_MONITOR_START_KEY = "integrations.tiktok_shop.returns_monitor_start_epoch"
RETURNS_MONITOR_TZ = "America/New_York"
_ORDER_LINE_CACHE_LOCK = threading.Lock()
_ORDER_LINE_CACHE: dict[str, Any] = {
    "key": None,
    "expires_at": 0.0,
    "value": None,
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _epoch_from_value(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        raw = float(value)
        return int(raw / 1000) if raw > 10_000_000_000 else int(raw)
    text = str(value).strip()
    if not text:
        return 0
    try:
        raw = float(text)
        return int(raw / 1000) if raw > 10_000_000_000 else int(raw)
    except Exception:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except Exception:
        return 0


def _local_today_start_epoch() -> int:
    now = datetime.now(ZoneInfo(RETURNS_MONITOR_TZ))
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp())


def _returns_monitor_start_epoch(payload: dict[str, Any] | None = None) -> int:
    payload = payload or {}
    explicit = _epoch_from_value(payload.get("monitor_from_epoch") or payload.get("monitor_from"))
    if explicit:
        return explicit
    settings = get_setting_map()
    stored = _epoch_from_value(settings.get(RETURNS_MONITOR_START_KEY))
    if stored:
        return stored
    start = _local_today_start_epoch()
    upsert_setting(RETURNS_MONITOR_START_KEY, str(start))
    return start


def _sale_order_epoch(order: dict[str, Any] | None) -> int:
    order = order or {}
    return _epoch_from_value(
        order.get("ordered_at")
        or order.get("sold_at")
        or order.get("created_at")
        or order.get("updated_at")
    )


def _return_row_epoch(row: dict[str, Any] | None) -> int:
    row = row or {}
    return _epoch_from_value(row.get("updated_at") or row.get("created_at"))


def _tiktok_return_event_epoch(row: dict[str, Any] | None) -> int:
    row = row or {}
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    return _epoch_from_value(
        row.get("update_time")
        or row.get("create_time")
        or raw.get("update_time")
        or raw.get("create_time")
        or _return_row_epoch(row)
    )


def _monitored_tiktok_order_reason(order: dict[str, Any] | None, monitor_start_epoch: int) -> tuple[bool, str]:
    if not order:
        return True, "unmatched"
    source = str(order.get("order_source") or "").strip().lower()
    if source not in {"tiktok_shop", "tiktok_live"}:
        return False, f"ignored_source_{source or 'blank'}"
    sold_epoch = _sale_order_epoch(order)
    if monitor_start_epoch and sold_epoch and sold_epoch < monitor_start_epoch:
        return False, "ignored_before_returns_monitor_start"
    return True, "monitored"


def _shop_order_import_enabled() -> bool:
    return bool(TIKTOK_SHOP_ORDER_IMPORT_ENABLED)


def _secret_material() -> str:
    return (
        TIKTOK_SHOP_TOKEN_ENCRYPTION_KEY
        or DASHBOARD_TOTP_ENCRYPTION_KEY
        or DASHBOARD_JWT_SECRET
        or ""
    ).strip()


def _fernet() -> Fernet:
    material = _secret_material()
    if not material:
        raise RuntimeError(
            "Set TIKTOK_SHOP_TOKEN_ENCRYPTION_KEY or DASHBOARD_JWT_SECRET before connecting TikTok Shop."
        )
    try:
        if len(material) == 44:
            return Fernet(material.encode("utf-8"))
    except Exception:
        pass
    key = base64.urlsafe_b64encode(hashlib.sha256(material.encode("utf-8")).digest())
    return Fernet(key)


def _encrypt(value: str | None) -> str:
    if not value:
        return ""
    return _fernet().encrypt(str(value).encode("utf-8")).decode("utf-8")


def _decrypt(value: str | None) -> str:
    if not value:
        return ""
    return _fernet().decrypt(str(value).encode("utf-8")).decode("utf-8")


def _shop_key(record: dict[str, Any] | None) -> str:
    record = record or {}
    return str(
        record.get("shop_cipher")
        or record.get("shop_id")
        or record.get("merchant_id")
        or record.get("seller_name")
        or ""
    ).strip()


def _tiktok_recipient_contact_fields(order: dict[str, Any] | None) -> dict[str, str]:
    order = order or {}
    recipient_address = order.get("recipient_address") if isinstance(order.get("recipient_address"), dict) else {}
    return {
        "buyer_email": _first_present(order.get("buyer_email"), order.get("email")),
        "phone": _first_present(
            recipient_address.get("phone_number"),
            recipient_address.get("phone"),
            order.get("phone_number"),
            order.get("recipient_phone"),
        ),
        "address_line_1": _first_present(recipient_address.get("address_line1"), recipient_address.get("address_line_1")),
        "address_line_2": _first_present(recipient_address.get("address_line2"), recipient_address.get("address_line_2")),
        "address_line_3": _first_present(recipient_address.get("address_line3"), recipient_address.get("address_line_3")),
        "address_line_4": _first_present(recipient_address.get("address_line4"), recipient_address.get("address_line_4")),
        "full_address": _first_present(recipient_address.get("full_address"), recipient_address.get("address_detail")),
        "city": _first_present(recipient_address.get("city"), recipient_address.get("town")),
        "state": _first_present(recipient_address.get("state")),
        "zipcode": _first_present(recipient_address.get("postal_code"), recipient_address.get("zipcode"), recipient_address.get("zip_code")),
        "country": _first_present(recipient_address.get("region_code"), recipient_address.get("region")),
    }


def _sanitize_shop_record(shop: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(shop, dict):
        return {}
    expires_at = int(shop.get("access_token_expires_at") or 0)
    refresh_expires_at = int(shop.get("refresh_token_expires_at") or 0)
    now = int(time.time())
    return {
        "key": shop.get("key") or _shop_key(shop),
        "connected": bool(shop.get("connected")),
        "active": False,
        "app_key": shop.get("app_key") or "",
        "service_id": shop.get("service_id") or "",
        "merchant_id": shop.get("merchant_id") or "",
        "seller_name": shop.get("seller_name") or "",
        "shop_id": shop.get("shop_id") or "",
        "shop_cipher": shop.get("shop_cipher") or "",
        "region": shop.get("region") or "",
        "granted_scopes": shop.get("granted_scopes") or [],
        "authorized_shops": shop.get("authorized_shops") or [],
        "access_token_expires_at": expires_at or None,
        "refresh_token_expires_at": refresh_expires_at or None,
        "access_token_valid": bool(expires_at and expires_at > now + 60),
        "refresh_token_valid": bool(refresh_expires_at and refresh_expires_at > now + 60),
        "last_connected_at": shop.get("last_connected_at"),
        "last_refreshed_at": shop.get("last_refreshed_at"),
        "last_tested_at": shop.get("last_tested_at"),
        "last_error": shop.get("last_error") or "",
        "updated_at": shop.get("updated_at"),
    }


def _active_fields_from_shop(shop: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "connected", "app_key", "service_id", "app_secret_encrypted",
        "access_token_encrypted", "refresh_token_encrypted",
        "access_token_expires_at", "refresh_token_expires_at",
        "merchant_id", "seller_name", "shop_id", "shop_cipher", "region",
        "granted_scopes", "authorized_shops", "api_base_url", "auth_base_url",
        "authorize_base_url", "token_url", "refresh_url", "target_idc",
        "last_connected_at", "last_refreshed_at", "last_tested_at", "last_error",
    }
    return {key: shop.get(key) for key in keys if key in shop}


def _normalize_shop_list(record: dict[str, Any]) -> list[dict[str, Any]]:
    shops = [shop for shop in (record.get("shops") or []) if isinstance(shop, dict)]
    if not shops and record.get("connected"):
        shops = [{**record, "key": record.get("active_shop_key") or _shop_key(record)}]
    normalized = []
    seen = set()
    for shop in shops:
        key = str(shop.get("key") or _shop_key(shop)).strip()
        if not key or key in seen:
            continue
        normalized.append({**shop, "key": key})
        seen.add(key)
    return normalized


def _set_active_shop(record: dict[str, Any], shop_key: str) -> dict[str, Any]:
    shops = _normalize_shop_list(record)
    selected = next((shop for shop in shops if str(shop.get("key") or "") == str(shop_key or "")), None)
    if not selected:
        raise ValueError("tiktok_shop_not_found")
    next_record = {**record, **_active_fields_from_shop(selected)}
    next_record["shops"] = shops
    next_record["active_shop_key"] = selected.get("key")
    next_record["connected"] = bool(selected.get("connected"))
    return next_record


def _upsert_shop_profile(record: dict[str, Any], shop: dict[str, Any], *, make_active: bool = True) -> dict[str, Any]:
    now = _utcnow()
    shop = {**shop, "connected": True, "updated_at": now}
    shop["key"] = str(shop.get("key") or _shop_key(shop)).strip()
    if not shop["key"]:
        shop["key"] = f"shop-{hashlib.sha256(json.dumps(shop, sort_keys=True, default=str).encode('utf-8')).hexdigest()[:12]}"
    shops = [existing for existing in _normalize_shop_list(record) if str(existing.get("key") or "") != shop["key"]]
    shops.append(shop)
    next_record = {**record, "shops": shops}
    return _set_active_shop(next_record, shop["key"]) if make_active else next_record


def _save_active_shop_profile(record: dict[str, Any]) -> dict[str, Any]:
    key = str(record.get("active_shop_key") or _shop_key(record)).strip()
    if not key:
        return record
    shop = {**_active_fields_from_shop(record), "key": key, "connected": bool(record.get("connected"))}
    return _upsert_shop_profile(record, shop, make_active=True)


def switch_tiktok_shop(shop_key: str) -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record:
        return {"ok": False, "error": "tiktok_shop_not_connected", "connection": {}}
    try:
        return {"ok": True, "connection": _save_record(_set_active_shop(record, shop_key))}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "connection": _sanitize_record(record)}


def _load_record(include_secrets: bool = False) -> dict[str, Any]:
    raw = get_setting_map().get(SETTINGS_KEY)
    if not raw:
        return {}
    try:
        record = json.loads(raw)
    except Exception:
        return {}
    if not include_secrets:
        return _sanitize_record(record)
    return record if isinstance(record, dict) else {}


def _save_record(record: dict[str, Any]) -> dict[str, Any]:
    record["updated_at"] = _utcnow()
    upsert_setting(SETTINGS_KEY, json.dumps(record, sort_keys=True))
    return _sanitize_record(record)


def _sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    expires_at = int(record.get("access_token_expires_at") or 0)
    refresh_expires_at = int(record.get("refresh_token_expires_at") or 0)
    now = int(time.time())
    active_key = str(record.get("active_shop_key") or _shop_key(record)).strip()
    shops = []
    for shop in _normalize_shop_list(record):
        sanitized = _sanitize_shop_record(shop)
        sanitized["active"] = bool(active_key and sanitized.get("key") == active_key)
        shops.append(sanitized)
    return {
        "connected": bool(record.get("connected")),
        "active_shop_key": active_key,
        "shops": shops,
        "app_key": record.get("app_key") or "",
        "service_id": record.get("service_id") or "",
        "merchant_id": record.get("merchant_id") or "",
        "seller_name": record.get("seller_name") or "",
        "shop_id": record.get("shop_id") or "",
        "shop_cipher": record.get("shop_cipher") or "",
        "region": record.get("region") or "",
        "api_base_url": record.get("api_base_url") or TIKTOK_SHOP_API_BASE_URL,
        "auth_base_url": record.get("auth_base_url") or TIKTOK_SHOP_AUTH_BASE_URL,
        "authorize_base_url": record.get("authorize_base_url") or TIKTOK_SHOP_AUTHORIZE_BASE_URL,
        "token_url": record.get("token_url") or TIKTOK_SHOP_TOKEN_URL,
        "refresh_url": record.get("refresh_url") or TIKTOK_SHOP_REFRESH_URL,
        "target_idc": record.get("target_idc") or TIKTOK_SHOP_TARGET_IDC,
        "granted_scopes": record.get("granted_scopes") or [],
        "authorized_shops": record.get("authorized_shops") or [],
        "access_token_expires_at": expires_at or None,
        "refresh_token_expires_at": refresh_expires_at or None,
        "access_token_valid": bool(expires_at and expires_at > now + 60),
        "refresh_token_valid": bool(refresh_expires_at and refresh_expires_at > now + 60),
        "last_connected_at": record.get("last_connected_at"),
        "last_refreshed_at": record.get("last_refreshed_at"),
        "last_error": record.get("last_error") or "",
        "updated_at": record.get("updated_at"),
    }


def tiktok_shop_status() -> dict[str, Any]:
    return {"ok": True, "connection": _load_record(include_secrets=False)}


def _default_config(payload: dict[str, Any] | None = None) -> dict[str, str]:
    payload = payload or {}
    return {
        "app_key": str(payload.get("app_key") or TIKTOK_SHOP_APP_KEY or "").strip(),
        "app_secret": str(payload.get("app_secret") or TIKTOK_SHOP_APP_SECRET or "").strip(),
        "service_id": str(payload.get("service_id") or TIKTOK_SHOP_SERVICE_ID or "").strip(),
        "redirect_uri": str(payload.get("redirect_uri") or TIKTOK_SHOP_REDIRECT_URI or "").strip(),
        "auth_base_url": str(payload.get("auth_base_url") or TIKTOK_SHOP_AUTH_BASE_URL).rstrip("/"),
        "authorize_base_url": str(payload.get("authorize_base_url") or TIKTOK_SHOP_AUTHORIZE_BASE_URL).rstrip("/"),
        "api_base_url": str(payload.get("api_base_url") or TIKTOK_SHOP_API_BASE_URL).rstrip("/"),
        "token_url": str(payload.get("token_url") or TIKTOK_SHOP_TOKEN_URL).strip(),
        "refresh_url": str(payload.get("refresh_url") or TIKTOK_SHOP_REFRESH_URL).strip(),
        "target_idc": str(payload.get("target_idc") or TIKTOK_SHOP_TARGET_IDC or "").strip(),
    }


def build_tiktok_shop_auth_url(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _default_config(payload)
    if not cfg["app_key"] and not cfg["service_id"]:
        return {"ok": False, "error": "tiktok_app_key_or_service_id_required"}
    state = str((payload or {}).get("state") or secrets.token_urlsafe(24)).strip()
    upsert_setting(f"{STATE_PREFIX}{state}", json.dumps({"state": state, "created_at": _utcnow()}))
    if cfg["service_id"]:
        params = {"service_id": cfg["service_id"], "state": state}
        if cfg["redirect_uri"]:
            params["redirect_uri"] = cfg["redirect_uri"]
        auth_url = f"{cfg['authorize_base_url']}/open/authorize?{urlencode(params)}"
    else:
        params = {"app_key": cfg["app_key"], "state": state}
        if cfg["redirect_uri"]:
            params["redirect_uri"] = cfg["redirect_uri"]
        auth_url = f"{cfg['auth_base_url']}/api/v2/token/authorize?{urlencode(params)}"
    return {
        "ok": True,
        "auth_url": auth_url,
        "state": state,
        "redirect_uri": cfg["redirect_uri"],
        "app_key": cfg["app_key"],
        "service_id": cfg["service_id"],
    }


def _normalize_token_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    token_data = data.get("data") if isinstance(data.get("data"), dict) else data
    access_token = token_data.get("access_token") or token_data.get("accessToken")
    refresh_token = token_data.get("refresh_token") or token_data.get("refreshToken")
    now = int(time.time())

    def as_expiry(value, fallback_seconds=0):
        try:
            num = int(value or 0)
        except Exception:
            num = 0
        if num and num < 10000000000:
            return now + num
        return num or (now + fallback_seconds if fallback_seconds else 0)

    return {
        "access_token": access_token or "",
        "refresh_token": refresh_token or "",
        "access_token_expires_at": as_expiry(
            token_data.get("access_token_expire_in")
            or token_data.get("access_token_expire_at")
            or token_data.get("expires_in"),
            fallback_seconds=5 * 24 * 60 * 60,
        ),
        "refresh_token_expires_at": as_expiry(
            token_data.get("refresh_token_expire_in")
            or token_data.get("refresh_token_expire_at")
            or token_data.get("refresh_expires_in"),
        ),
        "shop_id": str(token_data.get("shop_id") or token_data.get("seller_id") or "").strip(),
        "shop_cipher": str(token_data.get("shop_cipher") or token_data.get("cipher") or "").strip(),
        "merchant_id": str(token_data.get("merchant_id") or "").strip(),
        "seller_name": str(token_data.get("seller_name") or "").strip(),
        "region": str(token_data.get("seller_base_region") or token_data.get("shop_region") or "").strip(),
        "granted_scopes": token_data.get("granted_scopes") if isinstance(token_data.get("granted_scopes"), list) else [],
    }


async def _exchange_token(cfg: dict[str, str], payload: dict[str, Any], refresh_token: str | None = None) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if cfg["target_idc"]:
        headers["x-tt-target-idc"] = cfg["target_idc"]
    params = {
        "app_key": cfg["app_key"],
        "app_secret": cfg["app_secret"],
    }
    if refresh_token:
        params.update({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        })
    elif payload.get("auth_code"):
        params.update({
            "grant_type": "authorized_code",
            "auth_code": str(payload.get("auth_code") or "").strip(),
        })
    else:
        params.update({
            "grant_type": "access_token",
            "merchant_id": str(payload.get("merchant_id") or "").strip(),
        })
    url = cfg["refresh_url"] if refresh_token else cfg["token_url"]
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params, headers=headers)
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text}
    if response.status_code >= 400:
        log_tiktok_api(
            "auth.refresh" if refresh_token else "auth.token",
            "GET",
            url,
            status_code=response.status_code,
            ok=False,
            request={k: ("***" if k in {"app_secret", "refresh_token", "auth_code"} else v) for k, v in params.items()},
            response=data,
            error=str(data),
        )
        raise RuntimeError(f"TikTok token request failed: HTTP {response.status_code} {data}")
    if isinstance(data, dict) and data.get("code") not in (None, 0, "0"):
        log_tiktok_api(
            "auth.refresh" if refresh_token else "auth.token",
            "GET",
            url,
            status_code=response.status_code,
            ok=False,
            request={k: ("***" if k in {"app_secret", "refresh_token", "auth_code"} else v) for k, v in params.items()},
            response=data,
            error=str(data),
        )
        raise RuntimeError(f"TikTok token request failed: {data}")
    log_tiktok_api(
        "auth.refresh" if refresh_token else "auth.token",
        "GET",
        url,
        status_code=response.status_code,
        ok=True,
        request={k: ("***" if k in {"app_secret", "refresh_token", "auth_code"} else v) for k, v in params.items()},
        response=data,
    )
    return data


def _tiktok_sign(path: str, params: dict[str, Any], app_secret: str, body: dict[str, Any] | None = None) -> str:
    sign_params = {
        str(key): str(value)
        for key, value in (params or {}).items()
        if value is not None and str(key) not in {"access_token", "sign"}
    }
    sign_source = path + "".join(f"{key}{sign_params[key]}" for key in sorted(sign_params))
    if body is not None:
        sign_source += json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    sign_source = f"{app_secret}{sign_source}{app_secret}"
    return hmac.new(app_secret.encode("utf-8"), sign_source.encode("utf-8"), hashlib.sha256).hexdigest()


def _redact_tiktok_body(body: Any) -> Any:
    if isinstance(body, dict):
        redacted = {}
        for key, value in body.items():
            if key in {"data"} and isinstance(value, str) and len(value) > 128:
                redacted[key] = f"<base64:{len(value)} chars>"
            else:
                redacted[key] = _redact_tiktok_body(value)
        return redacted
    if isinstance(body, list):
        return [_redact_tiktok_body(item) for item in body]
    return body


def _enqueue_tiktok_shop_sync_task(hours_back: int = 72, page_size: int = 50, max_pages: int = 5) -> bool:
    try:
        from app.tasks.business_tasks import sync_tiktok_shop_orders as sync_tiktok_shop_orders_task

        sync_tiktok_shop_orders_task.delay(hours_back, page_size, max_pages)
        return True
    except Exception:
        return False


async def _signed_tiktok_get(record: dict[str, Any], path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return await _signed_tiktok_request(record, "GET", path, params=params)


async def _signed_tiktok_request(
    record: dict[str, Any],
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    operation: str | None = None,
) -> dict[str, Any]:
    app_secret = _decrypt(record.get("app_secret_encrypted"))
    access_token = _decrypt(record.get("access_token_encrypted"))
    if not app_secret or not access_token:
        raise RuntimeError("TikTok Shop credentials are incomplete.")
    if record.get("access_token_expires_at") and int(record.get("access_token_expires_at") or 0) <= int(time.time()) + 90:
        refreshed = await refresh_tiktok_shop_token()
        if refreshed.get("ok"):
            record = _load_record(include_secrets=True)
            access_token = _decrypt(record.get("access_token_encrypted"))
    query = {
        "app_key": record.get("app_key"),
        "timestamp": int(time.time()),
        "access_token": access_token,
        **(params or {}),
    }
    query["sign"] = _tiktok_sign(path, query, app_secret, body if method.upper() != "GET" else None)
    headers = {"x-tts-access-token": access_token, "Content-Type": "application/json"}
    url = f"{(record.get('api_base_url') or TIKTOK_SHOP_API_BASE_URL).rstrip('/')}{path}"
    status_code = None
    data: dict[str, Any]
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(method.upper(), url, params=query, json=body if body is not None else None, headers=headers)
        status_code = response.status_code
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text}
    ok = response.status_code < 400 and (not isinstance(data, dict) or data.get("code") in (None, 0, "0"))
    log_tiktok_api(
        operation or path.strip("/").replace("/", "."),
        method.upper(),
        path,
        status_code=status_code,
        ok=ok,
        request={"params": {k: ("***" if k in {"access_token", "sign"} else v) for k, v in query.items()}, "body": _redact_tiktok_body(body)},
        response=data,
        error=None if ok else str(data),
    )
    if response.status_code >= 400:
        raise RuntimeError(f"TikTok API request failed: HTTP {response.status_code} {data}")
    if isinstance(data, dict) and data.get("code") not in (None, 0, "0"):
        raise RuntimeError(f"TikTok API request failed: {data}")
    return data


def _normalize_shops(data: dict[str, Any]) -> list[dict[str, Any]]:
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    shops = root.get("shops") if isinstance(root, dict) else []
    if not isinstance(shops, list):
        shops = []
    normalized = []
    for shop in shops:
        if not isinstance(shop, dict):
            continue
        normalized.append({
            "shop_id": str(shop.get("id") or shop.get("shop_id") or "").strip(),
            "shop_cipher": str(shop.get("cipher") or shop.get("shop_cipher") or "").strip(),
            "name": str(shop.get("name") or shop.get("shop_name") or "").strip(),
            "region": str(shop.get("region") or shop.get("seller_base_region") or "").strip(),
        })
    return normalized


async def connect_tiktok_shop(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = _default_config(payload)
    existing = _load_record(include_secrets=True)
    if not cfg["app_secret"] and existing.get("app_secret_encrypted"):
        cfg["app_secret"] = _decrypt(existing.get("app_secret_encrypted"))
    if not cfg["app_key"] or not cfg["app_secret"]:
        return {"ok": False, "error": "tiktok_app_credentials_required"}
    if not payload.get("auth_code") and not payload.get("merchant_id") and not payload.get("access_token"):
        return {"ok": False, "error": "auth_code_or_merchant_id_required"}
    try:
        token_payload = {
            "access_token": str(payload.get("access_token") or "").strip(),
            "refresh_token": str(payload.get("refresh_token") or "").strip(),
            "access_token_expires_at": int(payload.get("access_token_expires_at") or 0),
            "refresh_token_expires_at": int(payload.get("refresh_token_expires_at") or 0),
            "shop_id": str(payload.get("shop_id") or "").strip(),
            "shop_cipher": str(payload.get("shop_cipher") or "").strip(),
            "merchant_id": str(payload.get("merchant_id") or "").strip(),
        }
        if not token_payload["access_token"]:
            token_payload.update(_normalize_token_payload(await _exchange_token(cfg, payload)))
        record = {
            "connected": True,
            "app_key": cfg["app_key"],
            "service_id": cfg["service_id"],
            "app_secret_encrypted": _encrypt(cfg["app_secret"]),
            "access_token_encrypted": _encrypt(token_payload["access_token"]),
            "refresh_token_encrypted": _encrypt(token_payload["refresh_token"]),
            "access_token_expires_at": token_payload["access_token_expires_at"],
            "refresh_token_expires_at": token_payload["refresh_token_expires_at"],
            "merchant_id": token_payload["merchant_id"] or str(payload.get("merchant_id") or "").strip(),
            "seller_name": token_payload.get("seller_name") or str(payload.get("seller_name") or "").strip(),
            "shop_id": token_payload["shop_id"] or str(payload.get("shop_id") or "").strip(),
            "shop_cipher": token_payload["shop_cipher"] or str(payload.get("shop_cipher") or "").strip(),
            "region": token_payload.get("region") or str(payload.get("region") or "").strip(),
            "granted_scopes": token_payload.get("granted_scopes") or [],
            "api_base_url": cfg["api_base_url"],
            "auth_base_url": cfg["auth_base_url"],
            "authorize_base_url": cfg["authorize_base_url"],
            "token_url": cfg["token_url"],
            "refresh_url": cfg["refresh_url"],
            "target_idc": cfg["target_idc"],
            "last_connected_at": _utcnow(),
            "last_error": "",
        }
        make_active = bool(payload.get("make_active"))
        if not _normalize_shop_list(existing):
            make_active = True
        return {"ok": True, "connection": _save_record(_upsert_shop_profile(existing, record, make_active=make_active))}
    except Exception as exc:
        current = _load_record(include_secrets=True)
        current["last_error"] = str(exc)
        if current:
            _save_record(current)
        return {"ok": False, "error": str(exc), "connection": _sanitize_record(current)}


async def refresh_tiktok_shop_token() -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected"}
    cfg = _default_config({
        "app_key": record.get("app_key"),
        "app_secret": _decrypt(record.get("app_secret_encrypted")),
        "token_url": record.get("token_url"),
        "refresh_url": record.get("refresh_url"),
        "target_idc": record.get("target_idc"),
        "api_base_url": record.get("api_base_url"),
        "auth_base_url": record.get("auth_base_url"),
        "authorize_base_url": record.get("authorize_base_url"),
    })
    try:
        token_payload = _normalize_token_payload(
            await _exchange_token(
                cfg,
                {"merchant_id": record.get("merchant_id")},
                refresh_token=_decrypt(record.get("refresh_token_encrypted")),
            )
        )
        if token_payload.get("access_token"):
            record["access_token_encrypted"] = _encrypt(token_payload["access_token"])
        if token_payload.get("refresh_token"):
            record["refresh_token_encrypted"] = _encrypt(token_payload["refresh_token"])
        record["access_token_expires_at"] = token_payload.get("access_token_expires_at") or record.get("access_token_expires_at")
        record["refresh_token_expires_at"] = token_payload.get("refresh_token_expires_at") or record.get("refresh_token_expires_at")
        record["last_refreshed_at"] = _utcnow()
        record["last_error"] = ""
        return {"ok": True, "connection": _save_record(_save_active_shop_profile(record))}
    except Exception as exc:
        record["last_error"] = str(exc)
        _save_record(record)
        return {"ok": False, "error": str(exc), "connection": _sanitize_record(record)}


async def test_tiktok_shop_connection() -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected", "connection": _sanitize_record(record)}
    try:
        data = await _signed_tiktok_get(record, "/authorization/202309/shops")
        shops = _normalize_shops(data)
        if shops:
            primary = shops[0]
            record["shop_id"] = record.get("shop_id") or primary.get("shop_id")
            record["shop_cipher"] = record.get("shop_cipher") or primary.get("shop_cipher")
            record["region"] = record.get("region") or primary.get("region")
        record["authorized_shops"] = shops
        record["last_error"] = ""
        record["last_tested_at"] = _utcnow()
        return {"ok": True, "shops": shops, "connection": _save_record(_save_active_shop_profile(record))}
    except Exception as exc:
        record["last_error"] = str(exc)
        _save_record(record)
        return {"ok": False, "error": str(exc), "connection": _sanitize_record(record)}


def list_tiktok_mappings() -> dict[str, Any]:
    ensure_tiktok_shop_schema()
    return {
        "ok": True,
        "categories": list_tiktok_category_maps(),
        "products": list_tiktok_product_maps(),
    }


def list_recent_tiktok_webhooks(limit: int = 100, event_type: str | None = None, processed: bool | None = None) -> dict[str, Any]:
    ensure_tiktok_shop_schema()
    return {
        "ok": True,
        "summary": tiktok_webhook_event_summary(),
        "events": list_tiktok_webhook_events(limit=limit, event_type=event_type, processed=processed),
    }


async def fetch_tiktok_categories(parent_id: str | None = None) -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected"}
    params = {"category_version": "v2"}
    data = await _signed_tiktok_get(record, "/product/202309/global_categories", params=params)
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    categories = root.get("categories") if isinstance(root, dict) else []
    if parent_id:
        categories = [row for row in categories if str((row or {}).get("parent_id") or "") == str(parent_id)]
    return {"ok": True, "categories": categories or [], "raw": data}


async def fetch_tiktok_category_rules(category_id: str) -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected"}
    category_id = str(category_id or "").strip()
    if not category_id:
        return {"ok": False, "error": "category_id_required"}
    params = {"category_version": "v2"}
    cipher = _shop_cipher(record)
    if cipher:
        params["shop_cipher"] = cipher
    data = await _signed_tiktok_get(record, f"/product/202309/categories/{category_id}/rules", params=params)
    return {"ok": True, "rules": data.get("data") if isinstance(data.get("data"), dict) else data, "raw": data}


async def fetch_tiktok_category_attributes(category_id: str) -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected"}
    category_id = str(category_id or "").strip()
    if not category_id:
        return {"ok": False, "error": "category_id_required"}
    params = {"category_version": "v2"}
    cipher = _shop_cipher(record)
    if cipher:
        params["shop_cipher"] = cipher
    data = await _signed_tiktok_get(record, f"/product/202309/categories/{category_id}/attributes", params=params)
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    attributes = root.get("attributes") if isinstance(root, dict) else []
    return {"ok": True, "attributes": attributes or [], "raw": data}


async def fetch_tiktok_brands(brand_name: str, category_id: str | None = None) -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected"}
    brand_name = str(brand_name or "").strip()
    if not brand_name:
        return {"ok": False, "error": "brand_name_required"}
    params = {"page_size": 20, "brand_name": brand_name}
    category_id = str(category_id or "").strip()
    if category_id:
        params["category_id"] = category_id
        params["category_version"] = "v2"
    cipher = _shop_cipher(record)
    if cipher:
        params["shop_cipher"] = cipher
    data = await _signed_tiktok_get(record, "/product/202309/brands", params=params)
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    brands = root.get("brands") if isinstance(root, dict) else []
    return {"ok": True, "brands": brands or [], "raw": data}


async def fetch_tiktok_warehouses() -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected"}
    params = {}
    cipher = _shop_cipher(record)
    if cipher:
        params["shop_cipher"] = cipher
    data = await _signed_tiktok_get(record, "/logistics/202309/warehouses", params=params)
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    warehouses = root.get("warehouses") if isinstance(root, dict) else []
    return {"ok": True, "warehouses": warehouses or [], "raw": data}


async def _default_sales_warehouse_id(record: dict[str, Any]) -> str:
    params = {}
    cipher = _shop_cipher(record)
    if cipher:
        params["shop_cipher"] = cipher
    data = await _signed_tiktok_get(record, "/logistics/202309/warehouses", params=params)
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    warehouses = root.get("warehouses") if isinstance(root, dict) else []
    sales_warehouses = [
        row for row in warehouses
        if isinstance(row, dict)
        and row.get("effect_status") == "ENABLED"
        and row.get("type") == "SALES_WAREHOUSE"
        and row.get("id")
    ]
    default = next((row for row in sales_warehouses if row.get("is_default")), None) or (sales_warehouses[0] if sales_warehouses else None)
    return str((default or {}).get("id") or "").strip()


def _normalize_tiktok_package(row: dict[str, Any] | None) -> dict[str, Any]:
    row = row if isinstance(row, dict) else {}
    orders = row.get("orders") if isinstance(row.get("orders"), list) else []
    order_ids = [str(item.get("id") or "").strip() for item in orders if isinstance(item, dict) and str(item.get("id") or "").strip()]
    sku_names: list[str] = []
    total_quantity = 0
    for order in orders:
        if not isinstance(order, dict):
            continue
        for sku in order.get("skus") if isinstance(order.get("skus"), list) else []:
            if not isinstance(sku, dict):
                continue
            name = str(sku.get("name") or "").strip()
            if name:
                sku_names.append(name)
            try:
                total_quantity += int(sku.get("quantity") or 0)
            except Exception:
                pass
    return {
        "id": str(row.get("id") or "").strip(),
        "status": str(row.get("status") or "").strip(),
        "tracking_number": str(row.get("tracking_number") or "").strip(),
        "shipping_provider_id": str(row.get("shipping_provider_id") or "").strip(),
        "shipping_provider_name": str(row.get("shipping_provider_name") or "").strip(),
        "order_ids": order_ids,
        "order_count": len(order_ids),
        "sku_names": sku_names,
        "sku_count": len(sku_names),
        "quantity_total": total_quantity,
        "create_time": row.get("create_time"),
        "update_time": row.get("update_time"),
        "raw": row,
    }


async def fetch_tiktok_packages(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected", "packages": [], "pages_fetched": 0}
    page_size = max(1, min(int(payload.get("page_size") or 50), 50))
    max_pages = max(1, min(int(payload.get("max_pages") or 3), 20))
    params: dict[str, Any] = {"page_size": page_size}
    cipher = _shop_cipher(record)
    if cipher:
        params["shop_cipher"] = cipher
    package_ids = payload.get("package_ids")
    if package_ids is None and payload.get("package_id"):
        package_ids = [payload.get("package_id")]
    if isinstance(package_ids, (str, int)):
        package_ids = [package_ids]
    package_ids = [str(value or "").strip() for value in (package_ids or []) if str(value or "").strip()]
    body: dict[str, Any] = {}
    if package_ids:
        body["package_ids"] = package_ids
    package_status = str(payload.get("package_status") or "").strip().upper()
    if package_status:
        body["package_status"] = package_status
    page_token = str(payload.get("page_token") or "").strip()
    pages_fetched = 0
    packages: list[dict[str, Any]] = []
    raw_pages: list[dict[str, Any]] = []
    for _ in range(max_pages):
        request_params = dict(params)
        if page_token:
            request_params["page_token"] = page_token
        data = await _signed_tiktok_request(
            record,
            "POST",
            "/fulfillment/202309/packages/search",
            params=request_params,
            body=body,
            operation="packages.search",
        )
        raw_pages.append(data)
        root = data.get("data") if isinstance(data.get("data"), dict) else data
        page_rows = root.get("packages") if isinstance(root, dict) else []
        if isinstance(page_rows, list):
            packages.extend(_normalize_tiktok_package(row) for row in page_rows if isinstance(row, dict))
        page_token = str((root or {}).get("next_page_token") or "").strip()
        pages_fetched += 1
        if not page_token or package_ids:
            break
    return {
        "ok": True,
        "packages": packages,
        "pages_fetched": pages_fetched,
        "next_page_token": page_token or "",
        "raw": raw_pages[-1] if raw_pages else {},
    }


async def fetch_tiktok_package_shipping_document(package_id: str, document_type: str = "SHIPPING_LABEL") -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected"}
    package_id = str(package_id or "").strip()
    if not package_id:
        return {"ok": False, "error": "package_id_required"}
    document_type = str(document_type or "SHIPPING_LABEL").strip().upper()
    allowed_types = {
        "SHIPPING_LABEL",
        "PACKING_SLIP",
        "SHIPPING_LABEL_AND_PACKING_SLIP",
        "SHIPPING_LABEL_PICTURE",
        "HAZMAT_LABEL",
        "INVOICE_LABEL",
    }
    if document_type not in allowed_types:
        return {"ok": False, "error": "invalid_document_type", "allowed_types": sorted(allowed_types)}
    params: dict[str, Any] = {
        "document_type": document_type,
    }
    cipher = _shop_cipher(record)
    if cipher:
        params["shop_cipher"] = cipher
    data = await _signed_tiktok_get(
        record,
        f"/fulfillment/202309/packages/{package_id}/shipping_documents",
        params=params,
    )
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    return {
        "ok": True,
        "package_id": package_id,
        "document_type": document_type,
        "document": root or {},
        "raw": data,
    }


def _clean_tiktok_cs_payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {key: value for key, value in dict(payload or {}).items() if value not in (None, "")}


async def _tiktok_customer_service_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    operation: str | None = None,
) -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected"}
    request_params = _clean_tiktok_cs_payload(params)
    cipher = _shop_cipher(record)
    if cipher and "shop_cipher" not in request_params:
        request_params["shop_cipher"] = cipher
    try:
        data = await _signed_tiktok_request(
            record,
            method,
            path,
            params=request_params,
            body=_clean_tiktok_cs_payload(body) if body is not None else None,
            operation=operation or f"customer_service.{path.strip('/').replace('/', '.')}",
        )
        return {"ok": True, "data": data.get("data") if isinstance(data, dict) else data, "raw": data}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": path, "method": method.upper()}


async def tiktok_customer_service_agent_settings() -> dict[str, Any]:
    return await _tiktok_customer_service_request(
        "GET",
        "/customer_service/202309/agents/settings",
        operation="customer_service.agent_settings.get",
    )


async def update_tiktok_customer_service_agent_settings(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return await _tiktok_customer_service_request(
        "PUT",
        "/customer_service/202309/agents/settings",
        body=payload or {},
        operation="customer_service.agent_settings.update",
    )


async def search_tiktok_customer_service_sessions(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return await _tiktok_customer_service_request(
        "POST",
        "/customer_service/202309/sessions",
        body=payload or {},
        operation="customer_service.sessions.search",
    )


async def get_tiktok_customer_service_conversations(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(payload or {})
    params = {
        "page_size": max(1, min(int(payload.get("page_size") or 20), 100)),
        "page_token": payload.get("page_token"),
        "status": payload.get("status"),
    }
    return await _tiktok_customer_service_request(
        "GET",
        "/customer_service/202309/conversations",
        params=params,
        operation="customer_service.conversations.list",
    )


async def create_tiktok_customer_service_conversation(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return await _tiktok_customer_service_request(
        "POST",
        "/customer_service/202309/conversations",
        body=payload or {},
        operation="customer_service.conversations.create",
    )


async def get_tiktok_customer_service_conversation(conversation_id: str) -> dict[str, Any]:
    clean_id = str(conversation_id or "").strip()
    if not clean_id:
        return {"ok": False, "error": "conversation_id_required"}
    return await _tiktok_customer_service_request(
        "GET",
        f"/customer_service/202309/conversations/{clean_id}",
        operation="customer_service.conversations.get",
    )


async def get_tiktok_customer_service_messages(conversation_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_id = str(conversation_id or "").strip()
    if not clean_id:
        return {"ok": False, "error": "conversation_id_required"}
    payload = dict(payload or {})
    params = {
        "page_size": max(1, min(int(payload.get("page_size") or 50), 100)),
        "page_token": payload.get("page_token"),
    }
    return await _tiktok_customer_service_request(
        "GET",
        f"/customer_service/202309/conversations/{clean_id}/messages",
        params=params,
        operation="customer_service.messages.list",
    )


async def send_tiktok_customer_service_message(conversation_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_id = str(conversation_id or "").strip()
    if not clean_id:
        return {"ok": False, "error": "conversation_id_required"}
    body = dict(payload or {})
    if not body.get("message") and body.get("content"):
        body["message"] = body.get("content")
    return await _tiktok_customer_service_request(
        "POST",
        f"/customer_service/202309/conversations/{clean_id}/messages",
        body=body,
        operation="customer_service.messages.send",
    )


async def read_tiktok_customer_service_messages(conversation_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_id = str(conversation_id or "").strip()
    if not clean_id:
        return {"ok": False, "error": "conversation_id_required"}
    return await _tiktok_customer_service_request(
        "POST",
        f"/customer_service/202309/conversations/{clean_id}/read",
        body=payload or {},
        operation="customer_service.messages.read",
    )


async def search_tiktok_customer_service_coupons(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return await _tiktok_customer_service_request(
        "POST",
        "/customer_service/202309/coupons/search",
        body=payload or {},
        operation="customer_service.coupons.search",
    )


async def get_tiktok_customer_service_coupon(coupon_id: str) -> dict[str, Any]:
    clean_id = str(coupon_id or "").strip()
    if not clean_id:
        return {"ok": False, "error": "coupon_id_required"}
    return await _tiktok_customer_service_request(
        "GET",
        f"/customer_service/202309/coupons/{clean_id}",
        operation="customer_service.coupons.get",
    )


async def get_tiktok_customer_service_performance(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return await _tiktok_customer_service_request(
        "GET",
        "/customer_service/202309/performance",
        params=payload or {},
        operation="customer_service.performance.get",
    )


async def save_tiktok_category_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    category_id = str(payload.get("tiktok_category_id") or payload.get("category_id") or "").strip()
    if not category_id:
        return {"ok": False, "error": "tiktok_category_id_required"}
    is_leaf = bool(payload.get("is_leaf", True))
    if not is_leaf:
        return {"ok": False, "error": "tiktok_category_must_be_leaf"}
    rules = payload.get("rules")
    if rules is None and payload.get("fetch_rules", True):
        try:
            rules_result = await fetch_tiktok_category_rules(category_id)
            if rules_result.get("ok"):
                rules = rules_result.get("rules")
        except Exception as exc:
            rules = {"fetch_error": str(exc)}
    attributes = payload.get("attributes")
    if attributes is None and payload.get("fetch_attributes", True):
        try:
            attributes_result = await fetch_tiktok_category_attributes(category_id)
            if attributes_result.get("ok"):
                attributes = attributes_result.get("attributes")
        except Exception as exc:
            attributes = {"fetch_error": str(exc)}
    mapping_payload = {"rules": rules or {}, "attributes": attributes or []}
    row = upsert_tiktok_category_map(
        internal_category_id=payload.get("internal_category_id"),
        internal_category_name=payload.get("internal_category_name"),
        tiktok_category_id=category_id,
        tiktok_category_name=payload.get("tiktok_category_name"),
        is_leaf=True,
        rules=mapping_payload,
    )
    return {"ok": True, "mapping": row}


def _shop_cipher(record: dict[str, Any]) -> str:
    return str(record.get("shop_cipher") or record.get("shop_id") or "").strip()


def _first_present(*values) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalize_match_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_barcode_key(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _first_list(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list):
            return value
    return []


def _tiktok_root(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("data") if isinstance(data.get("data"), dict) else data


def _tiktok_product_rows(data: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    root = _tiktok_root(data)
    rows = _first_list(
        root.get("products") if isinstance(root, dict) else None,
        root.get("product_list") if isinstance(root, dict) else None,
        root.get("items") if isinstance(root, dict) else None,
        root.get("list") if isinstance(root, dict) else None,
    )
    next_page_token = ""
    if isinstance(root, dict):
        next_page_token = _first_present(root.get("next_page_token"), root.get("page_token"), root.get("next_token"))
    return [row for row in rows if isinstance(row, dict)], next_page_token


def _tiktok_order_rows(data: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    root = _tiktok_root(data)
    rows = _first_list(
        root.get("orders") if isinstance(root, dict) else None,
        root.get("order_list") if isinstance(root, dict) else None,
        root.get("list") if isinstance(root, dict) else None,
        root.get("items") if isinstance(root, dict) else None,
    )
    next_page_token = ""
    if isinstance(root, dict):
        next_page_token = _first_present(root.get("next_page_token"), root.get("page_token"), root.get("next_token"))
    return [row for row in rows if isinstance(row, dict)], next_page_token


def _tiktok_return_rows(data: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    root = _tiktok_root(data)
    rows = _first_list(
        root.get("returns") if isinstance(root, dict) else None,
        root.get("return_orders") if isinstance(root, dict) else None,
        root.get("return_requests") if isinstance(root, dict) else None,
        root.get("data") if isinstance(root, dict) else None,
    )
    next_page_token = _first_present(
        root.get("next_page_token") if isinstance(root, dict) else "",
        root.get("next_page") if isinstance(root, dict) else "",
        root.get("page_token") if isinstance(root, dict) else "",
    )
    return [row for row in rows if isinstance(row, dict)], next_page_token


def _tiktok_product_id(row: dict[str, Any]) -> str:
    return _first_present(row.get("id"), row.get("product_id"))


def _tiktok_category_from_row(row: dict[str, Any]) -> tuple[str, str]:
    chain_rows = _first_list(row.get("category_chains"), row.get("categories"))
    leaf = None
    if chain_rows:
        last_chain = chain_rows[-1] if isinstance(chain_rows[-1], dict) else {}
        categories = _first_list(last_chain.get("categories"), last_chain.get("category_nodes"))
        if categories:
            leaf = categories[-1] if isinstance(categories[-1], dict) else None
        elif last_chain:
            leaf = last_chain
    return (
        _first_present(row.get("category_id"), (leaf or {}).get("id"), (leaf or {}).get("category_id")),
        _first_present(row.get("category_name"), (leaf or {}).get("local_name"), (leaf or {}).get("name"), (leaf or {}).get("category_name")),
    )


def _tiktok_sku_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        sku for sku in _first_list(row.get("skus"), row.get("sku_list"), row.get("seller_skus"))
        if isinstance(sku, dict)
    ]


def _tiktok_sku_id(sku: dict[str, Any]) -> str:
    return _first_present(sku.get("id"), sku.get("sku_id"))


def _tiktok_seller_sku(sku: dict[str, Any]) -> str:
    return _first_present(sku.get("seller_sku"), sku.get("seller_sku_id"), sku.get("external_sku_id"))


def _tiktok_identifier_code(sku: dict[str, Any]) -> tuple[str, str]:
    code_row = _first_dict(sku.get("product_identifier_code"), sku.get("identifier_code"), sku.get("identifier"))
    if code_row:
        return (
            _first_present(code_row.get("identifier_code"), code_row.get("code"), code_row.get("value")),
            _first_present(code_row.get("identifier_code_type"), code_row.get("type")),
        )
    return (
        _first_present(sku.get("identifier_code"), sku.get("ean"), sku.get("barcode"), sku.get("gtin")),
        _first_present(sku.get("identifier_code_type"), sku.get("barcode_type")),
    )


def _tiktok_price_amount(sku: dict[str, Any]) -> str:
    price = sku.get("price")
    if isinstance(price, dict):
        return _first_present(price.get("amount"), price.get("original_price"), price.get("sale_price"))
    return _first_present(price, sku.get("retail_price"))


def _tiktok_inventory_qty(sku: dict[str, Any]) -> str:
    inventory = _first_list(sku.get("inventory"), sku.get("inventories"))
    quantities = []
    for row in inventory:
        if isinstance(row, dict):
            value = row.get("quantity")
            if value not in (None, ""):
                try:
                    quantities.append(float(value))
                except Exception:
                    pass
    if quantities:
        return str(int(sum(quantities)))
    return _first_present(sku.get("quantity"), sku.get("stock"))


def _tiktok_weight_oz(row: dict[str, Any]) -> str:
    weight = _first_dict(row.get("package_weight"), row.get("weight"))
    value = _first_present(weight.get("value"), weight.get("amount"))
    if not value:
        for fallback_key in ("tiktok_package_weight_oz", "size_oz", "volume_oz", "package_weight_oz", "weight_oz"):
            fallback_value = _first_present(row.get(fallback_key))
            if fallback_value:
                return fallback_value
        return ""
    try:
        number = float(value)
    except Exception:
        return value
    unit = _first_present(weight.get("unit"), weight.get("weight_unit")).upper()
    if unit in {"POUND", "POUNDS", "LB", "LBS"}:
        number *= 16
    elif unit in {"KILOGRAM", "KILOGRAMS", "KG"}:
        number *= 35.27396195
    elif unit in {"GRAM", "GRAMS", "G"}:
        number *= 0.03527396195
    return str(round(number, 3)).rstrip("0").rstrip(".")


def _tiktok_image_text(row: dict[str, Any]) -> str:
    images = _first_list(row.get("main_images"), row.get("images"), row.get("product_images"))
    values = []
    for image in images:
        if isinstance(image, dict):
            text = _first_present(image.get("uri"), image.get("url"), image.get("thumb_url"))
        else:
            text = _first_present(image)
        if text and text not in values:
            values.append(text)
    return "\n".join(values)


def _tiktok_brand_name(row: dict[str, Any]) -> str:
    brand = row.get("brand")
    if isinstance(brand, dict):
        return _first_present(brand.get("name"), brand.get("brand_name"), brand.get("id"))
    return _first_present(row.get("brand_name"), brand)


_TIKTOK_ATTRIBUTE_TO_FIELD = {
    "pack type": "tiktok_pack_type",
    "scent": "tiktok_scent",
    "region of origin": "tiktok_region_of_origin",
    "product form": "tiktok_product_form",
    "edition": "tiktok_edition",
    "contains alcohol or aerosol": "tiktok_contains_alcohol_or_aerosol",
    "manufacturer": "tiktok_manufacturer",
    "shelf life": "tiktok_shelf_life",
    "inactive ingredients": "tiktok_inactive_ingredients",
    "(inactive) ingredients": "tiktok_inactive_ingredients",
    "age group": "tiktok_age_group",
    "item name": "tiktok_item_name",
    "feature": "tiktok_feature",
    "fragrance concentration": "tiktok_fragrance_concentration",
    "material type free": "tiktok_material_type_free",
    "ingredients": "tiktok_ingredients",
    "container type": "tiktok_container_type",
    "allergen information": "tiktok_allergen_information",
    "ingredient feature": "tiktok_ingredient_feature",
    "volume": "tiktok_volume",
}


def _attribute_value_text(attribute: dict[str, Any]) -> str:
    values = _first_list(attribute.get("values"), attribute.get("attribute_values"), attribute.get("value"))
    text_values = []
    for value in values:
        if isinstance(value, dict):
            text = _first_present(value.get("name"), value.get("value_name"), value.get("value"), value.get("id"))
        else:
            text = _first_present(value)
        if text:
            text_values.append(text)
    if text_values:
        return ", ".join(text_values)
    return _first_present(attribute.get("value"), attribute.get("name"))


def _extract_tiktok_attribute_fields(row: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    attributes = _first_list(row.get("product_attributes"), row.get("attributes"), row.get("category_attributes"))
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        name = _first_present(attribute.get("name"), attribute.get("attribute_name")).lower().strip()
        field_name = _TIKTOK_ATTRIBUTE_TO_FIELD.get(name)
        if not field_name:
            continue
        text = _attribute_value_text(attribute)
        if text:
            updates[field_name] = text
    return updates


def _draft_product_to_tiktok_fields(row: dict[str, Any], sku: dict[str, Any]) -> dict[str, Any]:
    identifier_code, identifier_type = _tiktok_identifier_code(sku)
    category_id, category_name = _tiktok_category_from_row(row)
    updates: dict[str, Any] = {
        "tiktok_title": _first_present(row.get("title"), row.get("name")),
        "tiktok_category_id": category_id,
        "tiktok_category_name": category_name,
        "tiktok_brand": _tiktok_brand_name(row),
        "tiktok_search_keywords": _first_present(row.get("search_keywords"), row.get("keywords")),
        "tiktok_image_urls": _tiktok_image_text(row),
        "tiktok_description": _first_present(row.get("description"), row.get("desc")),
        "tiktok_highlights": "\n".join(str(item).strip() for item in _first_list(row.get("highlights"), row.get("product_highlights")) if str(item).strip()),
        "tiktok_quantity": _tiktok_inventory_qty(sku),
        "tiktok_retail_price": _tiktok_price_amount(sku),
        "tiktok_seller_sku": _tiktok_seller_sku(sku),
        "tiktok_ean": identifier_code,
        "tiktok_product_identifier_code_type": identifier_type or "EAN",
        "tiktok_package_weight_oz": _tiktok_weight_oz(row),
    }
    updates.update(_extract_tiktok_attribute_fields(row))
    return {key: value for key, value in updates.items() if value not in (None, "")}


async def _fetch_tiktok_product_detail(record: dict[str, Any], product_id: str) -> dict[str, Any]:
    params = {}
    cipher = _shop_cipher(record)
    if cipher:
        params["shop_cipher"] = cipher
    data = await _signed_tiktok_get(record, f"/product/202309/products/{product_id}", params=params)
    root = _tiktok_root(data)
    product = root.get("product") if isinstance(root.get("product"), dict) else root
    return product if isinstance(product, dict) else {}


async def fetch_tiktok_products(status: str = "DRAFT", page_size: int = 50, max_pages: int = 4, include_details: bool = True) -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected"}
    page_size = max(1, min(int(page_size or 50), 100))
    max_pages = max(1, min(int(max_pages or 4), 20))
    status = str(status or "DRAFT").strip().upper()
    params: dict[str, Any] = {"page_size": page_size}
    cipher = _shop_cipher(record)
    if cipher:
        params["shop_cipher"] = cipher
    page_token = ""
    products: list[dict[str, Any]] = []
    for _ in range(max_pages):
        request_params = dict(params)
        if page_token:
            request_params["page_token"] = page_token
        body = {"status": status} if status and status != "ALL" else {}
        data = await _signed_tiktok_request(
            record,
            "POST",
            "/product/202309/products/search",
            params=request_params,
            body=body,
            operation="products.search",
        )
        rows, page_token = _tiktok_product_rows(data)
        products.extend(rows)
        if not page_token:
            break
    if include_details and products:
        concurrency = 8
        semaphore = asyncio.Semaphore(concurrency)

        async def detail_merge(row: dict[str, Any]) -> dict[str, Any]:
            product_id = _tiktok_product_id(row)
            if not product_id:
                return row
            async with semaphore:
                try:
                    return {**row, **(await _fetch_tiktok_product_detail(record, product_id))}
                except Exception:
                    return row

        products = await asyncio.gather(*(detail_merge(row) for row in products))
    return {"ok": True, "products": products, "count": len(products), "status": status}


def _inventory_match_indexes() -> dict[str, dict[str, dict[str, Any]]]:
    rows = list_products(active_only=False, low_stock_only=False)
    by_sku: dict[str, dict[str, Any]] = {}
    by_barcode: dict[str, dict[str, Any]] = {}
    for row in rows:
        sku = _normalize_match_key(row.get("sku") or row.get("default_code"))
        barcode = _normalize_barcode_key(row.get("barcode"))
        if sku and sku not in by_sku:
            by_sku[sku] = row
        if barcode and barcode not in by_barcode:
            by_barcode[barcode] = row
    return {"sku": by_sku, "barcode": by_barcode}


async def enrich_inventory_from_tiktok_drafts(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    dry_run = bool(payload.get("dry_run", False))
    overwrite_existing = bool(payload.get("overwrite_existing", True))
    status = str(payload.get("status") or "DRAFT").strip().upper()
    page_size = int(payload.get("page_size") or 50)
    max_pages = int(payload.get("max_pages") or 8)
    result = await fetch_tiktok_products(
        status=status,
        page_size=page_size,
        max_pages=max_pages,
        include_details=payload.get("include_details", True) is not False,
    )
    if not result.get("ok"):
        return result
    indexes = _inventory_match_indexes()
    existing_maps = list_tiktok_product_maps()
    by_tiktok_sku_id = {
        _normalize_match_key(row.get("tiktok_sku_id")): row
        for row in existing_maps
        if row.get("tiktok_sku_id")
    }
    enriched = []
    unmatched = []
    skipped = []
    for product_row in result.get("products") or []:
        if not isinstance(product_row, dict):
            continue
        skus = _tiktok_sku_rows(product_row) or [{}]
        for sku_row in skus:
            seller_sku = _tiktok_seller_sku(sku_row)
            identifier_code, _identifier_type = _tiktok_identifier_code(sku_row)
            tiktok_sku_id = _tiktok_sku_id(sku_row)
            mapping = by_tiktok_sku_id.get(_normalize_match_key(tiktok_sku_id)) if tiktok_sku_id else None
            product = get_product(int(mapping["product_id"])) if mapping and mapping.get("product_id") else None
            matched_by = "tiktok_sku_id" if product else ""
            if not product and seller_sku:
                product = indexes["sku"].get(_normalize_match_key(seller_sku))
                matched_by = "seller_sku" if product else ""
            if not product and identifier_code:
                product = indexes["barcode"].get(_normalize_barcode_key(identifier_code))
                matched_by = "ean" if product else ""
            if not product:
                unmatched.append({
                    "tiktok_product_id": _tiktok_product_id(product_row),
                    "tiktok_sku_id": tiktok_sku_id,
                    "seller_sku": seller_sku,
                    "ean": identifier_code,
                    "title": _first_present(product_row.get("title"), product_row.get("name")),
                })
                continue
            updates = _draft_product_to_tiktok_fields(product_row, sku_row)
            if not overwrite_existing:
                updates = {
                    key: value for key, value in updates.items()
                    if product.get(key) in (None, "")
                }
            if not updates:
                skipped.append({"product_id": product["id"], "matched_by": matched_by, "reason": "no_new_fields"})
                continue
            tiktok_product_id = _tiktok_product_id(product_row)
            if not dry_run:
                set_product_details(
                    int(product["id"]),
                    audit_source="tiktok_shop_draft_enrichment",
                    audit_actor="system",
                    audit_context={
                        "matched_by": matched_by,
                        "tiktok_product_id": tiktok_product_id,
                        "tiktok_sku_id": tiktok_sku_id,
                    },
                    **updates,
                )
                if tiktok_product_id and tiktok_sku_id:
                    upsert_tiktok_product_map(
                        product_id=int(product["id"]),
                        internal_sku=product.get("sku") or product.get("barcode"),
                        tiktok_product_id=tiktok_product_id,
                        tiktok_sku_id=tiktok_sku_id,
                        tiktok_shop_id=product_row.get("shop_id"),
                        tiktok_category_id=updates.get("tiktok_category_id") or product_row.get("category_id"),
                        status=str(product_row.get("status") or status or "draft").lower(),
                        raw_response=product_row,
                    )
            enriched.append({
                "product_id": product["id"],
                "matched_by": matched_by,
                "seller_sku": seller_sku,
                "ean": identifier_code,
                "tiktok_product_id": tiktok_product_id,
                "tiktok_sku_id": tiktok_sku_id,
                "fields": sorted(updates.keys()),
            })
    return {
        "ok": True,
        "dry_run": dry_run,
        "status": status,
        "fetched": result.get("count", 0),
        "enriched_count": len(enriched),
        "unmatched_count": len(unmatched),
        "skipped_count": len(skipped),
        "enriched": enriched,
        "unmatched": unmatched[:100],
        "skipped": skipped[:100],
    }


def _looks_like_base64_image(value: str) -> bool:
    text = str(value or "").strip()
    if not text or len(text) < 128:
        return False
    prefixes = ("/9j/", "iVBOR", "UklGR", "R0lGOD")
    return text.startswith(prefixes) or text.startswith("data:image/")


def _decode_base64_image(value: str) -> tuple[bytes, str, str]:
    text = str(value or "").strip()
    mime = ""
    if text.startswith("data:image/") and "," in text:
        header, text = text.split(",", 1)
        mime = header.split(";", 1)[0].replace("data:", "")
    data = base64.b64decode(text, validate=False)
    if not mime:
        if data.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif data.startswith(b"\x89PNG"):
            mime = "image/png"
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            mime = "image/webp"
        elif data.startswith(b"GIF"):
            mime = "image/gif"
        else:
            mime = "application/octet-stream"
    extension = mimetypes.guess_extension(mime) or ".img"
    if extension == ".jpe":
        extension = ".jpg"
    return data, mime, extension


def _normalize_upload_image(content: bytes, mime: str) -> tuple[bytes, str, str]:
    if mime in {"image/jpeg", "image/png"}:
        return content, mime, ".jpg" if mime == "image/jpeg" else ".png"
    try:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as image:
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA")
            output = io.BytesIO()
            image.save(output, format="PNG")
            return output.getvalue(), "image/png", ".png"
    except Exception:
        return content, mime or "application/octet-stream", mimetypes.guess_extension(mime or "") or ".img"


def _split_image_sources(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    text = str(value or "").strip()
    if not text:
        return []
    if _looks_like_base64_image(text):
        return [text]
    rows: list[str] = []
    for line in text.replace(",", "\n").splitlines():
        source = line.strip()
        if source:
            rows.append(source)
    return rows


def _is_tiktok_image_uri(source: str) -> bool:
    """Return True if source is already a pre-uploaded TikTok CDN URI (not a local path or URL)."""
    if not source:
        return False
    # Local paths, URLs, and base64 data URIs are NOT TikTok CDN URIs
    if source.startswith(("http://", "https://", "/", "data:")):
        return False
    # TikTok CDN URIs look like: tos-useast5-i-omjb5zjo8w-tx/f33eea587cc2488c9010e048141e62ea
    # They contain exactly one slash and no protocol
    parts = source.split("/")
    if len(parts) == 2 and parts[0] and parts[1] and len(parts[1]) >= 16:
        return True
    return False


def _product_image_sources(product: dict[str, Any]) -> list[str]:
    sources: list[str] = []
    for field_name in ("image_path", "media_url", "image_url", "tiktok_image_urls"):
        for source in _split_image_sources(product.get(field_name)):
            if source and source not in sources:
                sources.append(source)
    return sources


def _split_product_image_sources(product: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (tiktok_uris, upload_paths) — split pre-uploaded TikTok URIs from local/remote paths."""
    tiktok_uris: list[str] = []
    upload_paths: list[str] = []
    for source in _product_image_sources(product):
        if _is_tiktok_image_uri(source):
            tiktok_uris.append(source)
        else:
            upload_paths.append(source)
    return tiktok_uris, upload_paths


def _numeric_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(value)
    except Exception:
        return str(value).strip()
    if number.is_integer():
        return str(int(number))
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _ounces_to_pounds_text(value: Any) -> str:
    try:
        ounces = float(value)
    except Exception:
        ounces = 0
    if ounces <= 0:
        ounces = 8
    pounds = max(0.01, ounces / 16)
    return f"{pounds:.4f}".rstrip("0").rstrip(".")


def _safe_inventory_quantity(value: Any) -> int:
    try:
        quantity = int(float(value or 0))
    except Exception:
        quantity = 0
    return max(0, quantity)


def _safe_tiktok_seller_sku(product: dict[str, Any], value: Any = None) -> str:
    sku = _first_present(value, product.get("tiktok_seller_sku"), product.get("sku"), product.get("barcode"), f"product-{product.get('id')}")
    sku = str(sku or "").strip()
    if len(sku) <= 50:
        return sku
    barcode = str(product.get("tiktok_ean") or product.get("barcode") or "").strip()
    if barcode:
        candidate = f"Y-{barcode}"
        if len(candidate) <= 50:
            return candidate
    digest = hashlib.sha1(sku.encode("utf-8")).hexdigest()[:8].upper()
    return f"{sku[:41].rstrip('-_ ')}-{digest}"[:50]


_INVENTORY_TO_TIKTOK_ATTRIBUTE_MAP: tuple[tuple[str, str], ...] = (
    ("Pack Type", "tiktok_pack_type"),
    ("Scent", "tiktok_scent"),
    ("Region Of Origin", "tiktok_region_of_origin"),
    ("Product Form", "tiktok_product_form"),
    ("Edition", "tiktok_edition"),
    ("Contains Alcohol Or Aerosol", "tiktok_contains_alcohol_or_aerosol"),
    ("Manufacturer", "tiktok_manufacturer"),
    ("Shelf Life", "tiktok_shelf_life"),
    ("(Inactive) Ingredients", "tiktok_inactive_ingredients"),
    ("Age Group", "tiktok_age_group"),
    ("Item Name", "tiktok_item_name"),
    ("Feature", "tiktok_feature"),
    ("Fragrance Concentration", "tiktok_fragrance_concentration"),
    ("Material Type Free", "tiktok_material_type_free"),
    ("Ingredients", "tiktok_ingredients"),
    ("Container Type", "tiktok_container_type"),
    ("Allergen Information", "tiktok_allergen_information"),
    ("Ingredient Feature", "tiktok_ingredient_feature"),
    ("Volume", "tiktok_volume"),
    ("CA Prop 65: Repro. Chems", "tiktok_ca_prop_65_repro_chems"),
    ("CA Prop 65: Carcinogens", "tiktok_ca_prop_65_carcinogens"),
    ("Flammable Liquid", "tiktok_flammable_liquid"),
    ("Aerosols", "tiktok_aerosols"),
    ("Dangerous Goods Or Hazardous Materials", "tiktok_dangerous_goods_or_hazardous_materials"),
    ("Environmental Feature", "tiktok_environmental_feature"),
)

_STRICT_ENUM_ATTRIBUTE_NAMES = {
    "Pack Type",
    "Contains Alcohol Or Aerosol",
    "Fragrance Concentration",
    "CA Prop 65: Repro. Chems",
    "CA Prop 65: Carcinogens",
    "Flammable Liquid",
    "Aerosols",
    "Dangerous Goods Or Hazardous Materials",
}


def _normalize_label_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _split_keywords(value: Any) -> list[str]:
    if isinstance(value, list):
        parts = [str(item or "").strip() for item in value]
    else:
        parts = re.split(r"[\n,;|]+", str(value or ""))
    rows: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = str(part or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(text)
    return rows


def _trim_search_terms(value: Any, max_length: int = 250) -> list[str]:
    terms = _split_keywords(value)
    if not terms:
        return []
    trimmed: list[str] = []
    current_length = 0
    for term in terms:
        candidate = term[:80].strip()
        if not candidate:
            continue
        separator = 2 if trimmed else 0
        projected = current_length + separator + len(candidate)
        if projected > max_length:
            remaining = max_length - current_length - separator
            if remaining <= 0:
                break
            candidate = candidate[:remaining].strip(" ,;|")
            if not candidate:
                break
            projected = current_length + separator + len(candidate)
        trimmed.append(candidate)
        current_length = projected
        if current_length >= max_length:
            break
    return trimmed


def _split_multi_value_text(value: Any) -> list[str]:
    return [row for row in _split_keywords(value) if row]


def _fragrance_product_form(value: str, product: dict[str, Any]) -> str:
    text = _first_present(value, product.get("tiktok_fragrance_concentration"), product.get("name")).lower()
    if any(token in text for token in ("parfum", "toilette", "cologne", "spray", "fragrance", "perfume", "oil")):
        return "Liquid"
    return value


def _fragrance_container_type(value: str, product: dict[str, Any]) -> str:
    text = _first_present(value, product.get("name")).lower()
    if "aerosol" in text:
        return "Aerosol Can"
    if any(token in text for token in ("spray", "perfume oil", "roll-on", "bottle", "parfum", "fragrance")):
        return "Bottle"
    return value


def _fragrance_age_group(value: str) -> str:
    normalized = _normalize_label_key(value)
    if normalized in {"adult", "adults"}:
        return "Adults"
    return value


def _fragrance_pack_type(value: str) -> str:
    normalized = _normalize_label_key(value)
    if normalized in {"singleitem", "single"}:
        return "Single Item"
    if normalized in {"multipack", "multi"}:
        return "Multi-Pack"
    return value


def _fragrance_contains_alcohol(value: str) -> str:
    normalized = _normalize_label_key(value)
    if normalized == "containsalcohol":
        return "Contains Alcohol"
    if normalized == "containsaerosol":
        return "Contains Aerosol"
    if normalized == "containsboth":
        return "Contains Both"
    if normalized == "containsneither":
        return "Contains Neither"
    return value


def _fragrance_concentration(value: str) -> str:
    normalized = _normalize_label_key(value)
    if normalized in {"eaudeparfum", "edp"}:
        return "Eau De Parfum"
    if normalized in {"eaudetoilette", "edt"}:
        return "Eau de Toilette"
    if normalized in {"eaudecologne", "edc"}:
        return "Eau de Cologne"
    return value


def _fragrance_volume(value: str, product: dict[str, Any]) -> str:
    raw = _first_present(value)
    numbers = [str(int(float(num))) for num in re.findall(r"(\d+(?:\.\d+)?)\s*m?l", raw.lower())]
    if not numbers:
        size_ml = _first_present(product.get("size_ml"), product.get("volume_ml"))
        if size_ml:
            try:
                numbers = [str(int(float(size_ml)))]
            except Exception:
                numbers = []
    if numbers:
        return f"{numbers[0]}Ml"
    return value


def _coerce_attribute_text(attribute_name: str, raw_value: Any, product: dict[str, Any]) -> str:
    value = _first_present(raw_value)
    if not value:
        return ""
    if attribute_name == "Pack Type":
        return _fragrance_pack_type(value)
    if attribute_name == "Contains Alcohol Or Aerosol":
        return _fragrance_contains_alcohol(value)
    if attribute_name == "Fragrance Concentration":
        return _fragrance_concentration(value)
    if attribute_name == "Volume":
        return _fragrance_volume(value, product)
    return value


def _attribute_value_candidates(value: str, multiple: bool) -> list[str]:
    if not value:
        return []
    if multiple:
        pieces = _split_multi_value_text(value)
        if len(pieces) <= 1:
            pieces = [
                token.strip()
                for token in re.split(r"[\s/&]+", value)
                if token.strip()
            ] or pieces
        if value not in pieces:
            pieces.append(value)
        return pieces
    return [value]


def _match_attribute_value(attribute: dict[str, Any], candidate: str) -> dict[str, Any] | None:
    values = _first_list(attribute.get("values"), attribute.get("attribute_values"))
    if not values:
        return None
    candidate_key = _normalize_label_key(candidate)
    if not candidate_key:
        return None
    exact_match = None
    partial_match = None
    for row in values:
        if not isinstance(row, dict):
            continue
        name = _first_present(row.get("name"), row.get("value_name"), row.get("value"))
        if not name:
            continue
        name_key = _normalize_label_key(name)
        if candidate_key == name_key:
            exact_match = {"id": str(row.get("id") or ""), "name": name}
            break
        if candidate_key in name_key or name_key in candidate_key:
            partial_match = {"id": str(row.get("id") or ""), "name": name}
    return exact_match or partial_match


def _attribute_values_payload(attribute: dict[str, Any], raw_value: Any, product: dict[str, Any]) -> list[dict[str, Any]]:
    attribute_name = _first_present(attribute.get("name"), attribute.get("attribute_name"))
    value = _coerce_attribute_text(attribute_name, raw_value, product)
    if not value:
        return []
    if bool(attribute.get("is_customizable")) and attribute_name not in _STRICT_ENUM_ATTRIBUTE_NAMES:
        values = _split_keywords(value) or [value]
        payload_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in values:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            payload_rows.append({"name": text[:120]})
            if not bool(attribute.get("is_multiple_selection")):
                break
        if payload_rows:
            return payload_rows
    multiple = bool(attribute.get("is_multiple_selection"))
    matches: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for candidate in _attribute_value_candidates(value, multiple):
        match = _match_attribute_value(attribute, candidate)
        if match:
            key = f"id:{match.get('id')}:{match.get('name')}"
            if key not in seen_keys:
                seen_keys.add(key)
                matches.append(match)
    if matches:
        return matches
    if bool(attribute.get("is_customizable")):
        values = _attribute_value_candidates(value, multiple)
        if not values:
            return []
        payload_rows: list[dict[str, Any]] = []
        for item in values:
            text = str(item or "").strip()
            if text:
                payload_rows.append({"name": text[:120]})
            if not multiple and payload_rows:
                break
        return payload_rows
    return []


async def _inventory_attribute_payload(product: dict[str, Any], category_id: str) -> list[dict[str, Any]]:
    result = await fetch_tiktok_category_attributes(category_id)
    attributes = result.get("attributes") or []
    by_name: dict[str, dict[str, Any]] = {}
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        key = _normalize_label_key(_first_present(attribute.get("name"), attribute.get("attribute_name")))
        if not key:
            continue
        existing = by_name.get(key)
        if existing is None:
            by_name[key] = attribute
            continue
        if str(existing.get("type") or "").upper() != "PRODUCT_PROPERTY" and str(attribute.get("type") or "").upper() == "PRODUCT_PROPERTY":
            by_name[key] = attribute
    rows: list[dict[str, Any]] = []
    for attribute_name, field_name in _INVENTORY_TO_TIKTOK_ATTRIBUTE_MAP:
        raw_value = product.get(field_name)
        if raw_value in (None, ""):
            continue
        attribute = by_name.get(_normalize_label_key(attribute_name))
        if not attribute:
            continue
        values = _attribute_values_payload(attribute, raw_value, product)
        if values:
            rows.append({"id": str(attribute.get("id") or ""), "values": values})
    return rows


async def _inventory_brand_payload(product: dict[str, Any], category_id: str) -> dict[str, Any]:
    brand_name = _first_present(product.get("tiktok_brand"), product.get("brand"))
    if not brand_name:
        return {}
    result = await fetch_tiktok_brands(brand_name, category_id)
    brands = result.get("brands") or []
    exact_authorized = None
    exact_any = None
    target_key = _normalize_label_key(brand_name)
    for row in brands:
        if not isinstance(row, dict):
            continue
        name = _first_present(row.get("name"), row.get("brand_name"))
        if _normalize_label_key(name) != target_key:
            continue
        if str(row.get("authorized_status") or "").upper() == "AUTHORIZED":
            exact_authorized = row
            break
        if exact_any is None:
            exact_any = row
    if exact_authorized and exact_authorized.get("id"):
        return {"brand_id": str(exact_authorized["id"])}
    if exact_any and exact_any.get("id"):
        return {"brand_id": str(exact_any["id"])}
    return {}


def _normalize_product_payload(product: dict[str, Any], payload: dict[str, Any], image_uris: list[str], warehouse_id: str | None = None) -> dict[str, Any]:
    category_id = str(payload.get("category_id") or payload.get("tiktok_category_id") or product.get("tiktok_category_id") or "").strip()
    if not category_id:
        category_map = get_tiktok_category_map(
            internal_category_id=product.get("category_id"),
            internal_category_name=product.get("category_name"),
        )
        category_id = str((category_map or {}).get("tiktok_category_id") or "").strip()
    if not category_id:
        raise ValueError("category_mapping_required")
    sku = _safe_tiktok_seller_sku(product, payload.get("seller_sku"))
    price = payload.get("price")
    if price in (None, ""):
        price = product.get("tiktok_retail_price") or product.get("retail_price") or product.get("list_price") or 0
    stock = payload.get("quantity")
    if stock in (None, ""):
        stock = product.get("tiktok_quantity") or product.get("on_hand_qty") or 0
    description = _first_present(payload.get("description"), product.get("tiktok_description"), product.get("description"), product.get("notes"), product.get("name"))
    inventory_row = {"quantity": _safe_inventory_quantity(stock)}
    warehouse_id = str(payload.get("warehouse_id") or warehouse_id or "").strip()
    if warehouse_id:
        inventory_row["warehouse_id"] = warehouse_id
    sku_body = {
        "seller_sku": sku,
        "price": {"amount": str(price), "currency": payload.get("currency") or "USD"},
        "inventory": [inventory_row],
    }
    if payload.get("sales_attributes"):
        sku_body["sales_attributes"] = payload["sales_attributes"]
    product_identifier = _first_present(payload.get("gtin"), product.get("tiktok_ean"), product.get("barcode"))
    if product_identifier:
        sku_body["product_identifier_code"] = {
            "identifier_code": product_identifier,
            "identifier_code_type": payload.get("identifier_code_type") or product.get("tiktok_product_identifier_code_type") or "EAN",
        }
    body = {
        "title": _first_present(payload.get("title"), product.get("tiktok_title"), product.get("name"))[:255],
        "description": description,
        "category_id": category_id,
        "category_version": payload.get("category_version") or "v2",
        "skus": [sku_body],
    }
    save_mode = str(payload.get("save_mode") or "").strip().upper()
    if save_mode in {"AS_DRAFT", "LISTING"}:
        body["save_mode"] = save_mode
    if image_uris:
        body["main_images"] = [{"uri": uri} for uri in image_uris]
    if payload.get("brand_id"):
        body["brand_id"] = str(payload["brand_id"])
    elif isinstance(payload.get("brand"), dict):
        body["brand"] = payload["brand"]
    if payload.get("search_terms"):
        body["search_terms"] = payload["search_terms"]
    weight_oz = payload.get("package_weight_oz")
    if weight_oz in (None, ""):
        weight_oz = product.get("tiktok_package_weight_oz")
    if weight_oz in (None, ""):
        weight_oz = _first_present(product.get("size_oz"), product.get("volume_oz"))
    body["package_weight"] = payload.get("package_weight") or {"value": _ounces_to_pounds_text(weight_oz), "unit": "POUND"}
    if payload.get("package_dimensions"):
        body["package_dimensions"] = payload["package_dimensions"]
    if payload.get("attributes"):
        body["product_attributes"] = payload["attributes"]
    if payload.get("certifications"):
        body["certifications"] = payload["certifications"]
    return body


def _extract_product_mapping(product_id: int, product: dict[str, Any], category_id: str, data: dict[str, Any]) -> dict[str, Any]:
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    tiktok_product_id = _first_present(root.get("product_id"), root.get("id"), root.get("product", {}).get("id") if isinstance(root.get("product"), dict) else "")
    sku_rows = root.get("skus") if isinstance(root.get("skus"), list) else []
    if not sku_rows and isinstance(root.get("product"), dict):
        sku_rows = root["product"].get("skus") if isinstance(root["product"].get("skus"), list) else []
    tiktok_sku_id = ""
    if sku_rows and isinstance(sku_rows[0], dict):
        tiktok_sku_id = _first_present(sku_rows[0].get("sku_id"), sku_rows[0].get("id"))
    tiktok_sku_id = tiktok_sku_id or _first_present(root.get("sku_id"), root.get("sku", {}).get("id") if isinstance(root.get("sku"), dict) else "")
    if not tiktok_product_id or not tiktok_sku_id:
        raise RuntimeError(f"TikTok product created but response did not include product_id/sku_id: {data}")
    return upsert_tiktok_product_map(
        product_id=int(product_id),
        internal_sku=product.get("sku") or product.get("barcode"),
        tiktok_product_id=tiktok_product_id,
        tiktok_sku_id=tiktok_sku_id,
        tiktok_shop_id=root.get("shop_id"),
        tiktok_category_id=category_id,
        status="active",
        raw_response=data,
    )


async def _upload_image_file(record: dict[str, Any], image_path: str) -> str:
    app_secret = _decrypt(record.get("app_secret_encrypted"))
    access_token = _decrypt(record.get("access_token_encrypted"))
    api_path = "/product/202309/images/upload"
    file_name = "product-image"
    mime = "application/octet-stream"
    content: bytes | None = None
    source = str(image_path or "").strip()
    if source.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            image_response = await client.get(source)
            image_response.raise_for_status()
            content = image_response.content
            mime = image_response.headers.get("content-type", "").split(";", 1)[0] or mimetypes.guess_type(source)[0] or mime
            extension = mimetypes.guess_extension(mime) or Path(source).suffix or ".img"
            file_name = f"product-image{extension}"
    elif _looks_like_base64_image(source):
        content, mime, extension = _decode_base64_image(source)
        file_name = f"product-image{extension}"
    else:
        if source.startswith("/marketplace-media/"):
            path = Path(__file__).resolve().parents[2] / "data" / "marketplace_images" / source.removeprefix("/marketplace-media/")
        elif source.startswith("/product-media/"):
            path = Path(__file__).resolve().parents[2] / "data" / "marketplace_images" / source.removeprefix("/product-media/")
        else:
            path = Path(source)
        if not path.is_absolute():
            path = Path.cwd() / source
        if not path.exists() or not path.is_file():
            raise ValueError(f"image_not_found: {image_path}")
        mime = mimetypes.guess_type(str(path))[0] or mime
        file_name = path.name
        content = path.read_bytes()
    content, mime, extension = _normalize_upload_image(content or b"", mime)
    if file_name == "product-image":
        file_name = f"product-image{extension}"
    query = {
        "app_key": record.get("app_key"),
        "timestamp": int(time.time()),
        "access_token": access_token,
    }
    query["sign"] = _tiktok_sign(api_path, query, app_secret)
    headers = {"x-tts-access-token": access_token}
    url = f"{(record.get('api_base_url') or TIKTOK_SHOP_API_BASE_URL).rstrip('/')}{api_path}"
    files = {"data": (file_name, content, mime)}
    form = {"use_case": "MAIN_IMAGE"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, params=query, headers=headers, data=form, files=files)
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text}
    ok = response.status_code < 400 and (not isinstance(data, dict) or data.get("code") in (None, 0, "0"))
    log_tiktok_api(
        "product.image_upload",
        "POST",
        api_path,
        status_code=response.status_code,
        ok=ok,
        request={"file": file_name, "mime": mime, "bytes": len(content), "use_case": "MAIN_IMAGE"},
        response=data,
        error=None if ok else str(data),
    )
    if not ok:
        raise RuntimeError(f"TikTok image upload failed: {data}")
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    return _first_present(root.get("uri"), root.get("image_uri"), root.get("url"))


async def push_product_to_tiktok(payload: dict[str, Any]) -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected"}
    product_id = payload.get("product_id")
    if not product_id:
        return {"ok": False, "error": "product_id_required"}
    product = get_product(int(product_id))
    if not product:
        return {"ok": False, "error": "product_not_found"}
    image_uris = [str(uri).strip() for uri in payload.get("image_uris") or [] if str(uri).strip()]
    image_paths = list(payload.get("image_paths") or [])
    if not image_uris and not image_paths:
        tiktok_uris, image_paths = _split_product_image_sources(product)
        image_uris.extend(tiktok_uris)
    else:
        # Caller may have mixed TikTok URIs into image_paths — detect and split
        real_paths = []
        for src in image_paths:
            if _is_tiktok_image_uri(str(src).strip()):
                image_uris.append(str(src).strip())
            else:
                real_paths.append(src)
        image_paths = real_paths
    for image_path in image_paths:
        image_uris.append(await _upload_image_file(record, str(image_path)))
    warehouse_id = str(payload.get("warehouse_id") or "").strip() or await _default_sales_warehouse_id(record)
    category_id = str(payload.get("category_id") or payload.get("tiktok_category_id") or product.get("tiktok_category_id") or "").strip()
    if not payload.get("search_terms"):
        payload["search_terms"] = _trim_search_terms(product.get("tiktok_search_keywords"))
    if category_id and not payload.get("attributes"):
        payload["attributes"] = await _inventory_attribute_payload(product, category_id)
    if category_id and not payload.get("brand_id"):
        payload.update(await _inventory_brand_payload(product, category_id))
    body = _normalize_product_payload(product, payload, image_uris, warehouse_id=warehouse_id)
    category_id = str(body["category_id"])
    params = {}
    cipher = _shop_cipher(record)
    if cipher:
        params["shop_cipher"] = cipher
    data = await _signed_tiktok_request(record, "POST", "/product/202309/products", params=params, body=body, operation="product.create")
    mapping = _extract_product_mapping(int(product_id), product, category_id, data)
    return {"ok": True, "mapping": mapping, "response": data}


async def push_missing_image_inventory_to_tiktok_drafts(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    dry_run = bool(payload.get("dry_run", False))
    limit = int(payload.get("limit") or 0)
    force_statuses = {s.strip().lower() for s in (payload.get("force_statuses") or [])}
    product_ids = {int(value) for value in payload.get("product_ids") or [] if str(value).strip().isdigit()}
    all_maps = list_tiktok_product_maps()
    mapped_by_status: dict[str, list[int]] = {}
    for row in all_maps:
        if not row.get("product_id"):
            continue
        status = str(row.get("status") or "unknown").lower()
        mapped_by_status.setdefault(status, []).append(int(row["product_id"]))
    force_ids: set[int] = set()
    for status, ids in mapped_by_status.items():
        if status in force_statuses:
            force_ids.update(ids)
    mapped_ids = {pid for ids in mapped_by_status.values() for pid in ids} - force_ids
    already_mapped_by_status = {status: len(ids) for status, ids in mapped_by_status.items() if not (force_statuses and status in force_statuses)}
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for product in list_products(active_only=False, low_stock_only=False):
        product_id = int(product.get("id") or 0)
        if product_ids and product_id not in product_ids:
            continue
        if product_id in mapped_ids:
            continue
        images = _product_image_sources(product)
        if not images:
            skipped.append({"product_id": product_id, "reason": "image_missing", "name": product.get("name")})
            continue
        if not product.get("barcode") and not product.get("tiktok_ean"):
            skipped.append({"product_id": product_id, "reason": "ean_missing", "name": product.get("name")})
            continue
        candidates.append(product)
        if limit and len(candidates) >= limit:
            break
    already_mapped_count = sum(len(ids) for ids in mapped_by_status.values()) - len(force_ids)
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "candidate_count": len(candidates),
            "skipped_count": len(skipped),
            "already_mapped_count": already_mapped_count,
            "already_mapped_by_status": already_mapped_by_status,
            "candidates": [
                {
                    "product_id": int(product.get("id") or 0),
                    "sku": product.get("sku"),
                    "barcode": product.get("barcode"),
                    "name": product.get("name"),
                    "image_count": len(_product_image_sources(product)),
                }
                for product in candidates
            ],
            "skipped": skipped[:100],
        }
    pushed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for product in candidates:
        product_id = int(product.get("id") or 0)
        try:
            tiktok_uris, upload_paths = _split_product_image_sources(product)
            push_call: dict[str, Any] = {
                "product_id": product_id,
                "save_mode": "AS_DRAFT",
                "category_id": product.get("tiktok_category_id") or payload.get("default_category_id") or "855824",
                "image_uris": tiktok_uris,
                "image_paths": upload_paths if not tiktok_uris else [],
                "quantity": product.get("tiktok_quantity") or product.get("on_hand_qty") or 0,
                "price": product.get("tiktok_retail_price") or product.get("retail_price") or product.get("list_price") or 0,
                "seller_sku": _safe_tiktok_seller_sku(product),
                "gtin": product.get("tiktok_ean") or product.get("barcode"),
                "identifier_code_type": product.get("tiktok_product_identifier_code_type") or "EAN",
                "package_weight_oz": product.get("tiktok_package_weight_oz"),
            }
            if product.get("tiktok_package_length_in") and product.get("tiktok_package_width_in") and product.get("tiktok_package_height_in"):
                def _dim_str(v: Any) -> str:
                    try:
                        f = float(v)
                        return str(int(f)) if f == int(f) else f"{f:.2f}".rstrip("0").rstrip(".")
                    except Exception:
                        return str(v)
                push_call["package_dimensions"] = {
                    "length": _dim_str(product["tiktok_package_length_in"]),
                    "width": _dim_str(product["tiktok_package_width_in"]),
                    "height": _dim_str(product["tiktok_package_height_in"]),
                    "unit": "INCH",
                }
            result = await push_product_to_tiktok(push_call)
            if result.get("ok"):
                pushed.append(
                    {
                        "product_id": product_id,
                        "sku": product.get("sku"),
                        "barcode": product.get("barcode"),
                        "mapping": result.get("mapping"),
                    }
                )
            else:
                errors.append({"product_id": product_id, "sku": product.get("sku"), "error": result})
        except Exception as exc:
            errors.append({"product_id": product_id, "sku": product.get("sku"), "error": str(exc)})
    return {
        "ok": not errors,
        "dry_run": False,
        "candidate_count": len(candidates),
        "pushed_count": len(pushed),
        "error_count": len(errors),
        "skipped_count": len(skipped),
        "already_mapped_count": already_mapped_count,
        "already_mapped_by_status": already_mapped_by_status,
        "pushed": pushed,
        "errors": errors,
        "skipped": skipped[:100],
    }


async def sync_tiktok_inventory(product_id: int | None = None) -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected"}
    mappings = [get_tiktok_product_map_by_product(int(product_id))] if product_id else list_tiktok_product_maps()
    mappings = [row for row in mappings if row]
    pushed = []
    errors = []
    for mapping in mappings:
        product = get_product(int(mapping["product_id"]))
        if not product:
            errors.append({"product_id": mapping["product_id"], "error": "product_not_found"})
            continue
        qty = max(0, int(float(product.get("on_hand_qty") or 0)))
        params = {}
        cipher = _shop_cipher(record)
        if cipher:
            params["shop_cipher"] = cipher
        body = {
            "skus": [
                {
                    "id": str(mapping["tiktok_sku_id"]),
                    "inventory": [{"quantity": qty}],
                }
            ]
        }
        try:
            warehouse_id = str(mapping.get("warehouse_id") or "").strip() or await _default_sales_warehouse_id(record)
            if warehouse_id:
                body["skus"][0]["inventory"][0]["warehouse_id"] = warehouse_id
            data = await _signed_tiktok_request(record, "POST", f"/product/202309/products/{mapping['tiktok_product_id']}/inventory/update", params=params, body=body, operation="inventory.update")
            pushed.append({"product_id": product["id"], "tiktok_sku_id": mapping["tiktok_sku_id"], "quantity": qty, "response": data})
        except Exception as exc:
            errors.append({"product_id": product["id"], "tiktok_sku_id": mapping["tiktok_sku_id"], "error": str(exc)})
    return {"ok": not errors, "pushed": pushed, "errors": errors}


async def delete_tiktok_products(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected"}
    filter_statuses = {s.strip().lower() for s in (payload.get("statuses") or [])}
    all_maps = list_tiktok_product_maps()
    targets = [
        row for row in all_maps
        if row.get("tiktok_product_id") and (not filter_statuses or str(row.get("status") or "").lower() in filter_statuses)
    ]
    if not targets:
        return {"ok": True, "deleted_count": 0, "error_count": 0, "deleted": [], "errors": []}
    params: dict[str, Any] = {}
    cipher = _shop_cipher(record)
    if cipher:
        params["shop_cipher"] = cipher
    # TikTok allows up to 20 product IDs per delete call
    BATCH = 20
    deleted: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    tiktok_ids_deleted: list[str] = []
    for i in range(0, len(targets), BATCH):
        batch = targets[i : i + BATCH]
        product_ids_batch = [str(row["tiktok_product_id"]) for row in batch]
        try:
            await _signed_tiktok_request(
                record,
                "DELETE",
                "/product/202309/products",
                params=params,
                body={"product_ids": product_ids_batch},
                operation="product.delete",
            )
            for row in batch:
                deleted.append({
                    "product_id": row.get("product_id"),
                    "tiktok_product_id": row["tiktok_product_id"],
                    "sku": row.get("sku") or row.get("internal_sku"),
                    "name": row.get("name"),
                    "status": row.get("status"),
                })
                tiktok_ids_deleted.append(str(row["tiktok_product_id"]))
        except Exception as exc:
            for row in batch:
                errors.append({
                    "product_id": row.get("product_id"),
                    "tiktok_product_id": row["tiktok_product_id"],
                    "error": str(exc),
                })
    if tiktok_ids_deleted:
        delete_tiktok_product_maps(tiktok_ids_deleted)
    return {
        "ok": not errors,
        "deleted_count": len(deleted),
        "error_count": len(errors),
        "deleted": deleted,
        "errors": errors,
    }


def _extract_order_items(order: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("line_items", "items", "order_lines", "sku_list"):
        value = order.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _order_status(order: dict[str, Any]) -> str:
    return str(order.get("status") or order.get("order_status") or "").strip().upper()


def _item_sku_id(item: dict[str, Any]) -> str:
    sku = item.get("sku") if isinstance(item.get("sku"), dict) else {}
    return _first_present(item.get("sku_id"), item.get("id"), sku.get("id"), sku.get("sku_id"))


def _item_product_id(item: dict[str, Any]) -> str:
    product = item.get("product") if isinstance(item.get("product"), dict) else {}
    return _first_present(
        item.get("product_id"),
        item.get("spu_id"),
        product.get("id"),
        product.get("product_id"),
    )


def _item_seller_sku(item: dict[str, Any]) -> str:
    sku = item.get("sku") if isinstance(item.get("sku"), dict) else {}
    return _first_present(
        item.get("seller_sku"),
        item.get("sku_seller_sku"),
        sku.get("seller_sku"),
        sku.get("external_sku_id"),
    )


def _item_qty(item: dict[str, Any]) -> float:
    try:
        return max(1.0, float(item.get("quantity") or item.get("qty") or 1))
    except Exception:
        return 1.0


def _money_amount(value) -> float:
    if isinstance(value, dict):
        value = (
            value.get("amount")
            or value.get("value")
            or value.get("refund_total")
            or value.get("refund_subtotal")
            or value.get("total")
        )
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _line_product_name(item: dict[str, Any]) -> str:
    return _first_present(item.get("product_name"), item.get("name"), item.get("sku_name"))


def _product_name_score(query: str, product: dict[str, Any]) -> float:
    query_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", str(query or "").lower())
        if len(token) > 2
    }
    name_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", str(product.get("name") or "").lower())
        if len(token) > 2
    }
    if not query_tokens or not name_tokens:
        return 0.0
    overlap = len(query_tokens & name_tokens)
    return overlap / max(len(query_tokens), 1)


def _find_product_for_tiktok_item(item: dict[str, Any], products: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any] | None, str]:
    sku_id = _item_sku_id(item)
    if sku_id:
        try:
            mapping = get_tiktok_product_map_by_sku(sku_id)
            if mapping and mapping.get("product_id"):
                product = get_product(int(mapping["product_id"]))
                if product:
                    return product, "tiktok_sku_map"
        except Exception:
            pass

    tiktok_product_id = _item_product_id(item)
    if tiktok_product_id:
        try:
            for mapping in list_tiktok_product_maps() or []:
                if str(mapping.get("tiktok_product_id") or "") == str(tiktok_product_id):
                    product = get_product(int(mapping["product_id"]))
                    if product:
                        return product, "tiktok_product_map"
        except Exception:
            pass

    seller_sku = _item_seller_sku(item)
    if seller_sku:
        try:
            product = find_product_by_code(seller_sku)
            if product:
                return product, "seller_sku"
        except Exception:
            pass

    name = _line_product_name(item)
    if name:
        candidates = products if products is not None else list_products(active_only=False, low_stock_only=False)
        scored = sorted(
            ((candidate, _product_name_score(name, candidate)) for candidate in candidates or []),
            key=lambda pair: pair[1],
            reverse=True,
        )
        if scored and scored[0][1] >= 0.45:
            return scored[0][0], "name_match"

    return None, "unmatched"


def _tiktok_order_id(order: dict[str, Any]) -> str:
    return _first_present(order.get("id"), order.get("order_id"), order.get("external_order_id"))


def _tiktok_order_is_paid(order: dict[str, Any]) -> bool:
    return tiktok_order_status_family(_order_status(order)) == "confirmed"


def _tiktok_order_is_cancelled(order: dict[str, Any]) -> bool:
    return tiktok_order_status_family(_order_status(order)) == "cancelled"


def _customer_address_text(fields: dict[str, str]) -> str:
    if fields.get("full_address"):
        return fields["full_address"]
    parts = [
        fields.get("address_line_1"),
        fields.get("address_line_2"),
        fields.get("address_line_3"),
        fields.get("address_line_4"),
        fields.get("city"),
        fields.get("state"),
        fields.get("zipcode"),
        fields.get("country"),
    ]
    return ", ".join(part for part in parts if part)


def tiktok_order_status_family(status: str | None) -> str:
    value = str(status or "").strip().upper()
    if value in {"CANCELLED", "CANCELED", "UNPAID_CANCELLED", "RETURNED", "RETURNING"}:
        return "cancelled"
    if value in {
        "ON_HOLD",
        "AWAITING_SHIPMENT",
        "READY_TO_SHIP",
        "READY_TO_SHIPMENT",
        "PAID",
        "SHIPPED",
        "DELIVERED",
        "COMPLETED",
    }:
        return "pending" if value == "ON_HOLD" else "confirmed"
    if value:
        return "pending"
    return "unknown"


def _order_line_timestamp(order: dict[str, Any], item: dict[str, Any]) -> str:
    return _first_present(
        item.get("update_time"),
        item.get("updated_at"),
        item.get("create_time"),
        order.get("update_time"),
        order.get("paid_time"),
        order.get("create_time"),
        order.get("created_at"),
    )


def _existing_sale_order(external_ref: str) -> dict[str, Any] | None:
    for order in list_sale_orders(order_source="tiktok_shop") or []:
        if str(order.get("external_order_ref") or "") == external_ref:
            return order
    return None


def _release_tiktok_reservation(sale_order_id: int) -> None:
    movements = list_inventory_movements_for_reference("tiktok_order_reserve", int(sale_order_id))
    releases = list_inventory_movements_for_reference("tiktok_order_reserve_release", int(sale_order_id))
    if not movements or releases:
        return
    for movement in movements:
        qty_delta = float(movement.get("qty_delta") or 0)
        if qty_delta:
            record_inventory_movement(
                int(movement["product_id"]),
                "reserve_release",
                -qty_delta,
                reason="TikTok order reservation released for shipment",
                reference_type="tiktok_order_reserve_release",
                reference_id=int(sale_order_id),
            )


async def fetch_tiktok_order_lines(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected", "lines": [], "orders_seen": 0, "pages_fetched": 0}
    page_size = max(1, min(int(payload.get("page_size") or 100), 100))
    max_pages = max(1, min(int(payload.get("max_pages") or 5), 20))
    params = {"page_size": page_size}
    cipher = _shop_cipher(record)
    if cipher:
        params["shop_cipher"] = cipher
    body: dict[str, Any] = {}
    if payload.get("create_time_ge"):
        body["create_time_ge"] = int(payload["create_time_ge"])
    if payload.get("create_time_lt"):
        body["create_time_lt"] = int(payload["create_time_lt"])
    page_token = str(payload.get("page_token") or "").strip()
    orders: list[dict[str, Any]] = []
    raw_pages: list[dict[str, Any]] = []
    for _ in range(max_pages):
        request_params = dict(params)
        if page_token:
            request_params["page_token"] = page_token
        data = await _signed_tiktok_request(
            record,
            "POST",
            "/order/202309/orders/search",
            params=request_params,
            body=body,
            operation="orders.search",
        )
        raw_pages.append(data)
        rows, page_token = _tiktok_order_rows(data)
        orders.extend(rows)
        if not page_token:
            break
    lines: list[dict[str, Any]] = []
    for order in orders:
        status = _order_status(order)
        recipient_address = order.get("recipient_address") if isinstance(order.get("recipient_address"), dict) else {}
        contact_fields = _tiktok_recipient_contact_fields(order)
        recipient_name = _first_present(
            order.get("recipient_name"),
            recipient_address.get("name"),
            " ".join(
                part
                for part in [
                    str(recipient_address.get("first_name") or "").strip(),
                    str(recipient_address.get("last_name") or "").strip(),
                ]
                if part
            ),
            order.get("buyer_name"),
            order.get("buyer_nickname"),
        )
        for item in _extract_order_items(order):
            seller_sku = _item_seller_sku(item)
            if not seller_sku:
                continue
            qty = _item_qty(item)
            unit_price = _money_amount(item.get("sale_price") or item.get("price") or item.get("sku_sale_price"))
            lines.append(
                {
                    "order_id": _first_present(order.get("id"), order.get("order_id"), order.get("external_order_id")),
                    "order_status": status,
                    "status_family": tiktok_order_status_family(status),
                    "seller_sku": seller_sku,
                    "buyer_name": _first_present(order.get("buyer_name"), order.get("buyer_nickname"), recipient_name),
                    "buyer_username": _first_present(order.get("buyer_nickname"), order.get("buyer_name")),
                    "buyer_user_id": _first_present(order.get("buyer_uid"), order.get("buyer_user_id")),
                    "recipient_name": recipient_name,
                    **contact_fields,
                    "product_name": _first_present(item.get("product_name"), item.get("name"), item.get("sku_name")),
                    "sku_id": _item_sku_id(item),
                    "quantity": qty,
                    "unit_price": unit_price,
                    "total_price": round(unit_price * qty, 4),
                    "currency": _first_present(
                        (item.get("sale_price") or {}).get("currency") if isinstance(item.get("sale_price"), dict) else "",
                        (item.get("price") or {}).get("currency") if isinstance(item.get("price"), dict) else "",
                        (order.get("payment") or {}).get("currency") if isinstance(order.get("payment"), dict) else "",
                    ),
                    "created_at": _first_present(order.get("create_time"), order.get("created_at")),
                    "paid_at": _first_present(order.get("paid_time"), order.get("payment_time")),
                    "updated_at": _order_line_timestamp(order, item),
                    "raw_order": order,
                    "raw_item": item,
                }
            )
    return {
        "ok": True,
        "lines": lines,
        "orders_seen": len(orders),
        "pages_fetched": len(raw_pages),
        "raw": raw_pages[-1] if raw_pages else {},
    }


def _normalize_tiktok_return(row: dict[str, Any] | None) -> dict[str, Any]:
    row = row or {}
    refund = _first_dict(row.get("refund"), row.get("refund_amount"), row.get("total_refund_amount"))
    order = _first_dict(row.get("order"), row.get("order_info"))
    amount = _money_amount(refund) if refund else _money_amount(row.get("refund_amount") or row.get("total_refund_amount") or row.get("amount"))
    line_items = _first_list(row.get("return_line_items"), row.get("line_items"), row.get("items"))
    return_id = _first_present(
        row.get("return_id"),
        row.get("return_order_id"),
        row.get("aftersale_id"),
        row.get("id"),
        row.get("request_id"),
    )
    order_id = _first_present(
        row.get("order_id"),
        row.get("order_line_id"),
        order.get("id"),
        order.get("order_id"),
    )
    return {
        "return_id": str(return_id or "").strip(),
        "order_id": str(order_id or "").strip(),
        "return_status": _first_present(row.get("return_status"), row.get("status"), row.get("aftersale_status")),
        "refund_status": _first_present(row.get("refund_status"), row.get("refund_state"), row.get("refund_status_text")),
        "return_type": _first_present(row.get("return_type"), row.get("type"), row.get("aftersale_type")),
        "reason": _first_present(row.get("reason"), row.get("return_reason"), row.get("buyer_reason")),
        "buyer_note": _first_present(row.get("buyer_note"), row.get("description"), row.get("comment")),
        "total_refund_amount": amount,
        "currency": _first_present(
            refund.get("currency") if isinstance(refund, dict) else "",
            row.get("currency"),
            row.get("refund_currency"),
        ),
        "line_items": line_items,
        "line_item_count": len(line_items),
        "raw": row,
    }


def _find_local_tiktok_sale_order(tiktok_order_id: str) -> dict[str, Any] | None:
    clean_order_id = str(tiktok_order_id or "").strip()
    if not clean_order_id:
        return None
    candidates = list_sale_orders_fast(order_source="tiktok", q=clean_order_id, limit=25) or []
    if not candidates:
        candidates = list_sale_orders(order_source="tiktok", q=clean_order_id) or []
    for order in candidates:
        external_ref = str(order.get("external_order_ref") or "")
        if external_ref == clean_order_id:
            return order
        if f":{clean_order_id}:" in external_ref or external_ref.endswith(f":{clean_order_id}") or external_ref.startswith(f"{clean_order_id}:"):
            return order
        notes = str(order.get("notes") or "")
        if clean_order_id and clean_order_id in notes:
            return order
    return None


def _return_line_seller_skus(normalized: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for item in normalized.get("line_items") or []:
        if not isinstance(item, dict):
            continue
        for key in ("seller_sku", "sku_name", "sku_id"):
            value = str(item.get(key) or "").strip()
            if value:
                values.add(value.lower())
    return values


def _order_lot_tokens(order: dict[str, Any], lines: list[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    external_ref = str((order or {}).get("external_order_ref") or "")
    for piece in re.split(r"[:\\-\\s]+", external_ref):
        piece = piece.strip()
        if piece:
            values.add(piece.lower())
    for line in lines or []:
        for key in ("lot_number", "sku", "barcode"):
            value = str(line.get(key) or "").strip()
            if value:
                values.add(value.lower())
    return values


def _can_auto_process_tiktok_return(order: dict[str, Any], normalized: dict[str, Any]) -> tuple[bool, str]:
    lines = list_sale_order_lines(int(order["id"])) if order and order.get("id") else []
    if len(lines) != 1:
        return False, f"manual_review_line_count_{len(lines)}"
    if int(normalized.get("line_item_count") or 0) != 1:
        return False, f"manual_review_return_lines_{int(normalized.get('line_item_count') or 0)}"
    seller_skus = _return_line_seller_skus(normalized)
    source = str(order.get("order_source") or "").strip().lower()
    if source == "tiktok_live" and seller_skus:
        order_tokens = _order_lot_tokens(order, lines)
        if not (seller_skus & order_tokens):
            return False, "manual_review_lot_mismatch"
    return True, "single_line_full_return"


def _return_is_final(normalized: dict[str, Any]) -> bool:
    text = " ".join(
        str(normalized.get(key) or "").strip().upper()
        for key in ("return_status", "refund_status", "return_type")
    )
    if not text:
        return False
    final_tokens = ("REFUNDED", "REFUND_SUCCESS", "SUCCESS", "COMPLETED", "COMPLETE")
    blocked_tokens = ("REJECT", "CANCEL", "DECLIN", "DENIED", "FAILED", "PENDING", "REVIEW", "WAIT")
    if any(token in text for token in blocked_tokens):
        return False
    return any(token in text for token in final_tokens)


def _append_return_note(order: dict[str, Any], normalized: dict[str, Any]) -> str:
    current = str((order or {}).get("notes") or "").strip()
    marker = f"TikTok return {normalized.get('return_id')}"
    if marker in current:
        return current
    note = (
        f"{marker}\n"
        f"TikTok order: {normalized.get('order_id') or '-'}\n"
        f"Return status: {normalized.get('return_status') or '-'}\n"
        f"Refund status: {normalized.get('refund_status') or '-'}\n"
        f"Reason: {normalized.get('reason') or '-'}"
    )
    return f"{current}\n\n{note}".strip() if current else note


async def fetch_tiktok_returns(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    record = _load_record(include_secrets=True)
    if not record.get("connected"):
        return {"ok": False, "error": "tiktok_shop_not_connected", "returns": [], "pages_fetched": 0}
    page_size = max(1, min(int(payload.get("page_size") or 50), 50))
    max_pages = max(1, min(int(payload.get("max_pages") or 3), 20))
    params = {"page_size": page_size}
    cipher = _shop_cipher(record)
    if cipher:
        params["shop_cipher"] = cipher
    body: dict[str, Any] = {}
    for key in ("create_time_ge", "create_time_lt", "update_time_ge", "update_time_lt"):
        if payload.get(key):
            body[key] = int(payload[key])
    if payload.get("order_id"):
        body["order_id"] = str(payload["order_id"]).strip()
    if payload.get("return_status"):
        body["return_status"] = str(payload["return_status"]).strip()
    page_token = str(payload.get("page_token") or "").strip()
    rows: list[dict[str, Any]] = []
    raw_pages: list[dict[str, Any]] = []
    for _ in range(max_pages):
        request_params = dict(params)
        if page_token:
            request_params["page_token"] = page_token
        data = await _signed_tiktok_request(
            record,
            "POST",
            "/return_refund/202309/returns/search",
            params=request_params,
            body=body,
            operation="returns.search",
        )
        raw_pages.append(data)
        page_rows, page_token = _tiktok_return_rows(data)
        rows.extend(_normalize_tiktok_return(row) for row in page_rows)
        if not page_token:
            break
    return {"ok": True, "returns": rows, "pages_fetched": len(raw_pages), "raw": raw_pages[-1] if raw_pages else {}}


async def sync_tiktok_returns(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(payload or {})
    monitor_only = payload.get("monitor_only") is not False and not payload.get("include_legacy")
    monitor_start_epoch = _returns_monitor_start_epoch(payload) if monitor_only else 0
    if monitor_only:
        payload["update_time_ge"] = max(_epoch_from_value(payload.get("update_time_ge")), monitor_start_epoch)
    fetched = await fetch_tiktok_returns(payload)
    if not fetched.get("ok"):
        return fetched
    results = []
    counts = {"seen": 0, "matched": 0, "processed": 0, "pending": 0, "unmatched": 0, "skipped": 0}
    for normalized in fetched.get("returns") or []:
        return_id = str(normalized.get("return_id") or "").strip()
        if not return_id:
            counts["skipped"] += 1
            continue
        counts["seen"] += 1
        order = _find_local_tiktok_sale_order(normalized.get("order_id"))
        sale_order_id = int(order["id"]) if order and order.get("id") else None
        if monitor_only and order:
            in_scope, scope_reason = _monitored_tiktok_order_reason(order, monitor_start_epoch)
            if not in_scope:
                counts["skipped"] += 1
                results.append({**normalized, "sale_order_id": sale_order_id, "action": scope_reason})
                continue
        if monitor_only and not order:
            return_event_epoch = _tiktok_return_event_epoch(normalized)
            if return_event_epoch and return_event_epoch < monitor_start_epoch:
                counts["skipped"] += 1
                results.append({**normalized, "sale_order_id": None, "action": "ignored_return_before_monitor_start"})
                continue
        if sale_order_id:
            counts["matched"] += 1
        else:
            counts["unmatched"] += 1
        stored = upsert_tiktok_return(
            return_id=return_id,
            order_id=normalized.get("order_id"),
            sale_order_id=sale_order_id,
            return_status=normalized.get("return_status"),
            refund_status=normalized.get("refund_status"),
            return_type=normalized.get("return_type"),
            reason=normalized.get("reason"),
            buyer_note=normalized.get("buyer_note"),
            total_refund_amount=normalized.get("total_refund_amount") or 0,
            currency=normalized.get("currency"),
            processed=False,
            raw_response=normalized.get("raw") or normalized,
        )
        action = "stored"
        is_final_return = _return_is_final(normalized)
        can_auto_process, process_reason = _can_auto_process_tiktok_return(order, normalized) if sale_order_id and order else (False, "unmatched")
        was_processed = int(stored.get("processed") or 0) == 1
        if sale_order_id and is_final_return and was_processed and not can_auto_process:
            stored = mark_tiktok_return_manual(
                return_id,
                sale_order_id=sale_order_id,
                note=f"Manual review required: {process_reason}",
            ) or stored
            counts["pending"] += 1
            action = process_reason
        elif sale_order_id and is_final_return and can_auto_process and not was_processed:
            updated_notes = _append_return_note(order, normalized)
            update_sale_order(
                sale_order_id,
                state="cancel",
                fulfillment_status="returned",
                payment_status="refunded",
                notes=updated_notes,
            )
            mark_tiktok_return_processed(return_id, sale_order_id=sale_order_id)
            counts["processed"] += 1
            action = "processed_return"
        elif sale_order_id and is_final_return and can_auto_process and was_processed:
            action = "already_processed"
        elif sale_order_id and is_final_return and not can_auto_process:
            counts["pending"] += 1
            action = process_reason
        elif not is_final_return:
            counts["pending"] += 1
            action = "pending_review"
        results.append({**normalized, "sale_order_id": sale_order_id, "action": action})
    return {
        "ok": True,
        "returns_seen": counts["seen"],
        "pages_fetched": fetched.get("pages_fetched") or 0,
        "monitor_only": monitor_only,
        "monitor_start_epoch": monitor_start_epoch,
        "counts": counts,
        "results": results,
    }


def list_tracked_tiktok_returns(limit: int = 200, processed: bool | None = None, q: str | None = None, monitor_only: bool = True) -> dict[str, Any]:
    rows = list_tiktok_returns(limit=limit, processed=processed, q=q)
    monitor_start_epoch = _returns_monitor_start_epoch({}) if monitor_only else 0
    if monitor_only:
        scoped_rows = []
        for row in rows:
            source = str(row.get("order_source") or "").strip().lower()
            if row.get("sale_order_id"):
                row_epoch = _epoch_from_value(row.get("sale_order_ordered_at") or row.get("sale_order_created_at"))
                if source in {"tiktok_shop", "tiktok_live"} and (not row_epoch or row_epoch >= monitor_start_epoch):
                    scoped_rows.append(row)
            elif _tiktok_return_event_epoch(row) >= monitor_start_epoch:
                scoped_rows.append(row)
        rows = scoped_rows
    summary = {
        "total": len(rows),
        "processed": sum(1 for row in rows if int(row.get("processed") or 0) == 1),
        "pending": sum(1 for row in rows if int(row.get("processed") or 0) != 1),
        "matched": sum(1 for row in rows if row.get("sale_order_id")),
        "unmatched": sum(1 for row in rows if not row.get("sale_order_id")),
        "refund_total": round(sum(float(row.get("total_refund_amount") or 0) for row in rows), 2),
    }
    return {"ok": True, "rows": rows, "summary": summary, "monitor_only": monitor_only, "monitor_start_epoch": monitor_start_epoch}


def get_recent_tiktok_order_line_matches(payload: dict[str, Any] | None = None, *, ttl_seconds: float = 12) -> dict[str, Any]:
    payload = dict(payload or {})
    if not payload.get("create_time_ge"):
        payload["create_time_ge"] = max(0, int(time.time()) - 24 * 3600)
    cache_key = json.dumps(payload, sort_keys=True, default=str)
    now = time.time()
    with _ORDER_LINE_CACHE_LOCK:
        if (
            _ORDER_LINE_CACHE.get("key") == cache_key
            and float(_ORDER_LINE_CACHE.get("expires_at") or 0) > now
            and isinstance(_ORDER_LINE_CACHE.get("value"), dict)
        ):
            return dict(_ORDER_LINE_CACHE["value"])
    result = asyncio.run(fetch_tiktok_order_lines(payload))
    if not result.get("ok"):
        return result
    matches: dict[str, dict[str, Any]] = {}
    for line in result.get("lines") or []:
        lot_key = str(line.get("seller_sku") or "").strip()
        if not lot_key:
            continue
        current = matches.get(lot_key)
        if current is None:
            matches[lot_key] = line
            continue
        current_rank = 2 if current.get("status_family") == "confirmed" else 1 if current.get("status_family") == "pending" else 0
        next_rank = 2 if line.get("status_family") == "confirmed" else 1 if line.get("status_family") == "pending" else 0
        current_ts = str(current.get("updated_at") or current.get("created_at") or "")
        next_ts = str(line.get("updated_at") or line.get("created_at") or "")
        if next_rank > current_rank or (next_rank == current_rank and next_ts >= current_ts):
            matches[lot_key] = line
    payload_result = {
        "ok": True,
        "matches": matches,
        "lines": result.get("lines") or [],
        "orders_seen": result.get("orders_seen") or 0,
        "pages_fetched": result.get("pages_fetched") or 0,
        "fetched_at": _utcnow(),
    }
    with _ORDER_LINE_CACHE_LOCK:
        _ORDER_LINE_CACHE["key"] = cache_key
        _ORDER_LINE_CACHE["expires_at"] = now + max(1.0, float(ttl_seconds or 12))
        _ORDER_LINE_CACHE["value"] = dict(payload_result)
    return payload_result


def import_tiktok_order(order: dict[str, Any], *, reserve_only: bool = False) -> dict[str, Any]:
    order_id = _tiktok_order_id(order)
    if not order_id:
        return {"ok": False, "status": "skipped", "error": "missing_order_id"}

    external_ref = str(order_id).strip()
    status = _order_status(order)
    status_family = tiktok_order_status_family(status)
    paid = _tiktok_order_is_paid(order)
    cancelled = _tiktok_order_is_cancelled(order)
    existing = _existing_sale_order(external_ref)
    if existing:
        update_sale_order(
            int(existing["id"]),
            state="cancel" if cancelled else "sale" if paid else "draft",
            fulfillment_status="cancelled" if cancelled else str(existing.get("fulfillment_status") or "pending"),
            payment_status="refunded" if cancelled else "paid" if paid else str(existing.get("payment_status") or "unpaid"),
        )
        return {
            "ok": True,
            "status": "updated_existing",
            "order_id": external_ref,
            "sale_order_id": int(existing["id"]),
            "status_family": status_family,
            "inventory_rule": "deducted_if_paid_else_not_deducted",
        }

    items = _extract_order_items(order)
    if not items:
        return {"ok": True, "status": "skipped_no_items", "order_id": external_ref, "status_family": status_family}

    recipient_address = order.get("recipient_address") if isinstance(order.get("recipient_address"), dict) else {}
    contact_fields = _tiktok_recipient_contact_fields(order)
    recipient_name = _first_present(
        order.get("recipient_name"),
        recipient_address.get("name"),
        " ".join(
            part
            for part in [
                str(recipient_address.get("first_name") or "").strip(),
                str(recipient_address.get("last_name") or "").strip(),
            ]
            if part
        ),
        order.get("buyer_name"),
        order.get("buyer_nickname"),
    )
    buyer_username = _first_present(order.get("buyer_nickname"), order.get("buyer_name"), recipient_name, order.get("buyer_uid"))
    customer = upsert_customer(
        buyer_username or external_ref,
        display_name=recipient_name or buyer_username,
        email=contact_fields.get("buyer_email"),
        phone=contact_fields.get("phone"),
        address=_customer_address_text(contact_fields),
        platform="tiktok_shop",
        platform_user_id=_first_present(order.get("buyer_uid"), order.get("buyer_user_id"), buyer_username),
        identity_username=buyer_username or recipient_name or external_ref,
    )
    order_notes = "\n".join(
        part for part in [
            "TikTok Shop API order",
            f"TikTok status: {status or '-'}",
            f"Recipient: {recipient_name}" if recipient_name else "",
        ] if part
    )
    sale_order = create_sale_order(
        session_id=None,
        customer_id=customer.get("id") if customer else None,
        buyer_group_id=None,
        whatnot_buyer_username=buyer_username or recipient_name,
        state="cancel" if cancelled else "sale" if paid else "draft",
        subtotal=0,
        total_amount=0,
        ordered_at=_first_present(order.get("paid_time"), order.get("create_time"), order.get("created_at")) or _utcnow(),
        notes=order_notes,
        order_source="tiktok_shop",
        external_order_ref=external_ref,
        fulfillment_status="cancelled" if cancelled else "pending",
        payment_status="refunded" if cancelled else "paid" if paid else "unpaid",
    )

    products = list_products(active_only=False, low_stock_only=False)
    matched = 0
    unmatched = 0
    for item in items:
        product, matched_by = _find_product_for_tiktok_item(item, products)
        if product:
            matched += 1
        else:
            unmatched += 1
        qty = _item_qty(item)
        unit_price = _money_amount(item.get("sale_price") or item.get("price") or item.get("sku_sale_price"))
        add_sale_order_line(
            int(sale_order["id"]),
            product_id=int(product["id"]) if product else None,
            description=_line_product_name(item) or (product or {}).get("name") or "TikTok Shop item",
            qty=qty,
            unit_price=unit_price,
            inventory_applied=0,
        )

    applied = 0
    if paid and not cancelled and not reserve_only:
        applied = int(apply_sale_order_inventory(int(sale_order["id"])) or 0)
    return {
        "ok": True,
        "status": "imported",
        "order_id": external_ref,
        "sale_order_id": int(sale_order["id"]),
        "status_family": status_family,
        "matched_lines": matched,
        "unmatched_lines": unmatched,
        "inventory_applied_lines": applied,
        "inventory_rule": "paid_orders_deduct_cancelled_orders_do_not",
    }


async def sync_tiktok_orders(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(payload or {})
    raw_orders = payload.get("orders")
    if isinstance(raw_orders, list):
        fetched = {"ok": True, "lines": [], "orders_seen": len(raw_orders), "pages_fetched": 0, "raw": {}, "orders": raw_orders}
        orders = [row for row in raw_orders if isinstance(row, dict)]
    else:
        record = _load_record(include_secrets=True)
        if not record.get("connected"):
            return {"ok": False, "error": "tiktok_shop_not_connected", "results": []}
        page_size = max(1, min(int(payload.get("page_size") or 100), 100))
        max_pages = max(1, min(int(payload.get("max_pages") or 5), 20))
        params = {"page_size": page_size}
        cipher = _shop_cipher(record)
        if cipher:
            params["shop_cipher"] = cipher
        body: dict[str, Any] = {}
        if payload.get("create_time_ge"):
            body["create_time_ge"] = int(payload["create_time_ge"])
        elif not payload.get("include_legacy"):
            body["create_time_ge"] = _local_today_start_epoch()
        if payload.get("create_time_lt"):
            body["create_time_lt"] = int(payload["create_time_lt"])
        page_token = str(payload.get("page_token") or "").strip()
        orders = []
        raw_pages = []
        for _ in range(max_pages):
            request_params = dict(params)
            if page_token:
                request_params["page_token"] = page_token
            data = await _signed_tiktok_request(
                record,
                "POST",
                "/order/202309/orders/search",
                params=request_params,
                body=body,
                operation="orders.search.import",
            )
            raw_pages.append(data)
            rows, page_token = _tiktok_order_rows(data)
            orders.extend(rows)
            if not page_token:
                break
        fetched = {
            "ok": True,
            "orders_seen": len(orders),
            "pages_fetched": len(raw_pages),
            "raw": raw_pages[-1] if raw_pages else {},
        }

    results = []
    counts: dict[str, int] = {}
    for order in orders:
        result = import_tiktok_order(order, reserve_only=False)
        results.append(result)
        key = str(result.get("status") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return {
        "ok": True,
        "orders_seen": fetched.get("orders_seen") or len(orders),
        "pages_fetched": fetched.get("pages_fetched") or 0,
        "results": results,
        "status_counts": counts,
        "message": "TikTok Shop paid orders are imported and deducted; cancelled/refunded orders do not deduct.",
        "raw": fetched.get("raw") or {},
    }


def _webhook_event_id(payload: dict[str, Any]) -> str:
    return _first_present(
        payload.get("event_id"),
        payload.get("id"),
        payload.get("message_id"),
        payload.get("data", {}).get("order_id") if isinstance(payload.get("data"), dict) else "",
        hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest(),
    )


async def handle_tiktok_webhook(payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    ensure_tiktok_shop_schema()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    event_type = _first_present(payload.get("type"), payload.get("event_type"), payload.get("event"))
    order_id = _first_present(data.get("order_id"), data.get("id")) if isinstance(data, dict) else ""
    event_id = _webhook_event_id(payload)
    is_new, _event = record_tiktok_webhook_event(event_id, event_type, order_id, payload)
    if not is_new:
        return {"ok": True, "status": "duplicate", "event_id": event_id}
    try:
        event_name = str(event_type or "").lower()
        should_trigger_order_sync = bool(
            order_id
            or any(
                token in event_name
                for token in ("order", "package", "cancellation", "return", "refund", "recipient_address")
            )
        )
        should_trigger_return_sync = any(token in event_name for token in ("return", "refund", "aftersale"))
        result = {"ok": True, "status": "stored_import_disabled"}
        if not _shop_order_import_enabled():
            result = {"ok": True, "status": "stored_import_disabled"}
        if should_trigger_return_sync:
            result = await sync_tiktok_returns({"page_size": 50, "max_pages": 3, "update_time_ge": max(0, int(time.time()) - 30 * 24 * 3600)})
        elif isinstance(data, dict) and _extract_order_items(data):
            # Go-live behavior: deduct inventory as soon as TikTok reports the sale.
            # If the order is later cancelled, the existing cancel path restores stock.
            result = result if not _shop_order_import_enabled() else import_tiktok_order(data, reserve_only=False)
        elif isinstance(data, dict) and order_id:
            result = result if not _shop_order_import_enabled() else await sync_tiktok_orders({"orders": [data]})
            if _shop_order_import_enabled() and not result.get("ok") and should_trigger_order_sync:
                result = await sync_tiktok_orders({"page_size": 50, "max_pages": 5, "create_time_ge": max(0, int(time.time()) - 14 * 24 * 3600)})
        elif should_trigger_order_sync:
            if _shop_order_import_enabled() and _enqueue_tiktok_shop_sync_task(72, 50, 5):
                result = {"ok": True, "status": "queued_recent_order_sync"}
            elif _shop_order_import_enabled():
                result = await sync_tiktok_orders({"page_size": 50, "max_pages": 5, "create_time_ge": max(0, int(time.time()) - 14 * 24 * 3600)})
            else:
                result = {"ok": True, "status": "stored_import_disabled"}
        else:
            result = {"ok": True, "status": "stored_no_order_payload"}
        mark_tiktok_webhook_event(event_id, processed=True)
        return {"ok": True, "event_id": event_id, "result": result}
    except Exception as exc:
        mark_tiktok_webhook_event(event_id, processed=False, error=str(exc))
        return {"ok": False, "event_id": event_id, "error": str(exc)}


def disconnect_tiktok_shop() -> dict[str, Any]:
    record = _load_record(include_secrets=True)
    if not record:
        return {"ok": True, "connection": {}}
    active_key = str(record.get("active_shop_key") or _shop_key(record)).strip()
    shops = []
    for shop in _normalize_shop_list(record):
        if active_key and str(shop.get("key") or "") == active_key:
            continue
        shops.append(shop)
    if shops:
        next_record = {**record, "shops": shops}
        next_record = _set_active_shop(next_record, str(shops[0].get("key") or ""))
        next_record["last_error"] = ""
        return {"ok": True, "connection": _save_record(next_record)}
    record.update({
        "connected": False,
        "access_token_encrypted": "",
        "refresh_token_encrypted": "",
        "last_error": "",
        "disconnected_at": _utcnow(),
        "active_shop_key": "",
        "shops": [],
    })
    return {"ok": True, "connection": _save_record(record)}
