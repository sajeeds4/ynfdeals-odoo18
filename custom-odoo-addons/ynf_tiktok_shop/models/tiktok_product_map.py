# -*- coding: utf-8 -*-
from odoo import api, fields, models


class YnfTiktokProductMap(models.Model):
    _name = "ynf.tiktok.product.map"
    _description = "TikTok Product Map"
    _order = "product_id"

    account_id = fields.Many2one(
        "ynf.tiktok.shop.account",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="account_id.company_id", store=True)
    active = fields.Boolean(default=True)
    product_id = fields.Many2one("product.product", required=True, ondelete="cascade", index=True)
    product_tmpl_id = fields.Many2one(related="product_id.product_tmpl_id", store=True)
    internal_sku = fields.Char(related="product_id.default_code", store=True)
    tiktok_product_id = fields.Char(required=True, index=True)
    tiktok_sku_id = fields.Char(required=True, index=True)
    tiktok_category_id = fields.Char()
    status = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("inactive", "Inactive")],
        default="active",
    )
    last_inventory_sync_at = fields.Datetime()
    last_odoo_qty = fields.Float()
    raw_response = fields.Text()

    _sql_constraints = [
        (
            "uniq_product_account",
            "unique(account_id, product_id)",
            "Each product can only be mapped once per TikTok account.",
        ),
        (
            "uniq_tiktok_sku_account",
            "unique(account_id, tiktok_sku_id)",
            "TikTok SKU must be unique per account.",
        ),
    ]

    @api.model
    def upsert_from_product(self, account, product, tiktok_product_id, tiktok_sku_id, **extra):
        domain = [("account_id", "=", account.id), ("product_id", "=", product.id)]
        mapping = self.search(domain, limit=1)
        vals = {
            "account_id": account.id,
            "product_id": product.id,
            "tiktok_product_id": tiktok_product_id,
            "tiktok_sku_id": tiktok_sku_id,
            "active": True,
            **extra,
        }
        if mapping:
            mapping.write(vals)
            return mapping
        return self.create(vals)
