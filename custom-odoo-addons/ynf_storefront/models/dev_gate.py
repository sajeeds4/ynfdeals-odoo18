# -*- coding: utf-8 -*-
"""Storefront dev-mode gate.

When the system parameter `ynf.dev_mode` is set to "True" (default), all
non-internal visitors to ynfdeals.com (and other public storefront hostnames)
are redirected to /under-construction. Logged-in internal users (devs)
continue to see the live site normally so they can keep working on it.

Allowlist always passes through: /web/* (login, assets, signup, reset),
/odoo backend, /web/static, /web/image, /web/binary, /web/assets,
/websocket, /longpolling, /auth_oauth, /xmlrpc.

Toggle live without restart:
    ir.config_parameter set 'ynf.dev_mode' = 'False'  → site goes public
"""
import logging
import werkzeug.utils

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

ALLOW_PREFIXES = (
    "/web/static", "/web/assets", "/web/image", "/web/binary",
    "/web/login", "/web/signup", "/web/reset_password",
    "/web/logout", "/web/session",
    "/web/database",
    "/odoo", "/_odoo",
    "/under-construction",
    "/longpolling", "/websocket", "/bus",
    "/auth_oauth", "/auth_signup",
    "/xmlrpc", "/jsonrpc",
    "/favicon.ico", "/robots.txt", "/sitemap.xml",
    # Internal operator/admin endpoints — never gate, they're not public
    # entry points and some (video_file, websocket) are hit by media
    # elements that don't always send session cookies cleanly.
    "/ynf_operator", "/my",
)


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _ynf_dev_gate_active(cls):
        """Return True iff the current request should be blocked and redirected."""
        try:
            req = request
            if not req:
                return False
            path = (req.httprequest.path or "/").rstrip("/") or "/"

            if any(path == p or path.startswith(p + "/") or path.startswith(p) for p in ALLOW_PREFIXES):
                return False

            user = req.env.user
            if user and not user._is_public() and user.share is False:
                return False

            Param = req.env["ir.config_parameter"].sudo()
            return Param.get_param("ynf.dev_mode", "True").strip().lower() in ("true", "1", "yes", "on")
        except Exception:
            _logger.exception("YNF dev-gate check failed; allowing request")
            return False

    @classmethod
    def _dispatch(cls, endpoint):
        if cls._ynf_dev_gate_active():
            return werkzeug.utils.redirect("/under-construction", code=302)
        return super()._dispatch(endpoint)
