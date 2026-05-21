# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class TiktokShopController(http.Controller):

    @http.route("/tiktok_shop/oauth/callback", type="http", auth="public", methods=["GET"], csrf=False, sitemap=False)
    def oauth_callback(self, **kwargs):
        """OAuth redirect target — register this URL in TikTok Partner Center."""
        code = kwargs.get("code") or kwargs.get("auth_code")
        state = kwargs.get("state")
        error = kwargs.get("error") or kwargs.get("error_description")
        Account = request.env["ynf.tiktok.shop.account"].sudo()
        account = Account.search([("oauth_state", "=", state)], limit=1) if state else Account.browse()
        if not account and state:
            account = Account.search([], limit=1)
        if error:
            return request.render("ynf_tiktok_shop.oauth_result", {
                "success": False,
                "message": str(error),
            })
        if not code:
            return request.render("ynf_tiktok_shop.oauth_result", {
                "success": False,
                "message": "Missing authorization code.",
            })
        try:
            if not account:
                raise ValueError("No TikTok account matched this OAuth state. Open Connect from the account form first.")
            account.action_connect_with_code(code)
            account.write({"oauth_state": False})
            return request.render("ynf_tiktok_shop.oauth_result", {
                "success": True,
                "message": "TikTok Shop connected. You can close this window and return to Odoo.",
                "account_name": account.name,
            })
        except Exception as exc:
            _logger.exception("TikTok OAuth callback failed")
            if account:
                account.write({"last_error": str(exc)})
            return request.render("ynf_tiktok_shop.oauth_result", {
                "success": False,
                "message": str(exc),
            })

    @http.route("/tiktok_shop/webhook", type="json", auth="public", methods=["POST"], csrf=False, sitemap=False)
    def webhook_json(self, **kwargs):
        return self._handle_webhook(request.httprequest.data)

    @http.route("/tiktok_shop/webhook", type="http", auth="public", methods=["POST"], csrf=False, sitemap=False)
    def webhook_http(self, **kwargs):
        return request.make_json_response(self._handle_webhook(request.httprequest.data))

    def _handle_webhook(self, raw_body):
        try:
            payload = json.loads(raw_body.decode("utf-8") if raw_body else "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        Account = request.env["ynf.tiktok.shop.account"].sudo()
        account = Account.search([("active", "=", True), ("is_connected", "=", True)], limit=1)
        shop_cipher = ""
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        if isinstance(data, dict):
            shop_cipher = str(data.get("shop_cipher") or "")
        if shop_cipher:
            matched = Account.search([("shop_cipher", "=", shop_cipher)], limit=1)
            if matched:
                account = matched

        Webhook = request.env["ynf.tiktok.webhook.event"].sudo()
        is_new, event = Webhook.record_event(account, payload)
        if is_new and account and account.auto_sync_orders:
            try:
                event.action_process()
            except Exception as exc:
                event.write({"error": str(exc)})
                return {"ok": False, "error": str(exc)}
        return {"ok": True, "duplicate": not is_new, "event_id": event.event_id}
