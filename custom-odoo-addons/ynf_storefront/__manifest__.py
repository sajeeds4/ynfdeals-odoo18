# -*- coding: utf-8 -*-
{
    "name": "YNF Deals — Storefront",
    "version": "18.0.7.0.2",
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
        "views/footer_templates.xml",
        "views/components.xml",
        "views/cart_templates.xml",
        "views/checkout_templates.xml",
        "views/shop_templates.xml",
        "views/portal_templates.xml",
        "views/portal_account.xml",
        "views/login_templates.xml",
        "views/dev_gate_templates.xml",
        "views/product_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "ynf_storefront/static/src/scss/ynf_theme.scss",
            "ynf_storefront/static/src/scss/mobile_first_design.scss",
            "ynf_storefront/static/src/scss/components/_components.scss",
            "ynf_storefront/static/src/scss/components/_footer.scss",
            "ynf_storefront/static/src/scss/components/_search.scss",
            "ynf_storefront/static/src/scss/pages/_cart.scss",
            "ynf_storefront/static/src/scss/pages/_checkout.scss",
            "ynf_storefront/static/src/scss/pages/_portal.scss",
            "ynf_storefront/static/src/scss/pages/_product.scss",
            "ynf_storefront/static/src/scss/pages/_shop.scss",
            "ynf_storefront/static/src/js/ynf_theme.js",
            "ynf_storefront/static/src/js/ynf_product.js",
            "ynf_storefront/static/src/js/ynf_search.js",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "post_init_hook": "post_init_hook",
}
