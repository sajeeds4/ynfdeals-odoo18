# -*- coding: utf-8 -*-
{
    "name": "YNF Perfume Website",
    "summary": "Luxury fragrance storefront theme for Odoo 18 Website & eCommerce",
    "description": """
YNF Perfume Website
===================
A luxury, editorial fragrance storefront built natively on Odoo 18 Community
(Website + Website Sale). Faithful to the YNF Deals design system:
Cormorant Garamond + Inter typography, gold & wine accents, warm-black palette.

Adds a cinematic homepage, luxury product cards, a fragrance-notes pyramid on
the product page, perfume metadata fields (notes, longevity, projection,
season, occasion, brand house, badges), and conversion/trust components.

Built ONLY with QWeb, SCSS and native Odoo JS. Cart, checkout, pricing and
inventory remain pure Odoo Website Sale.
""",
    "version": "18.0.1.0.0",
    "author": "YNF",
    "website": "https://ynfdeals.com",
    "category": "Website/Theme",
    "license": "LGPL-3",
    "depends": [
        "website",
        "website_sale",
    ],
    "data": [
        # NOTE: data/menu.xml + security/ were gitignored (data/ rule) in the dev
        # repo so they never shipped. Not needed here — nav is hardcoded in
        # website_layout_templates.xml and the module adds no new models.
        # backend views (perfume fields on product.template)
        "views/product_template_views.xml",
        # frontend templates
        "views/home_template.xml",
        "views/product_card_templates.xml",
        "views/shop_templates.xml",
        "views/product_page_templates.xml",
        "views/finder_templates.xml",
        "views/live_templates.xml",
        "views/website_layout_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            # ── Design system (order matters) ──
            "ynf_perfume_website/static/src/scss/base/_variables.scss",
            "ynf_perfume_website/static/src/scss/base/_fonts.scss",
            "ynf_perfume_website/static/src/scss/base/_base.scss",
            "ynf_perfume_website/static/src/scss/base/_animations.scss",
            "ynf_perfume_website/static/src/scss/components/_atoms.scss",
            "ynf_perfume_website/static/src/scss/components/_product_card.scss",
            "ynf_perfume_website/static/src/scss/components/_chrome.scss",
            "ynf_perfume_website/static/src/scss/pages/_home.scss",
            "ynf_perfume_website/static/src/scss/pages/_shop.scss",
            "ynf_perfume_website/static/src/scss/pages/_product.scss",
            "ynf_perfume_website/static/src/scss/pages/_finder.scss",
            "ynf_perfume_website/static/src/scss/pages/_live.scss",
            # ── JS (native Odoo / vanilla, no React) ──
            "ynf_perfume_website/static/src/js/reveal.js",
            "ynf_perfume_website/static/src/js/hero_video.js",
            "ynf_perfume_website/static/src/js/storefront.js",
            "ynf_perfume_website/static/src/js/recent.js",
        ],
    },
    "images": ["static/description/banner.png"],
    "installable": True,
    "application": True,
}
