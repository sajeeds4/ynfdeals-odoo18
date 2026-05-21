# -*- coding: utf-8 -*-
import hashlib
import json

from odoo import api, fields, models


class YnfTiktokWebhookEvent(models.Model):
    _name = "ynf.tiktok.webhook.event"
    _description = "TikTok Webhook Event"
    _order = "create_date desc"

    account_id = fields.Many2one("ynf.tiktok.shop.account", ondelete="set null", index=True)
    event_id = fields.Char(required=True, index=True)
    event_type = fields.Char(index=True)
    order_id = fields.Char(index=True)
    payload_json = fields.Text(required=True)
    processed = fields.Boolean(default=False, index=True)
    processed_at = fields.Datetime()
    error = fields.Text()

    _sql_constraints = [
        ("uniq_event_id", "unique(event_id)", "Webhook event already exists."),
    ]

    @api.model
    def _event_id_from_payload(self, payload: dict) -> str:
        for key in ("event_id", "id", "message_id"):
            if payload.get(key):
                return str(payload[key])
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    @api.model
    def record_event(self, account, payload: dict) -> tuple[bool, "YnfTiktokWebhookEvent"]:
        event_id = self._event_id_from_payload(payload)
        existing = self.search([("event_id", "=", event_id)], limit=1)
        if existing:
            return False, existing
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        order_id = ""
        if isinstance(data, dict):
            order_id = str(data.get("order_id") or data.get("id") or "")
        event = self.create({
            "account_id": account.id if account else False,
            "event_id": event_id,
            "event_type": str(payload.get("type") or payload.get("event_type") or payload.get("event") or ""),
            "order_id": order_id,
            "payload_json": json.dumps(payload, default=str),
        })
        return True, event

    def action_process(self):
        for event in self:
            account = event.account_id
            if not account:
                event.write({"processed": True, "error": "no_account"})
                continue
            try:
                name = (event.event_type or "").lower()
                if any(t in name for t in ("return", "refund", "aftersale")):
                    account.action_sync_returns()
                elif any(t in name for t in ("order", "package", "cancellation", "recipient")):
                    if account.auto_sync_orders:
                        account.action_sync_orders(days=3)
                event.write({"processed": True, "processed_at": fields.Datetime.now(), "error": False})
            except Exception as exc:
                event.write({"processed": False, "error": str(exc)})
