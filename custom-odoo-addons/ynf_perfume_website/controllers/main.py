# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale


# ── Shared domain builders: match an explicit ynf_ field OR the product name ──
# so brand/gender filtering works across the WHOLE catalogue (names already
# encode house + gender), not just the handful tagged by hand. No data writes.
def ynf_brand_domain(brand):
    return ["|", ("ynf_brand", "=ilike", brand), ("name", "=ilike", brand + " %")]


def ynf_gender_domain(gender):
    if gender == "unisex":
        return ["|", ("ynf_gender", "=", "unisex"), ("name", "ilike", "unisex")]
    if gender == "women":
        return ["|", "|",
                ("ynf_gender", "=", "women"),
                ("name", "ilike", "women"),
                ("name", "ilike", "femme")]
    if gender == "men":
        # "men" but not "women" (which contains the substring "men").
        return ["|",
                ("ynf_gender", "=", "men"),
                "&", "|",
                ("name", "ilike", "homme"),
                ("name", "ilike", "men"),
                ("name", "not ilike", "women")]
    return []


def ynf_family_domain(env, family_label):
    """Fuzzy olfactive-family browse: match the family's keywords in the name,
    family text or any notes tier. Keywords live in the model (single source)."""
    fams = env["product.template"]._YNF_FAMILIES
    kws = next((kw for _id, label, kw in fams if label == family_label), [])
    if not kws:
        return []
    fields = ("name", "ynf_family", "ynf_notes_top", "ynf_notes_heart", "ynf_notes_base")
    leaves = [(f, "ilike", k) for k in kws for f in fields]
    return ["|"] * (len(leaves) - 1) + leaves


class YnfPerfumeShop(WebsiteSale):
    """Extend the native /shop so our ?gender= and ?brand= chips filter the
    real product list. We add to the search domain and otherwise defer 100%
    to website_sale (pager, pricelist, attributes, sorting all untouched).
    """

    def _get_shop_domain(self, search, category, attrib_values, search_in_description=True):
        domain = super()._get_shop_domain(
            search, category, attrib_values, search_in_description=search_in_description)
        gender = request.params.get("gender")
        brand = request.params.get("brand")
        family = request.params.get("family")
        if gender in ("men", "women", "unisex"):
            domain += ynf_gender_domain(gender)
        if brand:
            domain += ynf_brand_domain(brand)
        if family:
            domain += ynf_family_domain(request.env, family)
        return domain

    def _shop_get_query_url_kwargs(self, category, search, *args, **kwargs):
        # Preserve our quick-filters across pagination / sort links.
        result = super()._shop_get_query_url_kwargs(category, search, *args, **kwargs)
        for key in ("gender", "brand", "family"):
            val = request.params.get(key)
            if val:
                result[key] = val
        return result


