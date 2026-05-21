# -*- coding: utf-8 -*-
from odoo import fields, models


class YnfTiktokCategoryMap(models.Model):
    _name = "ynf.tiktok.category.map"
    _description = "TikTok Category Map"

    account_id = fields.Many2one("ynf.tiktok.shop.account", ondelete="cascade")
    name = fields.Char(string="Internal Category", required=True)
    tiktok_category_id = fields.Char(required=True, index=True)
    tiktok_category_name = fields.Char()
    is_leaf = fields.Boolean(default=True)
    rules_json = fields.Text()
