# YNF Perfume Website

A luxury, editorial fragrance storefront built natively on **Odoo 18 Community**
(Website + Website Sale). Faithful to the YNF Deals design system —
Cormorant Garamond + Inter typography, gold & wine accents, warm-black palette —
extended from the mobile design into a fully responsive desktop/tablet experience.

Built with **QWeb, SCSS and native Odoo JS only**. No React/Vite/Next. Cart,
checkout, pricing, inventory and variants stay 100% Odoo Website Sale.

---

## What it adds

| Area | What you get |
|---|---|
| **Homepage** (`/fragrances`, also `/`) | Cinematic hero with the seamless fade-loop video, scrolling announcement bar, trust row, live-auction strip + countdown, gender collections, brand rail, bestsellers grid, "Inspired by the icons" dupes rail, new arrivals, house spotlight, testimonials, animated stats, newsletter — all from **live catalogue data**. |
| **Shop** (`/shop`) | Native website_sale grid re-skinned into luxury cards (hover-zoom + lift), luxury header, **gender quick-filter chips** (`?gender=men/women/unisex`) and `?brand=` filtering that hook into the real search domain (pager/sort preserved). |
| **Product page** (PDP) | Brand eyebrow, meta line, inspired-by chip, editorial blurb, **fragrance-notes pyramid** (Top / Heart / Base), longevity & projection meters, season/occasion, trust/perks panel. Native add-to-cart untouched. |
| **Backend** | A **“Fragrance” tab** on the product form: brand house, gender, concentration, volume, family, country, inspired-by, notes pyramid, longevity, projection, season, occasion, and merchandising badges (Bestseller / Trending / New) + luxury score + editorial blurb. |
| **Site-wide** | Luxury fonts + gold accent applied to header/footer/cart/checkout via a `.ynf-site` body class, plus a global scrolling announcement bar. |

All product sections **degrade gracefully**: if a section has no matching data
(e.g. no products tagged with a brand) it is simply hidden — never empty.

---

## Installation

The module lives at:

```
ynfdeals-addons/addons/ynf_perfume_website
```

which is already on the `addons_path` in `odoo.conf`.

```bash
# from the odoo root (/home/zulfiqar/s/odoo)
/home/zulfiqar/s/.venv/bin/python odoo-bin \
  -c odoo.conf -d YNFDEALS \
  -i ynf_perfume_website \
  --stop-after-init --http-port=8899
```

Or from the UI: **Apps → Update Apps List → search “YNF Perfume Website” → Install.**

> The running production server picks up the new module on its next worker
> reload after the `--stop-after-init` install commits.

### One-time DB note (already applied on YNFDEALS)
This DB had a pre-existing **orphaned Studio field** `x_ynf_packing_keyword`
(referenced by `ynf_operator`’s product form but whose definition had been
deleted). Any product-form change re-validates that view and failed. It was
healed by flipping the dangling `ir.model.fields` row to `state='manual'`, which
re-materialises the column. If you migrate to another DB with the same issue,
apply the same fix before installing (see *Troubleshooting*).

---

## Upgrade

After pulling new code:

```bash
/home/zulfiqar/s/.venv/bin/python odoo-bin \
  -c odoo.conf -d YNFDEALS \
  -u ynf_perfume_website \
  --stop-after-init --http-port=8899
```

---

## Rebuilding assets (SCSS/JS changes)

Odoo recompiles `web.assets_frontend` automatically on `-u`. To force a fresh
bundle without a full upgrade:

- **UI:** Settings → Technical → enable *Developer Tools*, then
  *Regenerate Assets Bundles*; or append `?debug=assets` to any URL to bypass
  the cached bundle while iterating.
- **CLI:** `-u ynf_perfume_website` rebuilds and re-minifies the bundle.

SCSS load order is pinned in `__manifest__.py` (variables → fonts → base →
animations → components → pages). Keep `_variables.scss` first.

---

## Making the luxury homepage your root `/`

By default this DB’s `website.homepage_url` is `/home` (set by
`ynf_website_custom`), so `/` serves a website-builder page and the luxury
homepage lives at **`/fragrances`**. To make `/` the luxury homepage:

```
Website → Settings → (clear Homepage URL)   # lets the controller route own /
```
or set `homepage_url` empty / to `/fragrances`. The controller already answers
both `/` and `/fragrances`.

---

## Tagging products (so every section lights up)

Open a product → **Fragrance** tab → fill in:

- **Fragrance House** (e.g. `Lattafa`) → powers the brand rail & brand filter.
- **Gender** → powers collections + `?gender=` chips.
- **Notes** (comma-separated) → renders the PDP notes pyramid.
- **Inspired By** → shows the “Inspired by …” chip + the dupes rail.
- **Bestseller / Trending / New** → badges + homepage sections.
- **Luxury Score** → highest score becomes the hero bottle.

A helper to bulk-seed sample data is described in the install chat / can be
re-run from `odoo-bin shell`.

---

## Testing checklist

