# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    x_ynf_tiktok_account_id = fields.Many2one(
        "ynf.tiktok.shop.account",
        string="TikTok Shop Account",
    )
    x_ynf_tiktok_product_id = fields.Char(string="TikTok Product ID", copy=False, index=True)
    x_ynf_tiktok_sku_id = fields.Char(string="TikTok SKU ID", copy=False)
    x_ynf_tiktok_listing_status = fields.Selection(
        [
            ("not_listed", "Not Listed"),
            ("draft", "Draft on TikTok"),
            ("active", "Active on TikTok"),
            ("inactive", "Inactive on TikTok"),
        ],
        default="not_listed",
    )
    x_ynf_tiktok_last_push_at = fields.Datetime(copy=False)

    def _get_active_tiktok_account(self):
        self.ensure_one()
        account = self.x_ynf_tiktok_account_id
        if account:
            return account
        param = self.env["ir.config_parameter"].sudo().get_param("ynf.tiktok.active_account_id")
        if param:
            account = self.env["ynf.tiktok.shop.account"].browse(int(param)).exists()
            if account:
                return account
        account = self.env["ynf.tiktok.shop.account"].search([
            ("company_id", "=", self.env.company.id),
            ("active", "=", True),
            ("is_connected", "=", True),
        ], limit=1)
        if not account:
            raise UserError(_("No connected TikTok Shop account. Configure one under TikTok Shop → Accounts."))
        return account

    def action_tiktok_push_inventory(self):
        Map = self.env["ynf.tiktok.product.map"]
        for tmpl in self:
            account = tmpl._get_active_tiktok_account()
            product = tmpl.product_variant_id
            mapping = Map.search([
                ("account_id", "=", account.id),
                ("product_id", "=", product.id),
            ], limit=1)
            if not mapping or not mapping.tiktok_product_id:
                raise UserError(_("Product %s is not mapped to TikTok. Push listing first.") % tmpl.display_name)
            qty = int(product.free_qty)
            account.update_product_inventory(
                account,
                mapping.tiktok_product_id,
                [{"id": mapping.tiktok_sku_id, "inventory": [{"quantity": max(0, qty)}]}],
            )
            mapping.write({"last_inventory_sync_at": fields.Datetime.now(), "last_odoo_qty": qty})
        return True

    def action_tiktok_open_maps(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("TikTok Product Maps"),
            "res_model": "ynf.tiktok.product.map",
            "view_mode": "list,form",
            "domain": [("product_tmpl_id", "=", self.id)],
        }
