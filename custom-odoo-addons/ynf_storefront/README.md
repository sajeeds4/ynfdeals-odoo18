# YNF Deals — Odoo 18 Module (`ynf_storefront`)

A complete, installable Odoo 18 **module** (not a theme) that reproduces the **YNF Deals** storefront design (the `YNF Deals.html` prototype) as native QWeb + SCSS + vanilla JS — no core template edits, upgrade-safe. Installs once via Apps and applies globally; no theme-switcher step.

## Why a module (not a theme)
This package ships **Python models** (`x_ynf_*` product fields), which a pure Odoo theme can't — themes are data-only. As a regular module it installs with `-i ynf_storefront`, registers its frontend assets in `web.assets_frontend`, and takes effect site-wide immediately.

## Install
1. Copy the **`ynf_storefront/`** folder into your Odoo `addons` (or `custom-odoo-addons`) path.
2. Apps → Update Apps List → install **"YNF Deals — Storefront"** (or `-i ynf_storefront`).
3. Website → Configuration → set the homepage to **`/ynf-home`** (or copy the hero into your existing home).

## Structure
```
ynf_storefront/
├── __manifest__.py            category: Website · depends: website, website_sale, website_sale_stock, portal
├── __init__.py / models/      product.template x_ynf_* fields (idempotent)
├── views/templates.xml        layout (marquee + butterfly), homepage, shop, product, /live
└── static/src/
    ├── scss/ynf_theme.scss    self-contained tokens + full reskin + all curated sections + butterfly
    └── js/ynf_theme.js        scroll-reveal, count-up, drop-alert, butterfly
```

## What's included (compliant, inheritance-only)
- **Layout** (`inherit_id="website.layout"`): scrolling announcement marquee + the flying butterfly on every page.
- **Curated homepage** (`/ynf-home`): hero, live strip, collections, bestsellers, **shop-by-mood**, **under $30**, new arrivals, **curated bundles** (real products, 15% off), **house spotlight**, **editorial image band** (images editable in the Website editor), **fragrance-finder CTA**, **testimonials**, **animated stats**, **authenticity band**, **drop-alert** form.
- **Catalog** (`inherit_id="website_sale.products_item"`): "Inspired by" dupe chip on every card.
- **Product** (`inherit_id="website_sale.product"`): wrapper class + Top/Heart/Base **notes pyramid**.
- **/live**: `website.page` + linked `website.menu`.
- **SCSS**: self-contained design tokens (no external `_variables` needed), Cormorant + Inter, gold full-pill buttons, white canvas, product-grid card reskin, scoped to `.ynf-*` / `website_sale` selectors → Odoo's asset hash cache-busts on every upgrade.

## Product images (included)
Real bottle photos are wired in via a **post-init hook** (`hooks.py`). On install it matches each product by name and, for any product **without** an image, downloads the real brand-CDN photo into Odoo's `image_1920` (Odoo's server fetches the URL) and stores the URL in `x_ynf_image_url` as a fallback. It's **re-runnable and non-destructive** — it never overwrites an existing image. 18 products are mapped; add rows to `YNF_PRODUCT_IMAGES` in `hooks.py` as the catalog grows. Cards render the DB image first, then the URL, then Odoo's placeholder.

## Data dependency
The dupe chips, mood/family filtering, and notes pyramid read these `product.template` fields (declared in `models/`, matching your existing `x_ynf_*` convention):
`x_ynf_inspired_by`, `x_ynf_family`, `x_ynf_note_top`, `x_ynf_note_mid`, `x_ynf_note_base`.
Backfill them from `inventory_enrichment_master.json` (your `scripts/backfill_enrichment.py`). The `t-if` guards keep empty fields from rendering.

## Notes / adjust per instance
- **Collection / mood links** use `?family=` / `?attribute_value=` query params — wire them to your real product attributes or a search controller (your DB already has `x_ynf_family`).
- **Editorial images** point at `website.s_banner_default_image` as a placeholder — replace them in the Website editor (drag any image), or set real attachments.
- **Live countdown / TikTok embed** are static here; add a JS countdown or oembed snippet if wanted.
- Fonts: the SCSS no longer uses a remote `@import`; load Cormorant + Inter via a `<link>` in `website.layout` (`//head`) or self-host into `static/fonts/` + `@font-face`.
- This module supersedes the older `ynf_theme_module/` and the partial `odoo_export/` files — use this one.
