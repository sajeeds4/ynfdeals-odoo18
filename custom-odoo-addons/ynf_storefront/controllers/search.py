# -*- coding: utf-8 -*-
"""Live-search overlay v2 endpoints.

Returns product suggestions and popular brand chips for the
storefront's #ynf-search-overlay enhancement (JSON-RPC).
"""
from odoo import http
from odoo.http import request


class YnfSearchSuggestions(http.Controller):
    """JSON endpoints powering the live-search overlay (suggestions + brands).

    Both routes are auth=public so the overlay works for unauthenticated
    visitors. CSRF is disabled because they are read-only JSON-RPC calls
    that never mutate state, and sitemap=False keeps them out of the
    sitemap.xml.
    """

    @http.route(
        "/ynf/search/suggestions",
        type="json",
        auth="public",
        csrf=False,
        sitemap=False,
    )
    def suggestions(self, q=None, limit=6, **kw):
        q = (q or "").strip()
        if len(q) < 2:
            return {"ok": True, "results": []}
        Product = request.env["product.template"].sudo()
        # Search across name, brand (x_ynf_brand), inspired_by, family
        domain = [
            "|", "|", "|",
            ("name", "ilike", q),
            ("x_ynf_brand", "ilike", q),
            ("x_ynf_inspired_by", "ilike", q),
            ("x_ynf_family", "ilike", q),
        ]
        # Only show sellable, published products
        domain = [
            ("website_published", "=", True),
            ("sale_ok", "=", True),
        ] + domain
        try:
            cap = int(limit or 6)
        except (TypeError, ValueError):
            cap = 6
        cap = max(1, min(cap, 24))
        prods = Product.search(domain, limit=cap)
        results = [{
            "id": p.id,
            "name": p.name,
            "brand": p.x_ynf_brand or "",
            "family": p.x_ynf_family or "",
            "inspired_by": p.x_ynf_inspired_by or "",
            "price": float(p.list_price or 0.0),
            "image_url": "/web/image/product.template/%d/image_256" % p.id,
            "url": "/shop/product/%d" % p.id,
        } for p in prods]
        return {"ok": True, "results": results}

    @http.route(
        "/ynf/search/popular_brands",
        type="json",
        auth="public",
        csrf=False,
        sitemap=False,
    )
    def popular_brands(self, limit=8, **kw):
        """Top brands by published-product count.

        Uses a raw aggregate against product_template to stay cheap; the
        x_ynf_brand column is plain Char on product.template.
        """
        try:
            cap = int(limit or 8)
        except (TypeError, ValueError):
            cap = 8
        cap = max(1, min(cap, 24))
        request.env.cr.execute(
            """
            SELECT x_ynf_brand, COUNT(*) AS c
              FROM product_template
             WHERE x_ynf_brand IS NOT NULL
               AND x_ynf_brand <> ''
               AND website_published = TRUE
             GROUP BY x_ynf_brand
             ORDER BY c DESC
             LIMIT %s
            """,
            [cap],
        )
        rows = [
            {"brand": r[0], "count": r[1]}
            for r in request.env.cr.fetchall()
        ]
        return {"ok": True, "brands": rows}
