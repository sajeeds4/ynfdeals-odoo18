# -*- coding: utf-8 -*-
import base64
import logging
import urllib.request

_logger = logging.getLogger(__name__)

# Real product photos (brand CDN). Keyed by product name (case-insensitive,
# exact match first, then a loose contains match). Add rows as the catalog grows.
YNF_PRODUCT_IMAGES = {
    "Khamrah": "https://cdn.shopify.com/s/files/1/0754/4936/8799/files/Khamrah-1_0ffa4f52-30e3-4dea-9399-9bae4b8cb4af.png?v=1747421472",
    "Khamrah Qahwa": "https://cdn.shopify.com/s/files/1/0754/4936/8799/files/Khamrah-Qahwa-1_a2c9fdc2-8264-4da1-83e2-e5e065cecd53.png?v=1747416095",
    "Asad Bourbon": "https://cdn.shopify.com/s/files/1/0754/4936/8799/files/Asad-Bourbon-1.png?v=1747416709",
    "Asad Elixir": "https://cdn.shopify.com/s/files/1/0754/4936/8799/files/ASADELIXIRBOTTLE.png?v=1760805808",
    "Angham": "https://cdn.shopify.com/s/files/1/0754/4936/8799/files/Angham-1_fea96331-1cd0-467d-be6d-56ad073a7f86.png?v=1747415391",
    "Bade'e Al Oud Honor & Glory": "https://cdn.shopify.com/s/files/1/0754/4936/8799/files/Badee-Al-Oud-Honor-_-Glory-1_a3e5a0eb-fe3d-4799-8408-2874e3a642fa.png?v=1747415524",
    "Fakhar": "https://cdn.shopify.com/s/files/1/0754/4936/8799/files/1_aa0a5a38-775b-4814-a909-837c1d360d9c.png?v=1747500778",
    "His Confession": "https://cdn.shopify.com/s/files/1/0754/4936/8799/files/His-Confession-1_2614a68d-8561-4a94-9c54-7739ae06f986.png?v=1747415996",
    "Her Confession": "https://cdn.shopify.com/s/files/1/0754/4936/8799/files/Her-Confession-1_37f3fdce-b4e7-4c30-969a-f41ff87de13c.png?v=1747415953",
    "Eclaire": "https://cdn.shopify.com/s/files/1/0754/4936/8799/files/Eclaire-1_5803282e-ea5b-4de5-99a5-7d06f5cbae33.png?v=1747415649",
    "Maahir Legacy": "https://cdn.shopify.com/s/files/1/0754/4936/8799/files/Maahir-Legacy-1.png?v=1747421494",
    "Opulent Dubai": "https://cdn.shopify.com/s/files/1/0754/4936/8799/files/1_7d5801be-0a5e-4ac4-bffc-3bee4a3c7a6b.png?v=1756143162",
    "Asad Zanzibar": "https://cdn.shopify.com/s/files/1/0754/4936/8799/files/Asad-Zanzibar-1_ab5df442-9906-4109-81d1-a21265914bfd.png?v=1747415448",
    "Yara": "https://cdn.shopify.com/s/files/1/0575/8664/7246/files/LattafaYara01.jpg?v=1694120009",
    "9 PM Night Out": "https://us.afnan.com/cdn/shop/files/72.png?v=1768473569&width=800",
    "Supremacy Collector's Edition": "https://cdn.shopify.com/s/files/1/0655/0473/9421/files/SupremacyCollectionsEditionFront_Gray.png?v=1729755757",
    "Hawas": "https://cdn.shopify.com/s/files/1/0670/2940/1841/files/Hawas_Ice_1.jpg?v=1760625881",
    "Hawas Ice": "https://rasasistore.com/cdn/shop/files/Hawas_Ice_2.jpg?v=1709140605&width=800",
}


def _fetch(url):
    """Download an image URL and return base64 bytes, or None on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (YNF Odoo)"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return base64.b64encode(resp.read())
    except Exception as e:  # noqa: BLE001 - never block install on a bad URL
        _logger.warning("YNF: could not fetch image %s (%s)", url, e)
        return None


def post_init_hook(env):
    """Rebuild the top nav + backfill real product photos.

    Both steps are re-runnable and safe. Menu rebuild wipes + recreates the
    desired set under the website's top menu. Image backfill only fills
    products that have no image yet (never overwrites), matched by name
    (exact, then contains).
    """
    try:
        env["website"]._ynf_setup_menus()
    except Exception:
        _logger.exception("YNF: menu setup failed (non-fatal)")

    Product = env["product.template"].sudo()
    filled = 0
    for name, url in YNF_PRODUCT_IMAGES.items():
        product = Product.search([("name", "=ilike", name)], limit=1)
        if not product:
            product = Product.search([("name", "ilike", name)], limit=1)
        if not product:
            continue
        # Always store the URL (cheap, used as a template fallback)
        if not product.x_ynf_image_url:
            product.x_ynf_image_url = url
        # Only download the binary if the product has no image yet
        if not product.image_1920:
            data = _fetch(url)
            if data:
                product.image_1920 = data
                filled += 1
    _logger.info("YNF: product images backfilled for %s products", filled)
