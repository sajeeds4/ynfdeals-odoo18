# -*- coding: utf-8 -*-
{
    "name": "YNF Web",
    "version": "18.0.1.0.0",
    "summary": "YNF Deals storefront — full customer-facing website (homepage, shop, product, cart, checkout, portal, dev-gate).",
    "description": """
YNF Web
=======
Fresh storefront module for ynfdeals.com. Built to match a user-supplied
reference site 1:1. Replaces the older ynf_storefront. Includes:

- Homepage layout + hero
- Catalog page reskin
- Product detail page
- Cart + checkout flow
- Customer portal (/my)
- Login / signup overrides
- Dev-gate (under-construction redirect for anonymous visitors when
  ynf.dev_mode is set in ir.config_parameter)
- Re-declares x_ynf_inspired_by, x_ynf_family, x_ynf_image_url on
  product.template (restored from CSV snapshot after the prior uninstall).
""",
    "category": "Website",
    "author": "YNF Deals",
    "website": "https://ynfdeals.com",
    "depends": [
        "website",
        "website_sale",
        "website_sale_stock",
        "portal",
        "sale",
        "mail",
    ],
    "data": [
        # Loaded in dependency order; each file is wired in as we build it.
        # "data/theme_data.xml",
        # "views/layout.xml",
        # "views/homepage.xml",
        # "views/shop.xml",
        # "views/product.xml",
        # "views/cart.xml",
        # "views/checkout.xml",
        # "views/portal.xml",
        # "views/login.xml",
        # "views/dev_gate.xml",
        # "views/footer.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            # "ynf_web/static/src/scss/style.scss",
            # "ynf_web/static/src/js/app.js",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "post_init_hook": "post_init_restore_xynf",
}
