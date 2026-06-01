# -*- coding: utf-8 -*-
{
    "name": "YNF Deals — Storefront",
    "version": "18.0.6.0.0",
    "summary": "Mobile-first light-luxury storefront for ynfdeals.com (curated homepage, live auctions, dupe badges, portal customizations).",
    "description": """
YNF Deals storefront
====================
A premium, classic, mobile-first storefront for the YNF Deals Arabian-fragrance
shop. Installs as a regular module (applies globally, no theme switcher) and
ships the x_ynf_* merchandising fields it needs.

* Curated homepage: hero, collections, brand rail, bestsellers, shop-by-mood,
  under-$30 deals, curated bundles, house spotlight, editorial image band,
  fragrance-finder CTA, testimonials, animated stats, authenticity band, drop-alert.
* website_sale catalog + product reskin via QWeb inheritance (no core edits).
* "Inspired by" dupe chips and a Top/Heart/Base notes pyramid driven by
  x_ynf_* product fields.
* /live auctions page (website.page + menu), announcement marquee, cookie bar.
* Scroll-reveal, count-up, and butterfly animations (vanilla JS).
* Portal: /my/orders broadened to include TikTok orders attached to a shipping
  recipient, grouped by Go Live Session; /my/help dispute flow.
* Mega-menu top nav rebuilt on install via post_init.
* Sale-order portal messages auto-route to Customer Service Discuss inbox.
""",
    "category": "Website",
    "author": "YNF Deals",
    "website": "https://ynfdeals.com",
    "depends": ["website", "website_sale", "website_sale_stock", "portal", "sale", "mail"],
    "data": [
        "data/theme_data.xml",
        "views/templates.xml",
        "views/footer_templates.xml",
        "views/portal_templates.xml",
        "views/login_templates.xml",
        "views/dev_gate_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "ynf_storefront/static/src/scss/ynf_theme.scss",
            "ynf_storefront/static/src/scss/mobile_first_design.scss",
            "ynf_storefront/static/src/scss/components/_footer.scss",
            "ynf_storefront/static/src/scss/components/_search.scss",
            "ynf_storefront/static/src/js/ynf_theme.js",
            "ynf_storefront/static/src/js/ynf_search.js",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "post_init_hook": "post_init_hook",
}
