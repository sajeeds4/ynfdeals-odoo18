# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class YnfTiktokConnectWizard(models.TransientModel):
    _name = "ynf.tiktok.connect.wizard"
    _description = "Connect TikTok Shop"

    account_id = fields.Many2one("ynf.tiktok.shop.account", required=True)
    auth_code = fields.Char(string="Authorization Code")
    use_browser = fields.Boolean(
        string="Open TikTok authorization in browser",
        default=True,
    )
    instructions = fields.Html(readonly=True, compute="_compute_instructions")

    def _compute_instructions(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        callback = f"{base.rstrip('/')}/tiktok_shop/oauth/callback"
        for wiz in self:
            wiz.instructions = _(
                "<p>1. Register redirect URI in TikTok Partner Center:<br/><code>%s</code></p>"
                "<p>2. Click <b>Authorize in Browser</b> and approve access.</p>"
                "<p>3. After redirect, connection completes automatically. "
                "Or paste the <b>auth code</b> manually below.</p>"
            ) % callback

    def action_apply_defaults_from_settings(self):
        self.ensure_one()
        ICP = self.env["ir.config_parameter"].sudo()
        account = self.account_id
        account.write({
            "app_key": account.app_key or ICP.get_param("ynf.tiktok.default_app_key"),
            "service_id": account.service_id or ICP.get_param("ynf.tiktok.default_service_id"),
            "redirect_uri": account.redirect_uri or ICP.get_param("ynf.tiktok.default_redirect_uri"),
            "api_base_url": account.api_base_url or ICP.get_param("ynf.tiktok.api_base_url"),
            "auth_base_url": account.auth_base_url or ICP.get_param("ynf.tiktok.auth_base_url"),
            "authorize_base_url": account.authorize_base_url or ICP.get_param("ynf.tiktok.authorize_base_url"),
            "token_url": account.token_url or ICP.get_param("ynf.tiktok.token_url"),
            "refresh_url": account.refresh_url or ICP.get_param("ynf.tiktok.refresh_url"),
            "target_idc": account.target_idc or ICP.get_param("ynf.tiktok.target_idc"),
        })
        if not account.redirect_uri:
            base = ICP.get_param("web.base.url", "")
            account.redirect_uri = f"{base.rstrip('/')}/tiktok_shop/oauth/callback"
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_authorize_browser(self):
        self.ensure_one()
        self.action_apply_defaults_from_settings()
        if not self.account_id.app_secret:
            raise UserError(_("Set App Secret on the account before authorizing."))
        return self.account_id.action_build_auth_url()

    def action_connect_manual(self):
        self.ensure_one()
        if not self.auth_code:
            raise UserError(_("Paste the authorization code from TikTok."))
        self.account_id.action_connect_with_code(self.auth_code.strip())
        return {"type": "ir.actions.act_window_close"}