- [ ] `/fragrances` renders hero video (fades, loops seamlessly, no jump).
- [ ] Announcement bar scrolls; reduced-motion users see it static.
- [ ] Bestsellers/new-arrivals grids show real products with real prices.
- [ ] Quick-add (gold `+` on a card) adds to the **native** cart; count bumps.
- [ ] `/shop` cards have hover-zoom + lift; chips filter by gender.
- [ ] `/shop?gender=women` and `?brand=Lattafa` filter correctly; pager keeps the filter.
- [ ] PDP shows brand eyebrow, blurb, notes pyramid (when notes set), perks panel.
- [ ] **Add to cart → checkout → payment** completes unchanged (pure Odoo).
- [ ] Backend product **Fragrance** tab saves all fields.
- [ ] Mobile (≤576px): no horizontal overflow; rails scroll; CTAs reachable.
- [ ] Lighthouse: lazy images, single CSS/JS bundle, fonts `display:swap`.

---

## Troubleshooting

**Install fails on `x_ynf_packing_keyword does not exist`** (or another orphan
Studio field): a registered manual field lost its definition. Repair with:

```python
# odoo-bin shell -c odoo.conf -d <db>
env.cr.execute("UPDATE ir_model_fields SET state='manual', store=true "
               "WHERE name='x_ynf_packing_keyword'")
env.cr.commit()
```
then re-run the install. (Generalises to any orphaned `state='base'` Studio field.)

**Two fields … have the same label** warnings (Gender/Volume/Notes): harmless —
our `ynf_*` fields share a *human label* with legacy `x_ynf_*`/`volume` fields.
They are distinct technical fields. Rename labels in `models/product_template.py`
if you want the warnings gone.

**Hero video doesn’t autoplay:** browsers block autoplay with sound. The video
is `muted playsinline`; if a corporate policy still blocks it, the product
poster image shows instead (by design).

---

## File map

```
ynf_perfume_website/
├── __manifest__.py
├── controllers/main.py          # / and /fragrances homepage + /shop filters
├── models/product_template.py   # perfume fields + notes helpers
├── security/ir.model.access.csv
├── data/menu.xml                # Shop / For Him / For Her / Unisex menus
├── views/
│   ├── product_template_views.xml   # backend “Fragrance” tab
│   ├── product_card_templates.xml   # icon set + luxury product card + section head
│   ├── home_template.xml            # the luxury homepage
│   ├── shop_templates.xml           # /shop re-skin + chips
│   ├── product_page_templates.xml   # luxury PDP (notes pyramid, perks)
│   └── website_layout_templates.xml # global announce bar + body class
└── static/src/
    ├── scss/{base,components,pages}/…
    └── js/{reveal,hero_video,storefront}.js
```

---

## Competitor-research backlog (setup-required — not auto-built)

A 10-site competitor study (Creed, MFK, Le Labo, Byredo, Diptyque, Parfums de
Marly, Tom Ford, Initio, Jo Malone, Aesop → 119 findings) produced these
high-value mechanics. They need **product/coupon setup in Odoo**, so they are
documented here rather than created on your live data:

1. **Free samples with every order** — create $0 sample products (tag with a new
   `ynf_is_sample` boolean), surface a "pick 2 complimentary samples" grid on the
   cart (inherit `website_sale.cart`), reuse `storefront.js` `quickAdd()` with a
   2-line cap. *Biggest blind-buy de-risker.*
2. **Try-then-credit Discovery Set** — sell a paid sampler SKU; use **native
   Odoo loyalty/coupon** to auto-issue a fixed-amount code redeemable on a full
   bottle. No custom cart code. Add `ynf_is_discovery_set` + a `/discovery` route.
3. **Gift-with-purchase progress bar** — "spend $X, get Y free" via native
   loyalty promotion; render a progress bar on cart.
4. **Bottle engraving / personalization** — custom value on the order line
   (Odoo product custom attribute) + live char-count preview on PDP.
5. **Size / concentration variant pills** — configure native product **variants**
   (Size attribute, "Pills" display) — website_sale renders price/stock per size
   with zero custom JS; SCSS to restyle the pills is already scaffolded.
6. **Restock "email me when available"** — native back-in-stock notification on
   out-of-stock PDPs.

These reuse existing patterns (the `product_card` partial, `quickAdd()`, the
`ynf_*` field + domain-helper convention) — wiring is straightforward once the
products/promotions exist.

## Future enhancement roadmap (AI-ready extension points)

The perfume metadata is **structured on `product.template`** precisely so a
recommender can read it directly. Suggested next passes:

1. **Search experience (Phase 8):** autocomplete over name/brand/notes/inspired-by,
   popular & trending chips (data already in the model).
2. **Perfume finder quiz (Phase 9):** 4-question wizard (gender, season, budget,
   scent family) → query `product.template` by `ynf_*` fields → recommendations.
3. **Recommendation engine (Phase 10):** “smells like” similarity over the notes
   pyramid + family; personalised homepage rail keyed on browsing/cart history.
4. **SEO (Phase 11):** Product/Breadcrumb schema.org JSON-LD, OpenGraph/Twitter,
   canonical URLs (Odoo provides hooks on the PDP).
5. **Conversion (Phase 14):** real-time low-stock from `qty_available`,
   “recently sold” pulses, bundle cross-sells via Optional Products.
6. **Live auctions:** wire the live strip/countdown to the existing
   `ynf_tiktok_live` module for real show times and lots.
```
