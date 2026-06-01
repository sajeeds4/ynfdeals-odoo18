# -*- coding: utf-8 -*-
"""
YNF MFD v2 — Newsletter signup endpoint.

Stores subscribed emails as a comma-separated list in
``ir.config_parameter`` under the key ``ynf.newsletter_emails``.

This keeps the endpoint dependency-free (no requirement on
``mass_mailing`` being installed). Operators can later export the
parameter value and import it into a real mailing list.
"""

import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Practical e-mail shape — intentionally permissive, server-side guard only.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Cap stored list so a runaway client can't bloat ir.config_parameter.
_MAX_STORED = 20000

PARAM_KEY = "ynf.newsletter_emails"


class YnfNewsletter(http.Controller):
    """JSON endpoint backing the v2 footer newsletter form."""

    @http.route(
        "/ynf/newsletter/signup",
        type="json",
        auth="public",
        csrf=False,
        sitemap=False,
    )
    def signup(self, email=None, **kw):
        email = (email or "").strip().lower()
        if not email or not _EMAIL_RE.match(email):
            return {"ok": False, "error": "Please enter a valid email."}

        Param = request.env["ir.config_parameter"].sudo()
        raw = Param.get_param(PARAM_KEY, "") or ""
        existing = {e.strip() for e in raw.split(",") if e.strip()}

        if email in existing:
            return {"ok": True, "message": "You're already on the list."}

        if len(existing) >= _MAX_STORED:
            _logger.warning(
                "ynf.newsletter: subscriber cap of %s reached; "
                "drop request for %r",
                _MAX_STORED,
                email,
            )
            return {
                "ok": False,
                "error": "Subscriptions are temporarily paused. Try again later.",
            }

        existing.add(email)
        Param.set_param(PARAM_KEY, ",".join(sorted(existing)))
        _logger.info("ynf.newsletter: subscribed %r (total=%d)",
                     email, len(existing))
        return {"ok": True, "message": "Thanks — you're on the list."}
