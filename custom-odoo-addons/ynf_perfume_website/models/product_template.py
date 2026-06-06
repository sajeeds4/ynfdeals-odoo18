# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models
from markupsafe import Markup


class ProductTemplate(models.Model):
    """Perfume metadata for the YNF luxury fragrance storefront.

    All fields are optional, so a plain product still works.  Notes are stored
    as comma-separated text and exposed as lists via computed helpers, which the
    QWeb notes-pyramid renders.  This keeps the data model light (no extra
    tables) while remaining an AI-ready extension point: a future recommender
    can read these structured attributes directly off product.template.
    """
    _inherit = "product.template"

    # ── Identity ──
    ynf_brand = fields.Char(
        string="Fragrance House",
        help="Brand house, e.g. Lattafa, Afnan, Rasasi, Maison Alhambra.")
    ynf_gender = fields.Selection(
        selection=[
            ("men", "For Him"),
            ("women", "For Her"),
            ("unisex", "Unisex"),
        ],
        string="Gender")
    ynf_concentration = fields.Selection(
        selection=[
            ("edc", "Eau de Cologne"),
            ("edt", "Eau de Toilette"),
            ("edp", "Eau de Parfum"),
            ("parfum", "Parfum / Extrait"),
        ],
        string="Concentration")
    ynf_volume = fields.Char(string="Volume", help="e.g. 100 ml")
    ynf_country = fields.Char(string="Country of Origin")
    ynf_family = fields.Char(
        string="Scent Family",
        help="e.g. Amber Gourmand, Aquatic Aromatic, Woody Spicy.")
    ynf_inspired_by = fields.Char(
        string="Inspired By",
        help="Community 'dupe' reference, e.g. Creed Aventus. Shown as a chip.")

    # ── Notes pyramid (comma-separated) ──
    ynf_notes_top = fields.Char(string="Top Notes")
    ynf_notes_heart = fields.Char(string="Heart / Middle Notes")
    ynf_notes_base = fields.Char(string="Base Notes")

    # ── Performance ──
    ynf_longevity = fields.Selection(
        selection=[
            ("1", "Light (2–4h)"),
            ("2", "Moderate (4–6h)"),
            ("3", "Long (6–8h)"),
            ("4", "Very Long (8h+)"),
        ],
        string="Longevity")
    ynf_projection = fields.Selection(
        selection=[
            ("1", "Intimate"),
            ("2", "Moderate"),
            ("3", "Strong"),
            ("4", "Enormous"),
        ],
        string="Projection")
    ynf_season = fields.Char(
        string="Season", help="e.g. Fall/Winter, Spring/Summer, All seasons.")
    ynf_occasion = fields.Char(
        string="Occasion", help="e.g. Evening, Office, Date night.")

    # ── Merchandising badges ──
    ynf_is_bestseller = fields.Boolean(string="Bestseller")
    ynf_is_trending = fields.Boolean(string="Trending")
    ynf_is_new = fields.Boolean(string="New Arrival")
    ynf_luxury_score = fields.Integer(
        string="Luxury Score", default=0,
        help="0–100. Used to rank/curate the most premium pieces.")
    ynf_blurb = fields.Text(
        string="Editorial Blurb",
        help="Short evocative description shown on the luxury product page.")

    # ── Computed list helpers for QWeb ──
    ynf_notes_top_list = fields.Char(
        compute="_compute_notes_lists", string="Top Notes (list)")
    ynf_notes_heart_list = fields.Char(
        compute="_compute_notes_lists", string="Heart Notes (list)")
    ynf_notes_base_list = fields.Char(
        compute="_compute_notes_lists", string="Base Notes (list)")

    @api.depends("ynf_notes_top", "ynf_notes_heart", "ynf_notes_base")
    def _compute_notes_lists(self):
        # Stored compute is unnecessary; QWeb reads notes_as_list() directly.
        for rec in self:
            rec.ynf_notes_top_list = rec.ynf_notes_top or ""
            rec.ynf_notes_heart_list = rec.ynf_notes_heart or ""
            rec.ynf_notes_base_list = rec.ynf_notes_base or ""

    def notes_as_list(self, which):
        """Return a clean list of notes for a pyramid tier ('top'/'heart'/'base')."""
        self.ensure_one()
        raw = {
            "top": self.ynf_notes_top,
            "heart": self.ynf_notes_heart,
            "base": self.ynf_notes_base,
        }.get(which) or ""
        return [n.strip() for n in raw.replace("·", ",").split(",") if n.strip()]

    def ynf_has_notes(self):
        self.ensure_one()
        return bool(self.ynf_notes_top or self.ynf_notes_heart or self.ynf_notes_base)

    # ── Display-time derivation (NO database writes) ──────────────────────
    # The catalogue's product NAMES already encode the house and gender, e.g.
    # "Lattafa Khamrah 100ml Unisex" or "Afnan 9 PM 100ml Men's".  We read that
    # existing data live so the brand rail and gender collections populate
    # across the whole catalogue without anyone having to tag products by hand.
    # An explicit ynf_brand / ynf_gender always wins when set.

    # Known multi-word fragrance houses (longest match first).
    _YNF_KNOWN_HOUSES = [
        "Maison Alhambra", "Jo Milano", "Al Haramain", "Khadlaj", "Ard Al Zaafaran",
        "Swiss Arabian", "French Avenue", "Paris Corner", "Pendora Scents",
        "Bharara", "Lattafa", "Afnan", "Rasasi", "Armaf", "Asdaaf", "Dumont",
        "Grandeur", "Arabiyat", "Risala", "Rave", "Nylaa", "Maison",
    ]

    ynf_display_brand = fields.Char(
        string="House (display)", compute="_compute_ynf_display",
        help="ynf_brand if set, else the fragrance house parsed from the name.")
    ynf_display_gender = fields.Selection(
        selection=[("men", "For Him"), ("women", "For Her"), ("unisex", "Unisex")],
        string="Gender (display)", compute="_compute_ynf_display")

    @api.depends("name", "ynf_brand", "ynf_gender")
    def _compute_ynf_display(self):
        for rec in self:
            rec.ynf_display_brand = rec.ynf_brand or rec._derive_brand_from_name()
            rec.ynf_display_gender = rec.ynf_gender or rec._derive_gender_from_name()

    def _derive_brand_from_name(self):
        self.ensure_one()
        name = (self.name or "").strip()
        if not name:
            return False
        low = name.lower()
        for house in self._YNF_KNOWN_HOUSES:
            if low.startswith(house.lower() + " ") or low == house.lower():
                return house
        # Fallback: first token (covers single-word houses we didn't list).
        first = name.split()[0]
        return first if first and first[0].isalpha() else False

    def _derive_gender_from_name(self):
        self.ensure_one()
        low = (self.name or "").lower()
        if "unisex" in low:
            return "unisex"
        if "women" in low or "femme" in low or "pour femme" in low or " her " in low:
            return "women"
        if "men" in low or "homme" in low or " him " in low:
            return "men"
        return False

    # ── Scent-family taxonomy (derived from family text + notes) ──────────
    # Controlled olfactive families used as the lead discovery facet (#4) and
    # for spec chips. Each maps to keywords found in ynf_family / notes / name.
    _YNF_FAMILIES = [
        ("oud", "Oud", ["oud", "agarwood", "dehn"]),
        ("amber", "Amber", ["amber", "ambr", "ambrox", "labdanum", "benzoin"]),
        ("gourmand", "Gourmand", ["gourmand", "vanilla", "caramel", "praline",
                                    "honey", "chocolate", "coffee", "toffee", "sugar", "dates"]),
        ("floral", "Floral", ["floral", "rose", "jasmine", "tuberose", "lily",
                               "peony", "blossom", "violet", "iris", "orchid", "flower"]),
        ("woody", "Woody", ["wood", "cedar", "sandalwood", "vetiver", "patchouli", "pine"]),
        ("spicy", "Spicy", ["spic", "cinnamon", "saffron", "pepper", "cardamom",
                            "clove", "nutmeg", "ginger"]),
        ("fresh", "Fresh", ["fresh", "aquatic", "marine", "citrus", "bergamot",
                            "lemon", "lime", "mint", "ice", "aqua", "green"]),
        ("musk", "Musk", ["musk", "white musk", "skin"]),
        ("leather", "Leather", ["leather", "suede", "tobacco", "smoke", "incense"]),
    ]

    ynf_display_family = fields.Char(
        string="Scent family (display)", compute="_compute_ynf_family",
        help="Controlled olfactive family parsed from family text and notes.")

    @api.depends("name", "ynf_family", "ynf_notes_top", "ynf_notes_heart", "ynf_notes_base")
    def _compute_ynf_family(self):
        for rec in self:
            rec.ynf_display_family = rec._derive_family()

    def _derive_family(self):
        self.ensure_one()
        blob = " ".join(filter(None, [
            self.ynf_family or "", self.ynf_notes_top or "", self.ynf_notes_heart or "",
            self.ynf_notes_base or "", self.name or "",
        ])).lower()
        if not blob:
            return False
        # Score each family by keyword hits; strongest wins (oud/amber/gourmand
        # are listed first so they win ties — they're the most distinctive).
        best, best_score = False, 0
        for fid, label, kws in self._YNF_FAMILIES:
            score = sum(1 for k in kws if k in blob)
            if score > best_score:
                best, best_score = label, score
        return best

    @api.model
    def ynf_distinct_families(self):
        """Olfactive families present in the published catalogue (ordered by the
        canonical taxonomy, only those with at least one product)."""
        prods = self.search([
            ("website_published", "=", True), ("sale_ok", "=", True),
        ], limit=600)
        present = set(p.ynf_display_family for p in prods if p.ynf_display_family)
        return [label for _fid, label, _kw in self._YNF_FAMILIES if label in present]

    # ── Note → accent colour (for the educational pyramid, #6) ────────────
    _YNF_NOTE_COLORS = [
        (["oud", "agarwood", "wood", "cedar", "sandalwood", "vetiver", "patchouli"], "#7c6128"),
        (["amber", "vanilla", "tonka", "benzoin", "labdanum"], "#c9a961"),
        (["rose", "jasmine", "tuberose", "floral", "lily", "peony", "violet", "iris", "blossom"], "#b06a7a"),
        (["citrus", "bergamot", "lemon", "lime", "orange", "mandarin", "grapefruit"], "#c7a830"),
        (["mint", "green", "aquatic", "marine", "fresh", "ice", "water"], "#5a8f78"),
        (["cinnamon", "saffron", "pepper", "cardamom", "clove", "nutmeg", "ginger", "spice"], "#a85a32"),
        (["leather", "tobacco", "smoke", "incense", "suede"], "#5a4636"),
        (["musk", "praline", "caramel", "honey", "coffee", "chocolate", "dates", "sugar"], "#a9824e"),
    ]

    @api.model
    def ynf_note_color(self, note):
        low = (note or "").lower()
        for keys, color in self._YNF_NOTE_COLORS:
            if any(k in low for k in keys):
                return color
        return "#a8997f"  # default warm dim

    # Plain-language descriptor per pyramid tier (educational copy, #6).
    _YNF_TIER_COPY = {
        "top": "The opening — fresh first impression, fades within the hour.",
        "heart": "The heart — the character that blooms once it settles.",
        "base": "The base — the lasting trail that lingers on skin.",
    }

    @api.model
    def ynf_tier_copy(self, tier):
        return self._YNF_TIER_COPY.get(tier, "")

    # ── Image presence + low-stock (Odoo-18-correct) ─────────────────────
    def ynf_has_image(self):
        """True only when the product has a REAL uploaded photo (not Odoo's
        gray placeholder). Lets the card render a branded flacon fallback."""
        self.ensure_one()
        return bool(self.image_1920)

    # Brand → flacon tint for the placeholder bottle (mirrors the design).
    _YNF_BRAND_TINT = {
        "Lattafa": ("#7a2a2f", "#3d1416"), "Afnan": ("#26324f", "#141a2c"),
        "Rasasi": ("#1d4a3c", "#0f261f"), "Maison Alhambra": ("#43295a", "#241433"),
        "Armaf": ("#3a2e1a", "#1f1810"), "Jo Milano": ("#2a2a2e", "#141417"),
    }

    def ynf_flacon_tint(self):
        self.ensure_one()
        return self._YNF_BRAND_TINT.get(self.ynf_display_brand, ("#6b1f23", "#3a1416"))

    def ynf_discount(self):
        """Marketplace deal info from the native 'Compare to Price' field.
        Returns dict(has, compare, pct). Empty when no real MSRP is set — we
        never fabricate a strikethrough price."""
        self.ensure_one()
        compare = self.compare_list_price or 0.0
        price = self.list_price or 0.0
        if compare and price and compare > price:
            pct = int(round((compare - price) / compare * 100))
            return {"has": True, "compare": compare, "pct": pct}
        return {"has": False, "compare": 0.0, "pct": 0}

    def ynf_low_stock(self, threshold=10):
        """Real low-stock flag. Odoo 18 products are type='consu', so we key off
        on-hand qty + is_storable instead of the removed type=='product'.

        Reads qty via sudo: the public website user can't read stock quants, and
        an uncaught AccessError on the PDP surfaces as a 403."""
        self.ensure_one()
        rec = self.sudo()
        if not getattr(rec, "is_storable", False):
            return 0
        try:
            qty = rec.qty_available or 0
        except Exception:
            return 0
        return int(qty) if 0 < qty <= threshold else 0

    def ynf_product_jsonld(self):
        """schema.org Product JSON-LD for SEO (rich product results).

        Returns Markup so QWeb t-out injects it verbatim (already escaped JSON).
        """
        self.ensure_one()
        website = self.env["website"].get_current_website()
        base = website.get_base_url() if website else ""
        currency = website.currency_id.name if website and website.currency_id else "USD"
        try:
            img = base + website.image_url(self, "image_1024") if website else ""
        except Exception:
            img = ""
        data = {
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": self.name or "",
            "image": img,
            "description": (self.ynf_blurb or self.description_sale or self.name or "")[:300],
            "brand": {"@type": "Brand", "name": self.ynf_display_brand or "YNF Deals"},
            "category": self.ynf_family or "Fragrance",
            "offers": {
                "@type": "Offer",
                "priceCurrency": currency,
                "price": "%.2f" % (self.list_price or 0.0),
                "availability": "https://schema.org/InStock" if self.sale_ok else "https://schema.org/OutOfStock",
                "url": base + (self.website_url or ""),
            },
        }
        return Markup(json.dumps(data))

    @api.model
    def ynf_distinct_houses(self, limit=12):
        """Distinct display-houses across published, saleable products, ordered
        by how many products each house has (most-stocked first)."""
        prods = self.search([
            ("website_published", "=", True), ("sale_ok", "=", True),
        ], limit=600)
        counts = {}
        for p in prods:
            b = p.ynf_display_brand
            if b:
                counts[b] = counts.get(b, 0) + 1
        ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return [b for b, _ in ordered[:limit]]
