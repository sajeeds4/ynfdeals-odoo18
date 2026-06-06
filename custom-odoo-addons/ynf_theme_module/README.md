# YNF Deals — Odoo 18 Theme Module (`ynf_theme_module`)

A complete, installable Odoo 18 website theme that reproduces the **YNF Deals** storefront design (the `YNF Deals.html` prototype) as native QWeb + SCSS + vanilla JS — no core template edits, upgrade-safe.

## Install
1. Copy the **`ynf_theme_module/`** folder into your Odoo `addons` (or `custom-odoo-addons`) path.
2. Apps → Update Apps List → install **"YNF Deals — Luxury Fragrance Theme"** (or `-i ynf_theme_module`).
3. Website → Configuration → set the homepage to **`/ynf-home`** (or copy the hero into your existing home).

## Structure
```
ynf_theme_module/
├── __manifest__.py            depends: website, website_sale, website_sale_stock, portal
├── __init__.py / models/      product.template x_ynf_* fields (idempotent)
├── views/templates.xml        layout (marquee + butterfly), homepage, shop, product, /live
└── static/src/
    ├── scss/ynf_theme.scss    full reskin + all curated sections + butterfly
    └── js/ynf_theme.js        scroll-reveal, count-up, drop-alert, butterfly
```

## What's included (compliant, inheritance-only)
- **Layout** (`inherit_id="website.layout"`): scrolling announcement marquee + the flying butterfly on every page.
- **Curated homepage** (`/ynf-home`): hero, live strip, collections, bestsellers, **shop-by-mood**, **under $30**, new arrivals, **curated bundles** (real products, 15% off), **house spotlight**, **editorial image band** (images editable in the Website editor), **fragrance-finder CTA**, **testimonials**, **animated stats**, **authenticity band**, **drop-alert** form.
- **Catalog** (`inherit_id="website_sale.products_item"`): "Inspired by" dupe chip on every card.
- **Product** (`inherit_id="website_sale.product"`): wrapper class + Top/Heart/Base **notes pyramid**.
- **/live**: `website.page` + linked `website.menu`.
- **SCSS**: Cormorant + Inter, gold full-pill buttons, white canvas, product-grid card reskin, reads `var(--ynf-font-serif/sans, …)` tokens with fallbacks, scoped to `.ynf-*` / `website_sale` selectors → Odoo's asset hash cache-busts on every upgrade.

## Data dependency
The dupe chips, mood/family filtering, and notes pyramid read these `product.template` fields (declared in `models/`, matching your existing `x_ynf_*` convention):
`x_ynf_inspired_by`, `x_ynf_family`, `x_ynf_note_top`, `x_ynf_note_mid`, `x_ynf_note_base`.
Backfill them from `inventory_enrichment_master.json` (your `scripts/backfill_enrichment.py`). The `t-if` guards keep empty fields from rendering.

## Notes / adjust per instance
- **Collection / mood links** use `?family=` / `?attribute_value=` query params — wire them to your real product attributes or a search controller (your DB already has `x_ynf_family`).
- **Editorial images** point at `website.s_banner_default_image` as a placeholder — replace them in the Website editor (drag any image), or set real attachments.
- **Live countdown / TikTok embed** are static here; add a JS countdown or oembed snippet if wanted.
- Fonts load from Google Fonts in the SCSS `@import`; for production/GDPR, self-host into `static/fonts/` + `@font-face`.
- This module supersedes the partial `odoo_export/` files — use this one.
