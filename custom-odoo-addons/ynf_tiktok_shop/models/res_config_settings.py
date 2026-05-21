# -*- coding: utf-8 -*-
from odoo import fields, models

from .tiktok_shop_api import (
    DEFAULT_API_BASE,
    DEFAULT_AUTH_BASE,
    DEFAULT_AUTHORIZE_BASE,
    DEFAULT_REFRESH_URL,
    DEFAULT_TARGET_IDC,
    DEFAULT_TOKEN_URL,
)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    tiktok_shop_default_app_key = fields.Char(
        string="Default TikTok App Key",
        config_parameter="ynf.tiktok.default_app_key",
    )
    tiktok_shop_default_service_id = fields.Char(
        string="Default TikTok Service ID",
        config_parameter="ynf.tiktok.default_service_id",
    )
    tiktok_shop_default_redirect_uri = fields.Char(
        string="Default OAuth Redirect URI",
        config_parameter="ynf.tiktok.default_redirect_uri",
        help="Public URL for /tiktok_shop/oauth/callback",
    )
    tiktok_shop_api_base_url = fields.Char(
        default=DEFAULT_API_BASE,
        config_parameter="ynf.tiktok.api_base_url",
    )
    tiktok_shop_auth_base_url = fields.Char(
        default=DEFAULT_AUTH_BASE,
        config_parameter="ynf.tiktok.auth_base_url",
    )
    tiktok_shop_authorize_base_url = fields.Char(
        default=DEFAULT_AUTHORIZE_BASE,
        config_parameter="ynf.tiktok.authorize_base_url",
    )
    tiktok_shop_token_url = fields.Char(
        default=DEFAULT_TOKEN_URL,
        config_parameter="ynf.tiktok.token_url",
    )
    tiktok_shop_refresh_url = fields.Char(
        default=DEFAULT_REFRESH_URL,
        config_parameter="ynf.tiktok.refresh_url",
    )
    tiktok_shop_target_idc = fields.Char(
        default=DEFAULT_TARGET_IDC,
        config_parameter="ynf.tiktok.target_idc",
    )
    tiktok_shop_webhook_base_url = fields.Char(
        string="Webhook Base URL",
        config_parameter="ynf.tiktok.webhook_base_url",
        help="Public Odoo base URL used in Partner Center webhook registration.",
    )
    tiktok_shop_active_account_id = fields.Many2one(
        "ynf.tiktok.shop.account",
        string="Default TikTok Shop Account",
        domain="[('company_id', '=', company_id)]",
    )

    def set_values(self):
        super().set_values()
        if self.tiktok_shop_active_account_id:
            self.env["ir.config_parameter"].sudo().set_param(
                "ynf.tiktok.active_account_id",
                str(self.tiktok_shop_active_account_id.id),
            )

    def get_values(self):
        res = super().get_values()
        param = self.env["ir.config_parameter"].sudo().get_param("ynf.tiktok.active_account_id")
        account = False
        if param:
            account = self.env["ynf.tiktok.shop.account"].browse(int(param)).exists()
        res["tiktok_shop_active_account_id"] = account.id if account else False
        return res

    def action_open_tiktok_accounts(self):
        return {
            "type": "ir.actions.act_window",
            "name": "TikTok Shop Accounts",
            "res_model": "ynf.tiktok.shop.account",
            "view_mode": "list,form",
        }
