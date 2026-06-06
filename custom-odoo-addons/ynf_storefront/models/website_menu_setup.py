from odoo import api, models


MEGA_COLLECTIONS_HTML = """
<section class="ynf-mega">
  <div class="container">
    <div class="row">
      <div class="col-6 col-lg-3">
        <h6 class="ynf-mega-title">By Gender</h6>
        <a href="/collections/men" class="ynf-mega-link">Men</a>
        <a href="/collections/women" class="ynf-mega-link">Women</a>
        <a href="/collections/unisex" class="ynf-mega-link">Unisex</a>
      </div>
      <div class="col-6 col-lg-3">
        <h6 class="ynf-mega-title">By Family</h6>
        <a href="/collections/oud-woody" class="ynf-mega-link">Oud &amp; Woody</a>
        <a href="/collections/sweet-gourmand" class="ynf-mega-link">Sweet &amp; Gourmand</a>
        <a href="/shop" class="ynf-mega-link">Fresh &amp; Citrus</a>
      </div>
      <div class="col-6 col-lg-3">
        <h6 class="ynf-mega-title">Featured</h6>
        <a href="/collections/gift-sets" class="ynf-mega-link">Gift Sets</a>
        <a href="/shop?order=create_date desc" class="ynf-mega-link">New Arrivals</a>
        <a href="/shop" class="ynf-mega-link">Best Sellers</a>
      </div>
      <div class="col-6 col-lg-3 ynf-mega-feature">
        <a href="/shop" class="ynf-mega-card">
          <span class="ynf-mega-card-eyebrow">Featured</span>
          <span class="ynf-mega-card-title">Shop the full catalog</span>
          <span class="ynf-mega-card-cta">Browse all &#8594;</span>
        </a>
      </div>
    </div>
  </div>
</section>
"""

# Exact nav: Shop, New Arrivals, Best Sellers, Collections (mega),
# Bundles, Live, Track My Order. (url, name, sequence, is_mega)
DESIRED_MENUS = [
    ("/shop", "Shop", 10, False),
    ("/shop?order=create_date desc", "New Arrivals", 20, False),
    ("/shop", "Best Sellers", 30, False),
    ("#collections", "Collections", 40, True),
    ("/collections/gift-sets", "Bundles", 50, False),
    ("/live", "Live", 55, False),
    ("/my/orders", "Track My Order", 60, False),
]


class Website(models.AbstractModel):
    _inherit = "website"

    @api.model
    def _ynf_setup_menus(self):
        """Idempotent: rebuild the top nav to exactly the desired item set."""
        Menu = self.env["website.menu"].sudo()
        top = Menu.search([("website_id", "=", 1), ("url", "=", "/default-main-menu")], limit=1)
        if not top:
            top = Menu.search([("website_id", "=", 1), ("parent_id", "=", False)], limit=1)
        if not top:
            return False
        parent_id = top.id

        existing = Menu.search([("parent_id", "=", parent_id)])
        existing.unlink()

        for url, name, seq, is_mega in DESIRED_MENUS:
            vals = {
                "name": name,
                "url": url,
                "parent_id": parent_id,
                "sequence": seq,
                "website_id": 1,
            }
            if is_mega:
                vals.update({
                    "is_mega_menu": True,
                    "mega_menu_content": MEGA_COLLECTIONS_HTML,
                    "mega_menu_classes": "o_mega_menu_container",
                    "url": "#",
                })
            Menu.create(vals)
        return True
