# -*- coding: utf-8 -*-
{
    "name": "YNF Deals — Luxury Fragrance Theme",
    "version": "18.0.5.0.0",
    "summary": "Mobile-first light-luxury storefront theme for ynfdeals.com (curated homepage, live auctions, dupe badges).",
    "description": """
YNF Deals storefront theme
==========================
A premium, classic, mobile-first theme for the YNF Deals Arabian-fragrance shop.

* Curated homepage: hero, collections, brand rail, bestsellers, shop-by-mood,
  under-$30 deals, curated bundles, house spotlight, editorial image band,
  fragrance-finder CTA, testimonials, animated stats, authenticity band, drop-alert.
* website_sale catalog + product reskin via QWeb inheritance (no core edits).
* "Inspired by" dupe chips and a Top/Heart/Base notes pyramid driven by
  x_ynf_* product fields.
* /live auctions page (website.page + menu), announcement marquee, cookie bar.
* Scroll-reveal, count-up, and butterfly animations (vanilla JS).
""",
    "category": "Website/Theme",
    "author": "YNF Deals",
    "website": "https://ynfdeals.com",
    "depends": ["website", "website_sale", "website_sale_stock", "portal"],
    "data": [
        "views/templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "ynf_theme_module/static/src/scss/ynf_theme.scss",
            "ynf_theme_module/static/src/js/ynf_theme.js",
        ],
    },
    "images": ["static/description/cover.png"],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
