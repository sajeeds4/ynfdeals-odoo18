# -*- coding: utf-8 -*-
from odoo import fields, models


class YnfTiktokApiLog(models.Model):
    _name = "ynf.tiktok.api.log"
    _description = "TikTok API Log"
    _order = "create_date desc"

    account_id = fields.Many2one("ynf.tiktok.shop.account", ondelete="set null", index=True)
    operation = fields.Char(required=True, index=True)
    method = fields.Char()
    path = fields.Char()
    status_code = fields.Integer()
    ok = fields.Boolean(default=False, index=True)
    request_json = fields.Text()
    response_json = fields.Text()
    error = fields.Text()