class YnfPerfumeWebsite(http.Controller):
    """Front-end data feeds for the luxury homepage.

    All product data is REAL Odoo data — pulled live from product.template,
    respecting website publication and the current pricelist.  We never invent
    products; if no perfume metadata is set the sections still render from the
    normal catalogue, degrading gracefully.
    """

    # How many products a rail/grid shows before "View all".
    _RAIL_LIMIT = 12

    def _published_products(self, domain=None, limit=None, order=None):
        Product = request.env["product.template"].sudo()
        base = [
            ("website_published", "=", True),
            ("sale_ok", "=", True),
        ]
        if domain:
            base += domain
        return Product.search(base, limit=limit, order=order or "create_date desc")

    def _homepage_values(self):
        """Assemble every homepage section from live catalogue data."""
        Product = request.env["product.template"].sudo()

        bestsellers = self._published_products(
            [("ynf_is_bestseller", "=", True)], limit=self._RAIL_LIMIT)
        if not bestsellers:
            # Fall back to most-recent published products so the section is never empty.
            bestsellers = self._published_products(limit=self._RAIL_LIMIT)

        trending = self._published_products(
            [("ynf_is_trending", "=", True)], limit=self._RAIL_LIMIT)
        new_arrivals = self._published_products(
            [("ynf_is_new", "=", True)], limit=self._RAIL_LIMIT)
        if not new_arrivals:
            new_arrivals = self._published_products(
                limit=self._RAIL_LIMIT, order="create_date desc")

        dupes = self._published_products(
            [("ynf_inspired_by", "!=", False)], limit=self._RAIL_LIMIT)

        # Hero = highest luxury score (prefer one with a real photo), else
        # first bestseller, else first imaged product.
        hero = self._published_products(
            [("ynf_luxury_score", ">", 0), ("image_1920", "!=", False)],
            limit=1, order="ynf_luxury_score desc")
        hero = (hero[:1] or self._published_products(
            [("ynf_luxury_score", ">", 0)], limit=1, order="ynf_luxury_score desc")[:1]
            or bestsellers[:1] or self._published_products([("image_1920", "!=", False)], limit=1))

        # Distinct fragrance houses derived from the catalogue (real data).
        brands = Product.ynf_distinct_houses(limit=10)

        # Olfactive families present in the catalogue (lead discovery facet).
        families = Product.ynf_distinct_families()

        # Gender collections — representative bottle per gender, preferring one
        # with a real photo so the tiles aren't gray placeholders.
        collections = []
        for code, label in [("men", "For Him"), ("women", "For Her"), ("unisex", "Unisex")]:
            sample = self._published_products(
                ynf_gender_domain(code) + [("image_1920", "!=", False)], limit=1)
            if not sample:
                sample = self._published_products(ynf_gender_domain(code), limit=1)
            collections.append({
                "code": code, "label": label,
                "product": sample[:1] and sample[0] or False,
            })

        return {
            "hero": hero[:1] and hero[0] or False,
            "bestsellers": bestsellers,
            "trending": trending,
            "new_arrivals": new_arrivals,
            "dupes": dupes,
            "brands": brands,
            "families": families,
            "collections": collections,
        }

    @http.route(["/", "/fragrances"], type="http", auth="public", website=True, sitemap=True)
    def ynf_home(self, **kw):
        values = self._homepage_values()
        return request.render("ynf_perfume_website.home_page", values)

    # ── Phase 9 · Fragrance Finder ──────────────────────────────────────
    # A 4-question quiz (gender, scent family/mood, budget, occasion) that
    # returns REAL catalogue matches. Pure read; an AI recommender can later
    # replace _finder_match() without touching the UI (extension point).
    _FINDER_MOODS = [
        {"id": "warm", "label": "Warm & Sweet", "sub": "Gourmand · amber · vanilla",
         "kw": ["gourmand", "amber", "vanilla", "sweet", "oud", "honey", "caramel"]},
        {"id": "fresh", "label": "Fresh & Clean", "sub": "Aquatic · citrus · cool",
         "kw": ["fresh", "aquatic", "citrus", "marine", "ice", "cool", "aqua", "blue"]},
        {"id": "woody", "label": "Woody & Spicy", "sub": "Cedar · oud · smoke",
         "kw": ["wood", "oud", "spicy", "smoke", "leather", "tobacco", "incense"]},
        {"id": "floral", "label": "Floral", "sub": "Rose · jasmine · blossom",
         "kw": ["floral", "rose", "jasmine", "blossom", "flower", "yara", "lily"]},
    ]
    _FINDER_BUDGETS = [
        {"id": "value", "label": "Under $30", "max": 30.0},
        {"id": "mid", "label": "$30 – $50", "min": 30.0, "max": 50.0},
        {"id": "premium", "label": "$50+", "min": 50.0},
        {"id": "any", "label": "Surprise me",},
    ]
    _FINDER_OCCASIONS = [
        {"id": "everyday", "label": "Everyday"},
        {"id": "office", "label": "Office"},
        {"id": "evening", "label": "Date / Evening"},
        {"id": "signature", "label": "Statement"},
    ]

    def _finder_match(self, gender=None, mood=None, budget=None, occasion=None, limit=8):
        """Score the catalogue against the quiz answers and return top matches."""
        Product = request.env["product.template"].sudo()
        domain = [("website_published", "=", True), ("sale_ok", "=", True)]
        if gender in ("men", "women", "unisex"):
            domain += ynf_gender_domain(gender)
        b = next((x for x in self._FINDER_BUDGETS if x["id"] == budget), None)
        if b and b.get("min"):
            domain.append(("list_price", ">=", b["min"]))
        if b and b.get("max"):
            domain.append(("list_price", "<=", b["max"]))
        candidates = Product.search(domain, limit=200)

        mood_def = next((m for m in self._FINDER_MOODS if m["id"] == mood), None)
        kws = mood_def["kw"] if mood_def else []

        # Occasion → preferred scent/keyword cues (Q4 now influences ranking).
        occasion_kw = {
            "everyday": ["fresh", "citrus", "light", "clean", "musk"],
            "office": ["fresh", "clean", "subtle", "woody", "light", "soft"],
            "evening": ["amber", "oud", "spicy", "vanilla", "leather", "intense", "warm"],
            "signature": ["oud", "amber", "extrait", "intense", "rich", "luxury", "noir"],
        }.get(occasion, [])

        scored = []
        for p in candidates:
            blob = " ".join(filter(None, [
                p.name or "", p.ynf_family or "", p.ynf_notes_top or "",
                p.ynf_notes_heart or "", p.ynf_notes_base or "", p.ynf_blurb or "",
            ])).lower()
            score = sum(2 for k in kws if k in blob)
            score += sum(1 for k in occasion_kw if k in blob)
            # 'signature/statement' favours stronger projection & longevity.
            if occasion in ("evening", "signature"):
                if p.ynf_projection and int(p.ynf_projection) >= 3:
                    score += 2
                if p.ynf_longevity and int(p.ynf_longevity) >= 3:
                    score += 1
            if p.ynf_is_bestseller:
                score += 3
            if p.ynf_luxury_score:
                score += min(3, p.ynf_luxury_score // 30)
            scored.append((score, p))
        # Highest score first; stable fallback keeps bestsellers up top.
        scored.sort(key=lambda sp: sp[0], reverse=True)
        matches = [p for s, p in scored if s > 0][:limit]
        if not matches:  # nothing matched the mood → still return budget/gender picks
            matches = [p for s, p in scored][:limit]
        return matches

    @http.route("/live", type="http", auth="public", website=True, sitemap=True)
    def ynf_live(self, **kw):
        """Live-auction page: countdown, how-it-works, tonight's lineup from real
        products (prefer bestsellers / luxury picks, imaged first)."""
        lineup = self._published_products(
            [("ynf_is_bestseller", "=", True), ("image_1920", "!=", False)], limit=6)
        if len(lineup) < 5:
            extra = self._published_products(
                [("image_1920", "!=", False)],
                limit=6, order="ynf_luxury_score desc, create_date desc")
            lineup = (lineup | extra)[:6]
        return request.render("ynf_perfume_website.live_page", {"lineup": lineup})

    @http.route("/fragrance-finder", type="http", auth="public", website=True, sitemap=True)
    def ynf_finder(self, **kw):
        gender = kw.get("gender")
        mood = kw.get("mood")
        budget = kw.get("budget")
        occasion = kw.get("occasion")
        submitted = bool(kw.get("submitted"))
        results = []
        if submitted:
            results = self._finder_match(gender, mood, budget, occasion)
        return request.render("ynf_perfume_website.finder_page", {
            "moods": self._FINDER_MOODS,
            "budgets": self._FINDER_BUDGETS,
            "occasions": self._FINDER_OCCASIONS,
            "answers": {"gender": gender, "mood": mood, "budget": budget, "occasion": occasion},
            "submitted": submitted,
            "results": results,
        })
