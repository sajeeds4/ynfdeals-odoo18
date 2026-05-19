#!/usr/bin/env python3
"""
Retired SQLite product-image backfill script.

This script used to mutate data/whatnot.db directly. The runtime database is
Postgres-first now, so the legacy entrypoint fails closed instead of opening
SQLite. Port the query/update path to a Postgres service before re-enabling it.
"""
import re
import time
import urllib.request
import urllib.parse
import ssl
import json

LEGACY_SQLITE_RETIRED = (
    "fetch_missing_images.py is retired because it writes directly to SQLite. "
    "Use a Postgres-backed product-image backfill path instead."
)

# Skip SSL verification for some sites
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}


def fetch_url(url, timeout=15):
    """Fetch a URL and return the HTML content."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return None


def extract_og_image(html):
    """Extract og:image meta tag from HTML."""
    if not html:
        return None
    # Try og:image
    m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.I)
    if m:
        url = m.group(1)
        # Filter out generic/placeholder images
        if any(x in url.lower() for x in ["placeholder", "no-image", "default", "logo"]):
            return None
        return url
    return None


def extract_shopify_images(html):
    """Extract Shopify CDN image URLs from HTML."""
    if not html:
        return []
    urls = re.findall(r'(https://cdn\.shopify\.com/s/files/[^"\'>\s]+\.(?:jpg|png|webp))', html, re.I)
    # Filter to product images (not icons, logos, etc.)
    product_imgs = [u for u in urls if "/products/" in u]
    return list(dict.fromkeys(product_imgs))  # dedupe, preserve order


def search_google_for_image(query):
    """Search Google and try to find product image from results."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded}&tbm=isch&udm=2"
    html = fetch_url(url)
    if not html:
        return None
    # Google image search embeds image URLs in data attributes
    # Try to extract direct image URLs
    imgs = re.findall(r'(https://[^"\'>\s]+\.(?:jpg|jpeg|png|webp))', html)
    # Filter for CDN / product images
    for img in imgs:
        if any(d in img for d in ["cdn.shopify.com", "fragrantica.com", "scentgod", "fragrancebuy"]):
            return img
    return None


def try_fragrantica(name):
    """Search fragrantica for the product image."""
    # Clean name for search
    clean = re.sub(r'\s*EDP\s*-?\s*\d+ml\s*', '', name)
    clean = re.sub(r'\[.*?\]\s*', '', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    encoded = urllib.parse.quote_plus(f"{clean} site:fragrantica.com")
    url = f"https://www.google.com/search?q={encoded}"
    html = fetch_url(url)
    if not html:
        return None
    # Find fragrantica URLs in results
    frag_urls = re.findall(r'(https://www\.fragrantica\.com/perfume/[^"\'>\s&]+)', html)
    for furl in frag_urls[:2]:
        fhtml = fetch_url(furl)
        img = extract_og_image(fhtml)
        if img:
            return img
    return None


def try_retailer_search(name, barcode):
    """Try various retailer searches."""
    retailers = [
        ("fragrancebuy.ca", f"https://fragrancebuy.ca/search?type=product&q={urllib.parse.quote_plus(name)}"),
        ("albaazperfumes.com", f"https://albaazperfumes.com/search?type=product&q={urllib.parse.quote_plus(barcode or name)}"),
    ]

    for rname, url in retailers:
        html = fetch_url(url)
        if not html:
            continue
        # Find product links
        if "shopify" in html.lower() or "cdn.shopify.com" in html:
            imgs = extract_shopify_images(html)
            if imgs:
                # Pick the first product image, preferring larger sizes
                for img in imgs:
                    # Upgrade to larger size
                    img = re.sub(r'_\d+x\d+', '_600x600', img)
                    img = re.sub(r'\?v=\d+', '', img)
                    return img
        # Try og:image from result pages
        product_links = re.findall(rf'href=["\']/(products/[^"\'>\s]+)["\']', html)
        for plink in product_links[:2]:
            purl = f"https://{rname}/{plink}"
            phtml = fetch_url(purl)
            img = extract_og_image(phtml)
            if img:
                return img
    return None


def try_barcode_lookup(barcode):
    """Try barcode lookup sites."""
    if not barcode or barcode == "1234567":
        return None

    # Try Open Food Facts / UPC lookup
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    html = fetch_url(url)
    if html:
        try:
            data = json.loads(html)
            if data.get("status") == 1:
                img = data.get("product", {}).get("image_url")
                if img:
                    return img
        except:
            pass

    return None


def find_image_for_product(product_id, name, barcode):
    """Try multiple strategies to find an image for a product."""
    clean_name = re.sub(r'\[.*?\]\s*', '', name).strip()

    # Strategy 1: Search retailer sites
    img = try_retailer_search(clean_name, barcode)
    if img:
        return img

    # Strategy 2: Try fragrantica
    img = try_fragrantica(clean_name)
    if img:
        return img

    # Strategy 3: Google image search
    img = search_google_for_image(f"{clean_name} perfume bottle")
    if img:
        return img

    # Strategy 4: Barcode lookup
    img = try_barcode_lookup(barcode)
    if img:
        return img

    return None


def main():
    raise SystemExit(LEGACY_SQLITE_RETIRED)


if __name__ == "__main__":
    main()
