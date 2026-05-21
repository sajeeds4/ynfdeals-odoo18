# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    x_ynf_tiktok_account_id = fields.Many2one(
        "ynf.tiktok.shop.account",
        string="TikTok Shop Account",
        copy=False,
        index=True,
    )
    x_ynf_tiktok_order_id = fields.Char(
        string="TikTok Order ID",
        copy=False,
        index=True,
    )
    x_ynf_tiktok_status = fields.Char(string="TikTok Order Status", copy=False)
    x_ynf_tiktok_package_id = fields.Char(string="TikTok Package ID", copy=False)
