# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models


class YnfTiktokReturn(models.Model):
    _name = "ynf.tiktok.return"
    _description = "TikTok Return"
    _order = "write_date desc"

    account_id = fields.Many2one("ynf.tiktok.shop.account", required=True, ondelete="cascade")
    return_id = fields.Char(required=True, index=True)
    order_id = fields.Char(index=True)
    sale_order_id = fields.Many2one("sale.order", ondelete="set null")
    return_status = fields.Char()
    refund_status = fields.Char()
    return_type = fields.Char()
    reason = fields.Text()
    buyer_note = fields.Text()
    total_refund_amount = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
    processed = fields.Boolean(default=False, index=True)
    processed_at = fields.Datetime()
    raw_response = fields.Text()

    _sql_constraints = [
        ("uniq_return_account", "unique(account_id, return_id)", "Return already tracked."),
    ]

    @api.model
    def sync_from_api_row(self, account, row: dict):
        rid = str(row.get("return_id") or row.get("return_order_id") or row.get("id") or "").strip()
        if not rid:
            return self.browse()
        order_id = str(row.get("order_id") or "").strip()
        sale_order = False
        if order_id:
            sale_order = self.env["sale.order"].search([
                ("x_ynf_tiktok_order_id", "=", order_id),
                ("x_ynf_tiktok_account_id", "=", account.id),
            ], limit=1)
        refund = row.get("refund") if isinstance(row.get("refund"), dict) else {}
        amount = 0.0
        if isinstance(refund, dict):
            try:
                amount = float(refund.get("amount") or refund.get("value") or 0)
            except (TypeError, ValueError):
                amount = 0.0
        vals = {
            "account_id": account.id,
            "return_id": rid,
            "order_id": order_id,
            "sale_order_id": sale_order.id if sale_order else False,
            "return_status": row.get("return_status") or row.get("status"),
            "refund_status": row.get("refund_status"),
            "return_type": row.get("return_type") or row.get("type"),
            "reason": row.get("reason") or row.get("return_reason"),
            "buyer_note": row.get("buyer_note") or row.get("description"),
            "total_refund_amount": amount,
            "raw_response": json.dumps(row, default=str),
        }
        existing = self.search([("account_id", "=", account.id), ("return_id", "=", rid)], limit=1)
        if existing:
            existing.write(vals)
            rec = existing
        else:
            rec = self.create(vals)
        status_text = " ".join(
            str(rec.get(k) or "").upper() for k in ("return_status", "refund_status")
        )
        if sale_order and any(t in status_text for t in ("REFUNDED", "SUCCESS", "COMPLETED")):
            if sale_order.state != "cancel":
                sale_order.action_cancel()
            sale_order.write({"x_ynf_fulfillment_status": "returned"})
            rec.write({"processed": True, "processed_at": fields.Datetime.now()})
        return rec
