# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .tiktok_shop_api import (
    DEFAULT_API_BASE,
    DEFAULT_AUTH_BASE,
    DEFAULT_AUTHORIZE_BASE,
    DEFAULT_REFRESH_URL,
    DEFAULT_TARGET_IDC,
    DEFAULT_TOKEN_URL,
)

_logger = logging.getLogger(__name__)


class YnfTiktokShopAccount(models.Model):
    _name = "ynf.tiktok.shop.account"
    _description = "TikTok Shop Account"
    _inherit = ["ynf.tiktok.shop.api", "mail.thread", "mail.activity.mixin"]
    _order = "sequence, id"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    is_connected = fields.Boolean(compute="_compute_connection_flags", store=True)
    access_token_valid = fields.Boolean(compute="_compute_connection_flags", store=True)
    last_error = fields.Text(tracking=True)

    # App credentials
    app_key = fields.Char(string="App Key", tracking=True)
    app_secret = fields.Char(string="App Secret", groups="ynf_tiktok_shop.group_tiktok_shop_manager")
    service_id = fields.Char(string="Service ID", tracking=True)
    redirect_uri = fields.Char(
        string="OAuth Redirect URI",
        help="Must match Partner Center app settings. Example: https://your-odoo.com/tiktok_shop/oauth/callback",
    )

    # Endpoint overrides
    api_base_url = fields.Char(default=DEFAULT_API_BASE)
    auth_base_url = fields.Char(default=DEFAULT_AUTH_BASE)
    authorize_base_url = fields.Char(default=DEFAULT_AUTHORIZE_BASE)
    token_url = fields.Char(default=DEFAULT_TOKEN_URL)
    refresh_url = fields.Char(default=DEFAULT_REFRESH_URL)
    target_idc = fields.Char(default=DEFAULT_TARGET_IDC, string="Target IDC")

    # Tokens (manager-only)
    access_token = fields.Char(groups="ynf_tiktok_shop.group_tiktok_shop_manager")
    refresh_token = fields.Char(groups="ynf_tiktok_shop.group_tiktok_shop_manager")
    access_token_expires_at = fields.Integer(string="Access Token Expires (epoch)")
    refresh_token_expires_at = fields.Integer(string="Refresh Token Expires (epoch)")

    # Shop identity
    merchant_id = fields.Char(tracking=True)
    seller_name = fields.Char()
    shop_id = fields.Char(tracking=True)
    shop_cipher = fields.Char(tracking=True, help="Required on most API calls for cross-border shops.")
    region = fields.Char()
    granted_scopes = fields.Text()
    authorized_shops_json = fields.Text(string="Authorized Shops (JSON)", readonly=True)

    # Sync settings
    auto_sync_orders = fields.Boolean(
        string="Auto Sync Orders",
        default=True,
        help="Cron and webhooks import TikTok Shop orders into Odoo sale orders.",
    )
    auto_sync_inventory = fields.Boolean(
        string="Auto Push Inventory",
        default=False,
        help="Cron pushes Odoo available qty to TikTok for mapped products.",
    )
    auto_sync_returns = fields.Boolean(string="Auto Sync Returns", default=True)
    order_import_days = fields.Integer(
        string="Order Lookback (days)",
        default=7,
        help="Default window when syncing orders without explicit dates.",
    )
    deduct_stock_on_import = fields.Boolean(
        string="Reserve Stock on Paid Import",
        default=True,
        help="Confirm sale and deliver stock when TikTok order is paid.",
    )
    sku_field = fields.Selection(
        [
            ("default_code", "Internal Reference (default_code)"),
            ("x_ynf_tiktok_seller_sku", "TikTok Seller SKU"),
            ("x_ynf_source_sku", "YNF Source SKU"),
            ("barcode", "Barcode"),
        ],
        default="x_ynf_tiktok_seller_sku",
        required=True,
    )
    webhook_secret = fields.Char(
        groups="ynf_tiktok_shop.group_tiktok_shop_manager",
        help="Optional shared secret to validate inbound webhooks.",
    )
    oauth_state = fields.Char(copy=False)

    last_connected_at = fields.Datetime(readonly=True)
    last_refreshed_at = fields.Datetime(readonly=True)
    last_tested_at = fields.Datetime(readonly=True)
    last_order_sync_at = fields.Datetime(readonly=True)
    last_inventory_sync_at = fields.Datetime(readonly=True)

    product_map_ids = fields.One2many("ynf.tiktok.product.map", "account_id")
    product_map_count = fields.Integer(compute="_compute_counts")
    api_log_ids = fields.One2many("ynf.tiktok.api.log", "account_id")
    api_log_count = fields.Integer(compute="_compute_counts")
    webhook_event_ids = fields.One2many("ynf.tiktok.webhook.event", "account_id")
    return_ids = fields.One2many("ynf.tiktok.return", "account_id")
    sale_order_ids = fields.One2many("sale.order", "x_ynf_tiktok_account_id")
    sale_order_count = fields.Integer(compute="_compute_counts")

    @api.depends("access_token", "access_token_expires_at")
    def _compute_connection_flags(self):
        now = int(datetime.now(timezone.utc).timestamp())
        for rec in self:
            rec.is_connected = bool(rec.access_token)
            rec.access_token_valid = bool(
                rec.access_token and rec.access_token_expires_at and rec.access_token_expires_at > now + 60
            )

    @api.depends("product_map_ids", "api_log_ids", "sale_order_ids")
    def _compute_counts(self):
        for rec in self:
            rec.product_map_count = len(rec.product_map_ids)
            rec.api_log_count = len(rec.api_log_ids)
            rec.sale_order_count = len(rec.sale_order_ids)

    def _ensure_access_token(self):
        self.ensure_one()
        now = int(datetime.now(timezone.utc).timestamp())
        if self.access_token_expires_at and self.access_token_expires_at <= now + 90:
            self.action_refresh_token()

    @api.model
    def _encryption_key(self) -> bytes:
        param = self.env["ir.config_parameter"].sudo().get_param("ynf.tiktok.encryption_key")
        if not param:
            param = secrets.token_urlsafe(32)
            self.env["ir.config_parameter"].sudo().set_param("ynf.tiktok.encryption_key", param)
        return base64.urlsafe_b64encode(hashlib.sha256(param.encode()).digest())

    def _encrypt_token(self, value: str) -> str:
        if not value:
            return ""
        try:
            from cryptography.fernet import Fernet
            return Fernet(self._encryption_key()).encrypt(value.encode()).decode()
        except ImportError:
            return value

    def _decrypt_token(self, value: str) -> str:
        if not value:
            return ""
        try:
            from cryptography.fernet import Fernet
            return Fernet(self._encryption_key()).decrypt(value.encode()).decode()
        except Exception:
            return value

    def _store_tokens(self, payload: dict):
        self.ensure_one()
        vals = {
            "access_token": self._encrypt_token(payload.get("access_token") or ""),
            "refresh_token": self._encrypt_token(payload.get("refresh_token") or ""),
            "access_token_expires_at": int(payload.get("access_token_expires_at") or 0),
            "refresh_token_expires_at": int(payload.get("refresh_token_expires_at") or 0),
            "shop_id": payload.get("shop_id") or self.shop_id,
            "shop_cipher": payload.get("shop_cipher") or self.shop_cipher,
            "merchant_id": payload.get("merchant_id") or self.merchant_id,
            "seller_name": payload.get("seller_name") or self.seller_name,
            "region": payload.get("region") or self.region,
            "granted_scopes": json.dumps(payload.get("granted_scopes") or []),
            "last_connected_at": fields.Datetime.now(),
            "last_error": False,
        }
        self.write(vals)

    def _read_stored_access_token(self) -> str:
        raw = self.access_token or ""
        return self._decrypt_token(raw) if raw else ""

    def _read_stored_refresh_token(self) -> str:
        raw = self.refresh_token or ""
        return self._decrypt_token(raw) if raw else ""

    def _get_app_secret(self) -> str:
        self.ensure_one()
        if not self.app_secret:
            raise UserError(_("App Secret is required on account %s.") % self.name)
        return self.app_secret.strip()

    def _get_access_token(self) -> str:
        self.ensure_one()
        token = self._read_stored_access_token()
        if not token:
            raise UserError(_("Connect TikTok Shop account %s first.") % self.name)
        return token

    def action_open_connect_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Connect TikTok Shop"),
            "res_model": "ynf.tiktok.connect.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_account_id": self.id},
        }

    def action_build_auth_url(self):
        self.ensure_one()
        state = secrets.token_urlsafe(24)
        self.write({"oauth_state": state})
        auth_url = self.build_auth_url(self, state)
        return {
            "type": "ir.actions.act_url",
            "url": auth_url,
            "target": "new",
        }

    def action_connect_with_code(self, auth_code: str):
        self.ensure_one()
        payload = self.exchange_token(self, auth_code=auth_code)
        self._store_tokens(payload)
        shops = self.fetch_authorized_shops(self)
        if shops:
            primary = shops[0]
            self.write({
                "shop_id": primary.get("shop_id") or self.shop_id,
                "shop_cipher": primary.get("shop_cipher") or self.shop_cipher,
                "region": primary.get("region") or self.region,
                "authorized_shops_json": json.dumps(shops, indent=2),
            })
        self.message_post(body=_("TikTok Shop connected successfully."))
        return True

    def action_refresh_token(self):
        self.ensure_one()
        refresh = self._read_stored_refresh_token()
        if not refresh:
            raise UserError(_("No refresh token stored."))
        payload = self.exchange_token(self, refresh_token=refresh)
        self._store_tokens(payload)
        self.write({"last_refreshed_at": fields.Datetime.now()})
        return True

    def action_test_connection(self):
        self.ensure_one()
        try:
            shops = self.fetch_authorized_shops(self)
            self.write({
                "authorized_shops_json": json.dumps(shops, indent=2),
                "last_tested_at": fields.Datetime.now(),
                "last_error": False,
            })
            if shops and not self.shop_cipher:
                self.shop_cipher = shops[0].get("shop_cipher")
            self.message_post(body=_("Connection test OK (%s shop(s)).") % len(shops))
        except Exception as exc:
            self.write({"last_error": str(exc)})
            raise
        return True

    def action_disconnect(self):
        self.write({
            "access_token": False,
            "refresh_token": False,
            "access_token_expires_at": 0,
            "refresh_token_expires_at": 0,
            "oauth_state": False,
            "last_error": False,
        })
        self.message_post(body=_("TikTok Shop disconnected."))

    def _resolve_product_from_sku(self, seller_sku: str):
        Product = self.env["product.product"]
        sku = (seller_sku or "").strip()
        if not sku:
            return Product.browse()
        field_name = self.sku_field
        if field_name == "barcode":
            return Product.search([("barcode", "=", sku)], limit=1)
        if field_name in ("default_code", "x_ynf_tiktok_seller_sku", "x_ynf_source_sku"):
            return Product.search([(field_name, "=", sku)], limit=1)
        return Product.search([("default_code", "=", sku)], limit=1)

    def _money(self, value) -> float:
        if isinstance(value, dict):
            try:
                return float(value.get("amount") or value.get("value") or 0)
            except (TypeError, ValueError):
                return 0.0
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _order_status(self, order: dict) -> str:
        return str(order.get("status") or order.get("order_status") or "").strip().upper()

    def _order_is_paid(self, order: dict) -> bool:
        status = self._order_status(order)
        if status in {"UNPAID", "CANCELLED", "CANCELED"}:
            return False
        payment = order.get("payment") if isinstance(order.get("payment"), dict) else {}
        if payment.get("payment_status"):
            return str(payment.get("payment_status")).upper() not in {"UNPAID", "FAILED"}
        return status not in {"UNPAID", "ON_HOLD"}

    def _order_is_cancelled(self, order: dict) -> bool:
        return self._order_status(order) in {"CANCELLED", "CANCELED", "UNPAID_CANCELLED"}

    def _extract_order_items(self, order: dict) -> list:
        for key in ("line_items", "item_list", "items", "skus"):
            val = order.get(key)
            if isinstance(val, list) and val:
                return val
        return []

    def _item_seller_sku(self, item: dict) -> str:
        return str(
            item.get("seller_sku")
            or item.get("sku_name")
            or (item.get("sku") or {}).get("seller_sku")
            or ""
        ).strip()

    def _item_qty(self, item: dict) -> float:
        for key in ("quantity", "sku_quantity", "qty"):
            if item.get(key) is not None:
                try:
                    return float(item[key])
                except (TypeError, ValueError):
                    pass
        return 1.0

    def _find_or_create_partner(self, order: dict):
        recipient = order.get("recipient_address") if isinstance(order.get("recipient_address"), dict) else {}
        name = (
            order.get("recipient_name")
            or recipient.get("name")
            or order.get("buyer_name")
            or order.get("buyer_nickname")
            or _("TikTok Buyer")
        )
        email = order.get("buyer_email") or order.get("email")
        phone = recipient.get("phone_number") or recipient.get("phone") or order.get("phone_number")
        ref = str(order.get("buyer_uid") or order.get("buyer_user_id") or order.get("buyer_nickname") or "").strip()
        domain = [("ref", "=", ref)] if ref else [("name", "=", name)]
        partner = self.env["res.partner"].search(domain, limit=1)
        if partner:
            return partner
        return self.env["res.partner"].create({
            "name": name,
            "email": email,
            "phone": phone,
            "ref": ref or False,
            "street": recipient.get("address_line1") or recipient.get("address_line_1"),
            "street2": recipient.get("address_line2") or recipient.get("address_line_2"),
            "city": recipient.get("city"),
            "zip": recipient.get("postal_code") or recipient.get("zipcode"),
            "country_id": self._country_from_code(recipient.get("region_code") or recipient.get("region")),
        })

    def _country_from_code(self, code):
        if not code:
            return False
        return self.env["res.country"].search([("code", "=", str(code).upper()[:2])], limit=1).id

    def import_order(self, order: dict) -> dict:
        self.ensure_one()
        order_id = str(order.get("id") or order.get("order_id") or "").strip()
        if not order_id:
            return {"status": "skipped", "reason": "missing_order_id"}

        SaleOrder = self.env["sale.order"]
        existing = SaleOrder.search([
            ("x_ynf_tiktok_order_id", "=", order_id),
            ("x_ynf_tiktok_account_id", "=", self.id),
        ], limit=1)

        paid = self._order_is_paid(order)
        cancelled = self._order_is_cancelled(order)

        if existing:
            if cancelled:
                existing.action_cancel()
            elif paid and existing.state in ("draft", "sent"):
                existing.action_confirm()
            existing.write({
                "x_ynf_tiktok_status": self._order_status(order),
                "x_ynf_tiktok_buyer_username": order.get("buyer_nickname") or order.get("buyer_name"),
            })
            return {"status": "updated", "sale_order_id": existing.id}

        partner = self._find_or_create_partner(order)
        lines = []
        for item in self._extract_order_items(order):
            sku = self._item_seller_sku(item)
            product = self._resolve_product_from_sku(sku)
            qty = self._item_qty(item)
            price = self._money(item.get("sale_price") or item.get("price") or item.get("sku_sale_price"))
            line_vals = {
                "name": item.get("product_name") or item.get("name") or sku or _("TikTok item"),
                "product_uom_qty": qty,
                "price_unit": price,
            }
            if product:
                line_vals["product_id"] = product.id
            lines.append((0, 0, line_vals))

        if not lines:
            return {"status": "skipped", "reason": "no_lines"}

        so = SaleOrder.create({
            "partner_id": partner.id,
            "company_id": self.company_id.id,
            "x_ynf_sale_channel": "tiktok_shop",
            "x_ynf_tiktok_account_id": self.id,
            "x_ynf_tiktok_order_id": order_id,
            "x_ynf_tiktok_status": self._order_status(order),
            "x_ynf_tiktok_buyer_username": order.get("buyer_nickname") or order.get("buyer_name"),
            "origin": f"TikTok Shop {order_id}",
            "note": _("Imported from TikTok Shop API"),
            "order_line": lines,
        })
        if cancelled:
            so.action_cancel()
        elif paid:
            so.action_confirm()
            if self.deduct_stock_on_import:
                for picking in so.picking_ids.filtered(lambda p: p.state not in ("done", "cancel")):
                    for move in picking.move_ids:
                        move.quantity = move.product_uom_qty
                    picking.button_validate()

        return {"status": "created", "sale_order_id": so.id}

    def action_sync_orders(self, days: int | None = None):
        self.ensure_one()
        import time
        lookback = days if days is not None else self.order_import_days
        body = {"create_time_ge": int(time.time()) - int(lookback) * 86400}
        orders = self.search_orders(self, body=body)
        results = []
        for order in orders:
            try:
                results.append(self.import_order(order))
            except Exception as exc:
                _logger.exception("TikTok order import failed")
                results.append({"status": "error", "order_id": order.get("id"), "error": str(exc)})
        self.write({"last_order_sync_at": fields.Datetime.now()})
        created = sum(1 for r in results if r.get("status") == "created")
        updated = sum(1 for r in results if r.get("status") == "updated")
        self.message_post(body=_("Order sync: %(created)s created, %(updated)s updated, %(total)s seen.") % {
            "created": created,
            "updated": updated,
            "total": len(orders),
        })
        return results

    def action_sync_inventory(self):
        self.ensure_one()
        Map = self.env["ynf.tiktok.product.map"]
        maps = Map.search([("account_id", "=", self.id), ("tiktok_product_id", "!=", False), ("active", "=", True)])
        updated = 0
        for mapping in maps:
            product = mapping.product_id
            if not product:
                continue
            qty = int(product.free_qty)
            if not mapping.tiktok_sku_id:
                continue
            body_skus = [{
                "id": mapping.tiktok_sku_id,
                "inventory": [{"quantity": max(0, qty)}],
            }]
            self.update_product_inventory(self, mapping.tiktok_product_id, body_skus)
            mapping.write({"last_inventory_sync_at": fields.Datetime.now(), "last_odoo_qty": qty})
            updated += 1
        self.write({"last_inventory_sync_at": fields.Datetime.now()})
        self.message_post(body=_("Inventory pushed for %(n)s product(s).") % {"n": updated})
        return updated

    def action_sync_returns(self):
        self.ensure_one()
        rows = self.search_returns(self, body={})
        Return = self.env["ynf.tiktok.return"]
        for row in rows:
            rid = str(row.get("return_id") or row.get("id") or "").strip()
            if not rid:
                continue
            Return.sync_from_api_row(self, row)
        self.message_post(body=_("Returns sync: %(n)s row(s) processed.") % {"n": len(rows)})
        return len(rows)

    @api.model
    def cron_refresh_tokens(self):
        now = int(datetime.now(timezone.utc).timestamp())
        accounts = self.search([("active", "=", True), ("access_token", "!=", False)])
        for account in accounts:
            if account.access_token_expires_at and account.access_token_expires_at <= now + 300:
                try:
                    account.action_refresh_token()
                except Exception as exc:
                    account.write({"last_error": str(exc)})
                    _logger.warning("TikTok token refresh failed for %s: %s", account.name, exc)

    @api.model
    def cron_sync_orders(self):
        for account in self.search([("active", "=", True), ("auto_sync_orders", "=", True), ("is_connected", "=", True)]):
            try:
                account.action_sync_orders()
            except Exception as exc:
                account.write({"last_error": str(exc)})

    @api.model
    def cron_sync_inventory(self):
        for account in self.search([("active", "=", True), ("auto_sync_inventory", "=", True), ("is_connected", "=", True)]):
            try:
                account.action_sync_inventory()
            except Exception as exc:
                account.write({"last_error": str(exc)})

    @api.model
    def cron_sync_returns(self):
        for account in self.search([("active", "=", True), ("auto_sync_returns", "=", True), ("is_connected", "=", True)]):
            try:
                account.action_sync_returns()
            except Exception as exc:
                account.write({"last_error": str(exc)})
