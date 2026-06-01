# -*- coding: utf-8 -*-
{
    "name": "YNF Deals — Storefront",
    "version": "18.0.16.0.0",
    "summary": "Mobile-first light-luxury storefront for ynfdeals.com (curated homepage, live auctions, dupe badges, portal customizations).",
    "description": """
YNF Deals storefront
====================
Mobile-first storefront for ynfdeals.com.
""",
    "category": "Website",
    "author": "YNF Deals",
    "website": "https://ynfdeals.com",
    "depends": ["website", "website_sale", "website_sale_stock", "portal", "sale", "mail"],
    "data": [
        "data/theme_data.xml",
        "views/templates.xml",
        "views/portal_templates.xml",
        "views/login_templates.xml",
        "views/dev_gate_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "ynf_storefront/static/src/scss/ynf_theme.scss",
            "ynf_storefront/static/src/js/ynf_theme.js",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "post_init_hook": "post_init_hook",
}
