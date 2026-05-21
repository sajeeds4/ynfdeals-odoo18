# -*- coding: utf-8 -*-
"""TikTok Shop Open API client (Partner Center 202309)."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://open-api.tiktokglobalshop.com"
DEFAULT_AUTH_BASE = "https://auth.tiktok-shops.com"
DEFAULT_AUTHORIZE_BASE = "https://services.us.tiktokshop.com"
DEFAULT_TOKEN_URL = "https://auth.tiktok-shops.com/api/v2/token/get"
DEFAULT_REFRESH_URL = "https://auth.tiktok-shops.com/api/v2/token/refresh"
DEFAULT_TARGET_IDC = "alisg"


class TiktokShopApi(models.AbstractModel):
    _name = "ynf.tiktok.shop.api"
    _description = "TikTok Shop API Client"

    # ------------------------------------------------------------------ HTTP
    def _http_request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        body: dict | None = None,
        headers: dict | None = None,
        timeout: int = 60,
    ) -> tuple[int, dict]:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        full_url = f"{url}?{query}" if query else url
        data = None
        req_headers = {"Content-Type": "application/json", **(headers or {})}
        if body is not None:
            data = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            full_url,
            data=data,
            headers=req_headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = response.getcode()
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        if not isinstance(payload, dict):
            payload = {"data": payload}
        return status, payload

    def _tiktok_sign(self, path: str, params: dict, app_secret: str, body: dict | None = None) -> str:
        sign_params = {
            str(k): str(v)
            for k, v in params.items()
            if v is not None and str(k) not in {"access_token", "sign"}
        }
        sign_source = path + "".join(f"{k}{sign_params[k]}" for k in sorted(sign_params))
        if body is not None:
            sign_source += json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        sign_source = f"{app_secret}{sign_source}{app_secret}"
        return hmac.new(
            app_secret.encode("utf-8"),
            sign_source.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _api_request(
        self,
        account,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        body: dict | None = None,
        operation: str | None = None,
    ) -> dict:
        account.ensure_one()
        account._ensure_access_token()
        app_secret = account._get_app_secret()
        access_token = account._get_access_token()
        query = {
            "app_key": account.app_key,
            "timestamp": int(time.time()),
            "access_token": access_token,
            **(params or {}),
        }
        query["sign"] = self._tiktok_sign(path, query, app_secret, body if method.upper() != "GET" else None)
        headers = {
            "x-tts-access-token": access_token,
            "Content-Type": "application/json",
        }
        if account.target_idc:
            headers["x-tt-target-idc"] = account.target_idc
        base = (account.api_base_url or DEFAULT_API_BASE).rstrip("/")
        url = f"{base}{path}"
        status, data = self._http_request(method, url, params=query, body=body, headers=headers)
        ok = status < 400 and (not isinstance(data, dict) or data.get("code") in (None, 0, "0"))
        self.env["ynf.tiktok.api.log"].sudo().create({
            "account_id": account.id,
            "operation": operation or path.strip("/").replace("/", "."),
            "method": method.upper(),
            "path": path,
            "status_code": status,
            "ok": ok,
            "request_json": json.dumps(
                {"params": {k: "***" if k in {"access_token", "sign"} else v for k, v in query.items()}, "body": body},
                default=str,
            ),
            "response_json": json.dumps(data, default=str)[:50000],
            "error": "" if ok else str(data),
        })
        if not ok:
            raise UserError(_("TikTok API error (%(path)s): %(msg)s", path=path, msg=data))
        return data

    def _api_get(self, account, path: str, params: dict | None = None, operation: str | None = None) -> dict:
        return self._api_request(account, "GET", path, params=params, operation=operation)

    def _api_post(self, account, path: str, params: dict | None = None, body: dict | None = None, operation: str | None = None) -> dict:
        return self._api_request(account, "POST", path, params=params, body=body, operation=operation)

    def _shop_params(self, account) -> dict:
        if account.shop_cipher:
            return {"shop_cipher": account.shop_cipher}
        return {}

    # -------------------------------------------------------------- Auth/token
    def exchange_token(self, account, *, auth_code: str | None = None, refresh_token: str | None = None) -> dict:
        account.ensure_one()
        app_secret = account._get_app_secret()
        params = {
            "app_key": account.app_key,
            "app_secret": app_secret,
        }
        if refresh_token:
            params.update({"grant_type": "refresh_token", "refresh_token": refresh_token})
            url = account.refresh_url or DEFAULT_REFRESH_URL
            op = "auth.refresh"
        elif auth_code:
            params.update({"grant_type": "authorized_code", "auth_code": auth_code})
            url = account.token_url or DEFAULT_TOKEN_URL
            op = "auth.token"
        else:
            raise UserError(_("Provide an authorization code or refresh token."))
        headers = {}
        if account.target_idc:
            headers["x-tt-target-idc"] = account.target_idc
        status, data = self._http_request("GET", url, params=params, headers=headers)
        ok = status < 400 and data.get("code") in (None, 0, "0")
        self.env["ynf.tiktok.api.log"].sudo().create({
            "account_id": account.id,
            "operation": op,
            "method": "GET",
            "path": url,
            "status_code": status,
            "ok": ok,
            "request_json": json.dumps({k: "***" if "secret" in k or "token" in k else v for k, v in params.items()}),
            "response_json": json.dumps(data, default=str)[:20000],
            "error": "" if ok else str(data),
        })
        if not ok:
            raise UserError(_("TikTok token exchange failed: %s") % data)
        return self._normalize_token_payload(data)

    @staticmethod
    def _normalize_token_payload(data: dict) -> dict:
        token_data = data.get("data") if isinstance(data.get("data"), dict) else data
        now = int(time.time())

        def as_expiry(value, fallback_seconds=0):
            try:
                num = int(value or 0)
            except (TypeError, ValueError):
                num = 0
            if num and num < 10_000_000_000:
                return now + num
            return num or (now + fallback_seconds if fallback_seconds else 0)

        return {
            "access_token": token_data.get("access_token") or token_data.get("accessToken") or "",
            "refresh_token": token_data.get("refresh_token") or token_data.get("refreshToken") or "",
            "access_token_expires_at": as_expiry(
                token_data.get("access_token_expire_in")
                or token_data.get("access_token_expire_at")
                or token_data.get("expires_in"),
                fallback_seconds=5 * 24 * 3600,
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

    def build_auth_url(self, account, state: str) -> str:
        account.ensure_one()
        if not account.app_key and not account.service_id:
            raise UserError(_("Configure App Key or Service ID on the TikTok Shop account."))
        if account.service_id:
            params = {"service_id": account.service_id, "state": state}
            if account.redirect_uri:
                params["redirect_uri"] = account.redirect_uri
            base = (account.authorize_base_url or DEFAULT_AUTHORIZE_BASE).rstrip("/")
            return f"{base}/open/authorize?{urllib.parse.urlencode(params)}"
        params = {"app_key": account.app_key, "state": state}
        if account.redirect_uri:
            params["redirect_uri"] = account.redirect_uri
        base = (account.auth_base_url or DEFAULT_AUTH_BASE).rstrip("/")
        return f"{base}/api/v2/token/authorize?{urllib.parse.urlencode(params)}"

    # -------------------------------------------------------------- API calls
    def fetch_authorized_shops(self, account) -> list[dict]:
        data = self._api_get(account, "/authorization/202309/shops", operation="authorization.shops")
        root = data.get("data") if isinstance(data.get("data"), dict) else data
        shops = root.get("shops") if isinstance(root, dict) else []
        if not isinstance(shops, list):
            return []
        return [
            {
                "shop_id": str(s.get("id") or s.get("shop_id") or "").strip(),
                "shop_cipher": str(s.get("cipher") or s.get("shop_cipher") or "").strip(),
                "name": str(s.get("name") or s.get("shop_name") or "").strip(),
                "region": str(s.get("region") or s.get("seller_base_region") or "").strip(),
            }
            for s in shops
            if isinstance(s, dict)
        ]

    def search_orders(self, account, body: dict | None = None, *, page_size: int = 50, max_pages: int = 5) -> list[dict]:
        params = {"page_size": page_size, **self._shop_params(account)}
        body = dict(body or {})
        orders = []
        page_token = ""
        for _ in range(max_pages):
            if page_token:
                params["page_token"] = page_token
            data = self._api_post(
                account,
                "/order/202309/orders/search",
                params=params,
                body=body,
                operation="orders.search",
            )
            root = data.get("data") if isinstance(data.get("data"), dict) else {}
            rows = root.get("orders") or root.get("order_list") or []
            if isinstance(rows, list):
                orders.extend(rows)
            page_token = str(root.get("next_page_token") or root.get("page_token") or "").strip()
            if not page_token:
                break
        return orders

    def search_returns(self, account, body: dict | None = None, *, page_size: int = 50, max_pages: int = 3) -> list[dict]:
        params = {"page_size": page_size, **self._shop_params(account)}
        body = dict(body or {})
        rows = []
        page_token = ""
        for _ in range(max_pages):
            if page_token:
                params["page_token"] = page_token
            data = self._api_post(
                account,
                "/return_refund/202309/returns/search",
                params=params,
                body=body,
                operation="returns.search",
            )
            root = data.get("data") if isinstance(data.get("data"), dict) else {}
            chunk = root.get("return_orders") or root.get("returns") or []
            if isinstance(chunk, list):
                rows.extend(chunk)
            page_token = str(root.get("next_page_token") or "").strip()
            if not page_token:
                break
        return rows

    def search_products(self, account, body: dict | None = None, *, page_size: int = 50, max_pages: int = 4) -> list[dict]:
        params = {"page_size": page_size, **self._shop_params(account)}
        body = dict(body or {})
        products = []
        page_token = ""
        for _ in range(max_pages):
            if page_token:
                params["page_token"] = page_token
            data = self._api_post(
                account,
                "/product/202309/products/search",
                params=params,
                body=body,
                operation="products.search",
            )
            root = data.get("data") if isinstance(data.get("data"), dict) else {}
            chunk = root.get("products") or []
            if isinstance(chunk, list):
                products.extend(chunk)
            page_token = str(root.get("next_page_token") or "").strip()
            if not page_token:
                break
        return products

    def update_product_inventory(self, account, tiktok_product_id: str, skus: list[dict]) -> dict:
        params = self._shop_params(account)
        body = {"skus": skus}
        return self._api_post(
            account,
            f"/product/202309/products/{tiktok_product_id}/inventory/update",
            params=params,
            body=body,
            operation="inventory.update",
        )

    def fetch_warehouses(self, account) -> list[dict]:
        data = self._api_get(
            account,
            "/logistics/202309/warehouses",
            params=self._shop_params(account),
            operation="logistics.warehouses",
        )
        root = data.get("data") if isinstance(data.get("data"), dict) else {}
        wh = root.get("warehouses") or []
        return wh if isinstance(wh, list) else []

    def fetch_global_categories(self, account, parent_id: str | None = None) -> list[dict]:
        params = self._shop_params(account)
        if parent_id:
            params["parent_id"] = parent_id
        data = self._api_get(account, "/product/202309/global_categories", params=params, operation="categories.global")
        root = data.get("data") if isinstance(data.get("data"), dict) else {}
        cats = root.get("categories") or []
        return cats if isinstance(cats, list) else []

    def search_packages(self, account, body: dict | None = None, *, page_size: int = 50, max_pages: int = 3) -> list[dict]:
        params = {"page_size": page_size, **self._shop_params(account)}
        body = dict(body or {})
        packages = []
        page_token = ""
        for _ in range(max_pages):
            if page_token:
                params["page_token"] = page_token
            data = self._api_post(
                account,
                "/fulfillment/202309/packages/search",
                params=params,
                body=body,
                operation="packages.search",
            )
            root = data.get("data") if isinstance(data.get("data"), dict) else {}
            chunk = root.get("packages") or []
            if isinstance(chunk, list):
                packages.extend(chunk)
            page_token = str(root.get("next_page_token") or "").strip()
            if not page_token:
                break
        return packages
